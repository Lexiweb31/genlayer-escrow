"""Merit marketplace API.

Live writes are explicit, server-signed Bradbury demo transactions. The API
requires two different demo accounts so one identity cannot act as both client
and worker. Marketplace metadata lives in SQLite, using ``PERSIST_DATA_DIR``
when a Render persistent disk is mounted.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).parents[1]
load_dotenv(ROOT / ".env")

import eth_utils
from genlayer_py import create_account, create_client, testnet_bradbury
from genlayer_py.abi.calldata.decoder import decode as calldata_decode
from genlayer_py.abi.calldata.encoder import encode as calldata_encode
from genlayer_py.abi.transactions import serialize as tx_serialize
from genlayer_py.contracts.utils import make_calldata_object
from genlayer_py.types.calldata import CalldataAddress
from genlayer_py.types.transactions import TransactionStatus

from dashboard.store import JobStore, utc_now


# ── Network and account configuration ─────────────────────────────────────────
EXPLORER = "https://explorer-bradbury.genlayer.com"
EXPLORER_ADDRESS = EXPLORER + "/address/"
EXPLORER_TX = EXPLORER + "/tx/"

deployments_path = ROOT / "artifacts" / "deployments.json"
deployments = json.loads(deployments_path.read_text()) if deployments_path.exists() else {}
EVAL_ADDR = str(deployments.get("evaluate_submission") or "")
ESCROW_CODE = (ROOT / "contracts" / "freelance_escrow.py").read_text()


def _configure_demo_accounts() -> tuple[Any, Any, Optional[str]]:
    client_key = os.getenv("DEMO_CLIENT_PRIVATE_KEY", "").strip()
    worker_key = os.getenv("DEMO_WORKER_PRIVATE_KEY", "").strip()
    if not client_key and not worker_key:
        return None, None, (
            "Live multi-role actions are disabled. Configure two different Bradbury "
            "demo keys to enable server-signed demo transactions."
        )
    if not client_key or not worker_key:
        return None, None, (
            "Both DEMO_CLIENT_PRIVATE_KEY and DEMO_WORKER_PRIVATE_KEY are required; "
            "live multi-role actions remain disabled."
        )
    try:
        client_account = create_account(client_key)
        worker_account = create_account(worker_key)
    except Exception:
        # Never reflect account-parser errors: some libraries include the
        # rejected key in their exception message.
        return None, None, (
            "Demo account configuration is invalid. Check both server-side "
            "Bradbury demo secrets."
        )
    if str(client_account.address).lower() == str(worker_account.address).lower():
        return None, None, (
            "DEMO_CLIENT_PRIVATE_KEY and DEMO_WORKER_PRIVATE_KEY resolve to the same "
            "address. Different demo identities are required."
        )
    return client_account, worker_account, None


demo_client_account, demo_worker_account, DEMO_CONFIG_ERROR = _configure_demo_accounts()
DEMO_ROLES_READY = DEMO_CONFIG_ERROR is None
network_client = create_client(testnet_bradbury)


def _read_sender() -> str:
    if demo_client_account is not None:
        return str(demo_client_account.address)
    return str(deployments.get("deployer") or "0x0000000000000000000000000000000000000000")


def _demo_public_config() -> dict[str, Any]:
    platform_address = os.getenv("PLATFORM_FEE_ADDRESS", "").strip() or str(
        deployments.get("platform") or deployments.get("deployer") or ""
    )
    return {
        "mode": "server-signed-demo" if DEMO_ROLES_READY else "simulated-walkthrough",
        "network": "testnet_bradbury",
        "live_actions_enabled": DEMO_ROLES_READY,
        "client_address": str(demo_client_account.address) if demo_client_account else None,
        "worker_address": str(demo_worker_account.address) if demo_worker_account else None,
        "platform_address": platform_address or None,
        "notice": (
            "Transactions are signed by separate Bradbury demo accounts on the server. "
            "No browser wallet is connected and visitors do not control deposited GEN."
            if DEMO_ROLES_READY
            else DEMO_CONFIG_ERROR
        ),
    }


# ── Durable job registry ──────────────────────────────────────────────────────
store = JobStore()
LEGACY_JOBS_FILE = ROOT / "artifacts" / "jobs.json"


def _import_legacy_jobs() -> None:
    records: list[dict[str, Any]] = []
    if LEGACY_JOBS_FILE.exists():
        try:
            payload = json.loads(LEGACY_JOBS_FILE.read_text())
            records.extend(payload.get("jobs", []))
        except Exception:
            # Keep the source untouched. A malformed old file must not prevent boot.
            pass
    seed = deployments.get("freelance_escrow")
    if seed:
        seed_record = {
            "id": seed,
            "address": seed,
            "title": "Fintech landing page",
            "spec": (
                "Build a landing page for a fintech startup. Must include a hero section, "
                "features, and a contact footer."
            ),
            "fee_bps": 200,
            "min_score": 70,
            "partial_floor": 40,
            "client_address": str(deployments.get("demo_client") or deployments.get("deployer") or ""),
            "worker_address": str(deployments.get("demo_worker") or ""),
            "deployment_tx": str(deployments.get("deployment_transaction") or ""),
            "created_at": utc_now(),
        }
        if deployments.get("settlement_version") == "safe-eoa-external-message-v2":
            store.add_job(seed_record, ignore_existing=True)
        else:
            seed_record["title"] += " (legacy)"
            records.append(seed_record)
    store.import_legacy_records(records)


_import_legacy_jobs()


def _find_job(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={
            "code": "JOB_NOT_FOUND",
            "message": f"No job with id {job_id}",
        })
    return job


def _require_live_roles() -> None:
    if not DEMO_ROLES_READY:
        raise HTTPException(status_code=503, detail={
            "code": "DEMO_ROLES_UNAVAILABLE",
            "message": DEMO_CONFIG_ERROR,
            "action": "Use the clearly labeled simulated walkthrough or configure two different demo keys.",
        })


def _require_safe_job(job: dict[str, Any]) -> None:
    if job.get("legacy_contract"):
        raise HTTPException(status_code=409, detail={
            "code": "LEGACY_SETTLEMENT_CONTRACT",
            "message": "Legacy settlement contract — do not fund or submit transactions.",
            "action": "Create a new escrow after the safety patch instead.",
        })


# ── Chain helpers ─────────────────────────────────────────────────────────────
def _wait(tx_hash: str, status: TransactionStatus = TransactionStatus.ACCEPTED) -> dict[str, Any]:
    # Bradbury can expose intermediate statuses that older genlayer-py builds
    # cannot decode. Poll the official lightweight status RPC first, then ask
    # the SDK for the full transaction only once it reaches a stable status.
    # https://docs.genlayer.com/api-references/genlayer-node/gen/gen_getTransactionStatus
    receipt: dict[str, Any] | None = None
    last_status = "UNKNOWN"
    terminal_failures = {
        "CANCELED",
        "UNDETERMINED",
        "VALIDATORS_TIMEOUT",
        "LEADER_TIMEOUT",
        "OUT_OF_FEE",
        "OUTOFFEE",
    }
    for _attempt in range(120):
        response = network_client.provider.make_request(
            method="gen_getTransactionStatus",
            params=[{"txId": tx_hash}],
        )
        result = response.get("result") or {}
        last_status = str(result.get("status") or result.get("statusCode") or "UNKNOWN")
        normalized = last_status.replace(" ", "_").replace("-", "_").upper()
        reached_target = normalized == "FINALIZED" or (
            status == TransactionStatus.ACCEPTED and normalized == "ACCEPTED"
        )
        if reached_target:
            receipt = dict(network_client.get_transaction(tx_hash))
            break
        if normalized in terminal_failures:
            if normalized in {"OUT_OF_FEE", "OUTOFFEE"}:
                raise RuntimeError(
                    f"Insufficient demo GEN: transaction {tx_hash} entered {normalized}."
                )
            raise RuntimeError(
                f"Testnet rejected transaction {tx_hash} with status {normalized}."
            )
        time.sleep(5)
    if receipt is None:
        raise RuntimeError(
            f"Transaction {tx_hash} did not reach {status.value}; last status {last_status}."
        )
    status_name = _status_name(receipt)
    execution = str(receipt.get("tx_execution_result_name") or "")
    if status_name not in {"ACCEPTED", "FINALIZED", "5", "7"}:
        raise RuntimeError(f"Testnet rejected transaction {tx_hash} with status {status_name}")
    if "ERROR" in execution.upper():
        raise RuntimeError(f"Testnet execution failed for {tx_hash}: {execution}")
    return dict(receipt)


def _call_read(contract_addr: str, method: str, args: list[Any] | None = None) -> str:
    data = [
        calldata_encode(make_calldata_object(method=method, args=args or [], kwargs=None)),
        b"\x00",
    ]
    raw = network_client.provider.make_request(
        method="gen_call",
        params=[{
            "type": "read",
            "to": contract_addr,
            "from": _read_sender(),
            "data": tx_serialize(data),
            "transaction_hash_variant": "latest-nonfinal",
        }],
    )["result"]
    hex_str = raw["data"] if isinstance(raw, dict) else raw
    return calldata_decode(eth_utils.hexadecimal.decode_hex("0x" + hex_str))


def _call_write(
    contract_addr: str,
    method: str,
    role: str,
    args: list[Any] | None = None,
    value: int = 0,
) -> str:
    _require_live_roles()
    role_account = demo_client_account if role == "client" else demo_worker_account
    return network_client.write_contract(
        address=contract_addr,
        function_name=method,
        account=role_account,
        args=args or [],
        value=value,
    )


def _get_address(receipt: dict[str, Any]) -> Optional[str]:
    td = receipt.get("tx_data_decoded") or {}
    return td.get("contract_address") or receipt.get("recipient")


def _status_name(transaction: dict[str, Any]) -> str:
    raw = transaction.get("status_name") or transaction.get("status") or "UNKNOWN"
    value = str(getattr(raw, "value", raw)).upper()
    return {"5": "ACCEPTED", "7": "FINALIZED"}.get(value, value.upper())


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _external_value_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Normalize finalized external-message recipients and GEN values."""
    records = []
    for message in messages:
        if isinstance(message, dict):
            recipient = message.get("recipient")
            amount = message.get("value")
        elif isinstance(message, list) and len(message) >= 3:
            recipient = message[1]
            amount = message[2]
        else:
            continue
        try:
            amount = int(amount or 0)
        except (TypeError, ValueError):
            continue
        if recipient and amount > 0:
            records.append({"recipient": str(recipient), "amount": amount})
    return records


def _addresses(escrow_addr: str) -> dict[str, Any]:
    return {
        "escrow": escrow_addr,
        "evaluator": EVAL_ADDR,
        "demo_client": str(demo_client_account.address) if demo_client_account else None,
        "demo_worker": str(demo_worker_account.address) if demo_worker_account else None,
        "explorer_escrow": EXPLORER_ADDRESS + escrow_addr,
        "explorer_evaluator": EXPLORER_ADDRESS + EVAL_ADDR if EVAL_ADDR else None,
        "account_mode": "Bradbury demo account",
    }


def _job_state(escrow_addr: str) -> dict[str, Any]:
    job = json.loads(_call_read(escrow_addr, "get_job"))
    result = json.loads(_call_read(escrow_addr, "get_result"))
    return {"job": job, "result": result}


def _expected_state(method: str) -> str:
    return {
        "fund": "UNFUNDED",
        "accept_terms": "OPEN",
        "submit_work": "AGREED",
        "evaluate": "SUBMITTED",
        "appeal": "EVALUATED",
        "finalize": "EVALUATED",
    }[method]


def _role_address(role: str) -> str:
    account = demo_client_account if role == "client" else demo_worker_account
    return str(account.address) if account else ""


def _preflight(job: dict[str, Any], method: str, role: str) -> dict[str, Any]:
    _require_live_roles()
    _require_safe_job(job)
    state = _job_state(job["address"])
    chain_job = state["job"]
    expected_status = _expected_state(method)
    actual_status = str(chain_job.get("status") or "UNKNOWN")
    if actual_status != expected_status:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_STATE",
            "message": f"Job is {actual_status}; {method} requires {expected_status}.",
            "expected_status": expected_status,
            "actual_status": actual_status,
        })
    expected_actor = str(chain_job.get(role) or "")
    signer = _role_address(role)
    if not signer or expected_actor.lower() != signer.lower():
        raise HTTPException(status_code=403, detail={
            "code": "WRONG_ROLE",
            "message": f"The configured {role} demo account is not the on-chain {role} for this job.",
            "expected_address": expected_actor,
            "configured_address": signer or None,
        })
    return state


def _action_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    message = str(exc)
    lowered = message.lower()
    if "insufficient" in lowered or "balance" in lowered or "funds" in lowered:
        return HTTPException(status_code=402, detail={
            "code": "INSUFFICIENT_DEMO_GEN",
            "message": "The Bradbury demo account has insufficient testnet GEN for this transaction.",
            "testnet_detail": message,
        })
    if "[expected]" in lowered or "already funded" in lowered or "not yet evaluated" in lowered:
        return HTTPException(status_code=409, detail={
            "code": "STALE_STATE",
            "message": "The on-chain job state changed before this server-signed demo transaction was accepted.",
            "testnet_detail": message,
        })
    return HTTPException(status_code=502, detail={
        "code": "TESTNET_REJECTION",
        "message": "Bradbury rejected or could not finalize the server-signed demo transaction.",
        "testnet_detail": message,
    })


def _refresh_settlement(meta: dict[str, Any], chain_job: dict[str, Any]) -> dict[str, Any]:
    contract_settlement = chain_job.get("settlement") or {}
    settlement = {**contract_settlement, **(meta.get("settlement") or {})}
    parent_tx = settlement.get("parent_transaction")
    if not parent_tx:
        return settlement
    try:
        transaction = dict(network_client.get_transaction(parent_tx))
        parent_status = _status_name(transaction)
        messages = _json_safe(transaction.get("messages") or [])
        try:
            triggered = _json_safe(network_client.get_triggered_transaction_ids(parent_tx))
        except Exception:
            triggered = []
        triggered = [str(reference) for reference in triggered if reference]
        nonzero_transfers = [
            transfer for transfer in settlement.get("transfers", [])
            if int(transfer.get("amount") or 0) > 0
        ]
        external_messages = _external_value_messages(messages)
        confirmed_external = bool(nonzero_transfers) and all(
            any(
                str(message["recipient"]).lower() == str(transfer.get("recipient") or "").lower()
                and message["amount"] == int(transfer.get("amount") or 0)
                for message in external_messages
            )
            for transfer in nonzero_transfers
        )
        transfer_evidence = []
        for index, reference in enumerate(triggered):
            transfer = nonzero_transfers[index] if index < len(nonzero_transfers) else {}
            settlement_type = str(transfer.get("settlement_type") or "TRANSFER")
            recipient_role = {
                "WORKER_PAYOUT": "worker",
                "CLIENT_REFUND": "client",
                "PLATFORM_FEE": "platform",
            }.get(settlement_type, "recipient")
            transfer_evidence.append({
                "reference": reference,
                "status": "CONFIRMED" if parent_status == "FINALIZED" else "PENDING",
                "explorer": EXPLORER_TX + reference,
                "recipient_role": recipient_role,
                "recipient": transfer.get("recipient"),
                "amount": int(transfer.get("amount") or 0),
                "settlement_type": settlement_type,
            })
        if not triggered and parent_status == "FINALIZED" and confirmed_external:
            for transfer in nonzero_transfers:
                settlement_type = str(transfer.get("settlement_type") or "TRANSFER")
                transfer_evidence.append({
                    "reference": parent_tx,
                    "status": "CONFIRMED",
                    "explorer": EXPLORER_TX + parent_tx,
                    "recipient_role": {
                        "WORKER_PAYOUT": "worker",
                        "CLIENT_REFUND": "client",
                        "PLATFORM_FEE": "platform",
                    }.get(settlement_type, "recipient"),
                    "recipient": transfer.get("recipient"),
                    "amount": int(transfer.get("amount") or 0),
                    "settlement_type": settlement_type,
                })
        primary_reference = triggered[0] if triggered else parent_tx
        settlement.update({
            "parent_status": parent_status,
            "messages": messages,
            "triggered_transaction_ids": triggered,
            "transfer_reference": triggered or [parent_tx],
            "transfer_evidence": transfer_evidence,
            "confirmation_basis": (
                "TRIGGERED_TRANSACTION" if triggered
                else "FINALIZED_EXTERNAL_MESSAGE" if confirmed_external
                else None
            ),
            "parent_explorer": EXPLORER_TX + parent_tx,
            "explorer": EXPLORER_TX + primary_reference,
        })
        # External EOA messages execute during parent finalization and therefore
        # do not always produce a child GenLayer transaction ID. Confirm only
        # when every contract-recorded transfer matches a finalized message, or
        # when the network exposes an inspectable triggered transaction.
        if parent_status == "FINALIZED" and (triggered or confirmed_external):
            settlement["transfer_status"] = "FINALIZED"
            settlement["finalized_at"] = settlement.get("finalized_at") or utc_now()
        elif parent_status == "FINALIZED":
            settlement["transfer_status"] = "PENDING_TRANSFER_RECORD"
        else:
            settlement["transfer_status"] = "PENDING_FINALIZATION"
        store.update_job(meta["address"], settlement=settlement)
    except Exception as exc:
        settlement["transfer_status"] = settlement.get("transfer_status") or "PENDING_FINALIZATION"
        settlement["status_error"] = str(exc)
    return settlement


def _settlement_for_wire(settlement: dict[str, Any]) -> dict[str, Any]:
    """Serialize wei values as decimal strings so JSON never loses precision."""
    output = dict(settlement)
    for field in ("transfers", "transfer_evidence"):
        rows = output.get(field)
        if not isinstance(rows, list):
            continue
        output[field] = [
            {
                **row,
                **(
                    {"amount": str(_wei_int(row.get("amount")))}
                    if isinstance(row, dict) and "amount" in row
                    else {}
                ),
            }
            if isinstance(row, dict)
            else row
            for row in rows
        ]
    return output


def _public_state(meta: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    chain_job = dict(state["job"])
    result = dict(state["result"])
    if meta.get("legacy_contract"):
        chain_job["on_chain_status"] = chain_job.get("status")
        chain_job["status"] = "LEGACY_UNSAFE"
        chain_job["legacy_contract"] = True
        chain_job["legacy_warning"] = "Legacy settlement contract — do not fund"
        if "amount" in chain_job:
            chain_job["amount"] = str(_wei_int(chain_job.get("amount")))
        if isinstance(chain_job.get("settlement"), dict):
            chain_job["settlement"] = _settlement_for_wire(chain_job["settlement"])
        result["status"] = "LEGACY_UNSAFE"
        return {"job": chain_job, "result": result}
    settlement = _refresh_settlement(meta, chain_job)
    chain_job["legacy_contract"] = False
    chain_job["on_chain_status"] = chain_job.get("status")
    if settlement.get("transfer_status") == "FINALIZED" and settlement.get("outcome"):
        chain_job["status"] = settlement["outcome"]
        result["status"] = settlement["outcome"]
    if "amount" in chain_job:
        chain_job["amount"] = str(_wei_int(chain_job.get("amount")))
    chain_job["settlement"] = _settlement_for_wire(settlement)
    return {"job": chain_job, "result": result}


# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="Merit Escrow Marketplace")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://genlayer-escrow.vercel.app",
        "https://lexiweb31.github.io",
        "http://localhost:8001",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "index.html").read_text()


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "network": "testnet_bradbury",
        "jobs": len(store.list_jobs()),
        "storage": "sqlite",
        "persistent_data_dir_configured": bool(os.getenv("PERSIST_DATA_DIR")),
        "demo": _demo_public_config(),
    }


@app.get("/api/demo-mode")
def demo_mode():
    return _demo_public_config()


MIN_DEMO_AMOUNT_WEI = 10**15  # 0.001 GEN
_ACTIVE_STATUSES = {"UNFUNDED", "OPEN", "AGREED", "SUBMITTED", "EVALUATED", "SETTLEMENT_PENDING"}
_LOCKED_STATUSES = {"OPEN", "AGREED", "SUBMITTED", "EVALUATED"}
_EVALUATED_STATUSES = {"EVALUATED", "SETTLEMENT_PENDING", "ACCEPTED", "PARTIAL", "REFUNDED"}
_FINAL_STATUSES = {"ACCEPTED", "PARTIAL", "REFUNDED"}


def _wei_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _settlement_wei(entry: dict[str, Any]) -> int:
    settlement = entry.get("settlement") or {}
    total = sum(
        _wei_int(transfer.get("amount"))
        for transfer in settlement.get("transfers", [])
        if isinstance(transfer, dict)
    )
    return total or _wei_int(entry.get("amount"))


def _marketplace_stats(
    jobs: list[dict[str, Any]],
    *,
    total_jobs: int,
    degraded_jobs: int,
    legacy_jobs: int,
) -> dict[str, Any]:
    locked_wei = sum(
        _wei_int(job.get("amount"))
        for job in jobs
        if job.get("status") in _LOCKED_STATUSES
    )
    pending_jobs = [job for job in jobs if job.get("status") == "SETTLEMENT_PENDING"]
    pending_wei = sum(_settlement_wei(job) for job in pending_jobs)
    finalized_jobs = [job for job in jobs if job.get("status") in _FINAL_STATUSES]
    finalized_wei = sum(_settlement_wei(job) for job in finalized_jobs)
    protected_wei = locked_wei + pending_wei
    return {
        "network": "testnet_bradbury",
        "total_jobs": total_jobs,
        "active_jobs": sum(1 for job in jobs if job.get("status") in _ACTIVE_STATUSES),
        "open_opportunities": sum(
            1 for job in jobs if job.get("status") in {"UNFUNDED", "OPEN"}
        ),
        "locked_wei": str(locked_wei),
        "pending_settlement_wei": str(pending_wei),
        "protected_wei": str(protected_wei),
        "settlement_pending": len(pending_jobs),
        "finalized_settlements": len(finalized_jobs),
        "finalized_settlement_wei": str(finalized_wei),
        # Backward-compatible aliases for clients deployed before this release.
        "escrow_wei": str(locked_wei),
        "escrow_gen": locked_wei / 10**18,
        "degraded_jobs": degraded_jobs,
        "legacy_jobs": legacy_jobs,
        "generated_at": utc_now(),
    }


@app.get("/api/stats")
def stats():
    return list_jobs()["stats"]


@app.get("/api/jobs")
def list_jobs():
    output: list[dict[str, Any]] = []
    records = store.list_jobs()
    degraded = 0
    for meta in records:
        entry = dict(meta)
        if meta.get("legacy_contract"):
            entry.update({
                "status": "LEGACY_UNSAFE",
                "legacy_warning": "Legacy settlement contract — do not fund",
            })
        else:
            try:
                public = _public_state(meta, _job_state(meta["address"]))
                entry["status"] = public["job"].get("status")
                entry["amount"] = public["job"].get("amount")
                entry["evaluation_complete"] = entry["status"] in _EVALUATED_STATUSES
                entry["score"] = (
                    public["result"].get("score")
                    if entry["evaluation_complete"]
                    else None
                )
                entry["settlement"] = public["job"].get("settlement")
                store.update_job(meta["address"], lifecycle_status=entry["status"])
            except Exception as exc:
                entry["status"] = "UNKNOWN"
                entry["error"] = str(exc)
                degraded += 1
        output.append(entry)
    return {
        "jobs": output,
        "stats": _marketplace_stats(
            output,
            total_jobs=len(records),
            degraded_jobs=degraded,
            legacy_jobs=sum(1 for job in records if job.get("legacy_contract")),
        ),
        "demo": _demo_public_config(),
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    meta = _find_job(job_id)
    try:
        public = _public_state(meta, _job_state(meta["address"]))
        return {
            "meta": meta,
            "job": public["job"],
            "result": public["result"],
            "addresses": _addresses(meta["address"]),
            "demo": _demo_public_config(),
        }
    except Exception as exc:
        if meta.get("legacy_contract"):
            return {
                "meta": {**meta, "legacy_warning": "Legacy settlement contract — do not fund"},
                "job": {
                    "status": "LEGACY_UNSAFE",
                    "legacy_contract": True,
                    "legacy_warning": "Legacy settlement contract — do not fund",
                },
                "result": {"status": "LEGACY_UNSAFE"},
                "addresses": _addresses(meta["address"]),
                "demo": _demo_public_config(),
            }
        raise HTTPException(status_code=502, detail={
            "code": "TESTNET_READ_FAILED",
            "message": "Bradbury job state could not be read.",
            "testnet_detail": str(exc),
        })


# ── Create and action routes ──────────────────────────────────────────────────
class CreateJobRequest(BaseModel):
    spec: str
    title: Optional[str] = None
    fee_bps: int = Field(default=200, ge=0, le=1000)
    min_score: int = Field(default=70, ge=0, le=100)
    partial_floor: int = Field(default=40, ge=0, le=100)


class RegisterWalletJobRequest(CreateJobRequest):
    address: str
    client_address: str
    worker_address: str
    deployment_tx: str


@app.post("/api/jobs/register")
def register_wallet_job(req: RegisterWalletJobRequest):
    address_pattern = re.compile(r"^0x[0-9a-fA-F]{40}$")
    tx_pattern = re.compile(r"^0x[0-9a-fA-F]{64}$")
    if not address_pattern.fullmatch(req.address):
        raise HTTPException(status_code=422, detail={"code": "INVALID_CONTRACT_ADDRESS", "message": "Invalid escrow contract address."})
    if not address_pattern.fullmatch(req.client_address) or not address_pattern.fullmatch(req.worker_address):
        raise HTTPException(status_code=422, detail={"code": "INVALID_ROLE_ADDRESS", "message": "Invalid client or worker address."})
    if req.client_address.lower() == req.worker_address.lower():
        raise HTTPException(status_code=422, detail={"code": "SAME_ROLE_ADDRESS", "message": "Client and worker must use different wallets."})
    if not tx_pattern.fullmatch(req.deployment_tx):
        raise HTTPException(status_code=422, detail={"code": "INVALID_DEPLOYMENT_TX", "message": "Invalid deployment transaction hash."})
    if req.partial_floor > req.min_score:
        raise HTTPException(status_code=422, detail={"code": "INVALID_THRESHOLDS", "message": "partial_floor cannot exceed min_score"})
    spec = req.spec.strip()
    if len(spec) < 20:
        raise HTTPException(status_code=422, detail={"code": "INVALID_SPEC", "message": "Spec must be at least 20 characters"})

    try:
        state = _job_state(req.address)["job"]
    except Exception:
        raise HTTPException(status_code=422, detail={"code": "CONTRACT_NOT_READABLE", "message": "The deployed escrow could not be verified on Bradbury."})
    expected = {
        "client": req.client_address,
        "worker": req.worker_address,
        "spec": spec,
        "fee_bps": req.fee_bps,
        "min_score": req.min_score,
        "partial_floor": req.partial_floor,
        "status": "UNFUNDED",
    }
    for key, value in expected.items():
        actual = state.get(key)
        if key in ("client", "worker"):
            matches = str(actual).lower() == str(value).lower()
        else:
            matches = actual == value
        if not matches:
            raise HTTPException(status_code=422, detail={"code": "CONTRACT_METADATA_MISMATCH", "message": "The deployed contract does not match the submitted job details."})

    existing = store.get_job(req.address)
    if existing:
        return {"job": existing, "tx": req.deployment_tx, "transaction_type": "wallet-signed transaction", "signer_role": "connected Bradbury client wallet", "network": "testnet_bradbury"}
    record = store.add_job({
        "id": req.address,
        "address": req.address,
        "title": (req.title or spec.split(".")[0]).strip()[:80],
        "spec": spec,
        "fee_bps": req.fee_bps,
        "min_score": req.min_score,
        "partial_floor": req.partial_floor,
        "client_address": req.client_address,
        "worker_address": req.worker_address,
        "lifecycle_status": "UNFUNDED",
        "deployment_tx": req.deployment_tx,
        "created_at": utc_now(),
    })
    return {"job": record, "tx": req.deployment_tx, "transaction_type": "wallet-signed transaction", "signer_role": "connected Bradbury client wallet", "network": "testnet_bradbury"}


@app.post("/api/jobs")
def create_job(req: CreateJobRequest):
    _require_live_roles()
    spec = req.spec.strip()
    if len(spec) < 20:
        raise HTTPException(status_code=422, detail={"code": "INVALID_SPEC", "message": "Spec must be at least 20 characters"})
    if req.partial_floor > req.min_score:
        raise HTTPException(status_code=422, detail={"code": "INVALID_THRESHOLDS", "message": "partial_floor cannot exceed min_score"})
    try:
        tx = network_client.deploy_contract(
            ESCROW_CODE,
            account=demo_client_account,
            args=[
                spec,
                CalldataAddress(demo_worker_account.address),
                CalldataAddress(demo_client_account.address),
                req.fee_bps,
                req.min_score,
                req.partial_floor,
            ],
        )
        receipt = _wait(tx)
        address = _get_address(receipt)
        if not address:
            raise RuntimeError("Deployment receipt did not include a contract address")
    except Exception as exc:
        raise _action_error(exc)
    address = str(address)
    record = store.add_job({
        "id": address,
        "address": address,
        "title": (req.title or spec.split(".")[0]).strip()[:80],
        "spec": spec,
        "fee_bps": req.fee_bps,
        "min_score": req.min_score,
        "partial_floor": req.partial_floor,
        "client_address": str(demo_client_account.address),
        "worker_address": str(demo_worker_account.address),
        "lifecycle_status": "UNFUNDED",
        "deployment_tx": tx,
        "created_at": utc_now(),
    })
    return {
        "job": record,
        "tx": tx,
        "transaction_type": "server-signed demo transaction",
        "signer_role": "Bradbury demo client account",
    }


class FundRequest(BaseModel):
    # JSON strings preserve the exact integer produced by the browser's BigInt
    # conversion. Integer input remains accepted for older API clients.
    amount_wei: str | int = str(MIN_DEMO_AMOUNT_WEI)

    @field_validator("amount_wei")
    @classmethod
    def validate_amount_wei(cls, value: str | int) -> str:
        if isinstance(value, bool):
            raise ValueError("amount_wei must be a base-10 integer string")
        text = str(value).strip()
        if not text.isdigit():
            raise ValueError("amount_wei must be a base-10 integer string")
        return text


class SubmitRequest(BaseModel):
    url: str


def _run_action(job_id: str, method: str, role: str, args: list[Any] | None = None, value: int = 0) -> dict[str, Any]:
    job = _find_job(job_id)
    try:
        _preflight(job, method, role)
        tx = _call_write(job["address"], method, role, args=args, value=value)
        receipt = _wait(tx)
        state = _job_state(job["address"])
        chain_status = state["job"].get("status")
        store.update_job(job["address"], lifecycle_status=str(chain_status or "UNKNOWN"))
        return {
            "tx": tx,
            "status": receipt.get("status_name") or receipt.get("status"),
            "job_status": chain_status,
            "transaction_type": "server-signed demo transaction",
            "signer_role": f"Bradbury demo {role} account",
        }
    except Exception as exc:
        raise _action_error(exc)


@app.post("/api/jobs/{job_id}/fund")
def fund(job_id: str, req: FundRequest):
    amount_wei = int(req.amount_wei)
    if amount_wei < MIN_DEMO_AMOUNT_WEI:
        raise HTTPException(status_code=422, detail={
            "code": "BELOW_MINIMUM_DEMO_AMOUNT",
            "message": "Minimum demo deposit is 0.001 GEN.",
            "minimum_wei": str(MIN_DEMO_AMOUNT_WEI),
        })
    return _run_action(job_id, "fund", "client", value=amount_wei)


@app.post("/api/jobs/{job_id}/accept_terms")
def accept_terms(job_id: str):
    return _run_action(job_id, "accept_terms", "worker")


@app.post("/api/jobs/{job_id}/submit")
def submit_work(job_id: str, req: SubmitRequest):
    if not req.url.startswith("http"):
        raise HTTPException(status_code=422, detail={"code": "INVALID_URL", "message": "URL must start with http"})
    return _run_action(job_id, "submit_work", "worker", args=[req.url])


@app.post("/api/jobs/{job_id}/evaluate")
def evaluate(job_id: str):
    return _run_action(job_id, "evaluate", "client")


@app.post("/api/jobs/{job_id}/appeal")
def appeal(job_id: str):
    return _run_action(job_id, "appeal", "client")


@app.post("/api/jobs/{job_id}/finalize")
def finalize(job_id: str):
    job = _find_job(job_id)
    try:
        _preflight(job, "finalize", "client")
        tx = _call_write(job["address"], "finalize", "client")
        receipt = _wait(tx)
        state = _job_state(job["address"])
        contract_settlement = state["job"].get("settlement") or {}
        settlement = {
            **contract_settlement,
            "parent_transaction": tx,
            "parent_status": str(receipt.get("status_name") or receipt.get("status") or "ACCEPTED"),
            "transfer_status": "PENDING_FINALIZATION",
            "transfer_reference": [tx],
            "explorer": EXPLORER_TX + tx,
            "submitted_at": utc_now(),
        }
        store.update_job(job["address"], lifecycle_status="SETTLEMENT_PENDING", settlement=settlement)
        return {
            "tx": tx,
            "status": "PENDING_FINALIZATION",
            "settlement": settlement,
            "transaction_type": "server-signed demo transaction",
            "signer_role": "Bradbury demo client account",
            "notice": "Outcome decided; outbound EOA transfers are not complete until the parent transaction finalizes and its messages are inspectable.",
        }
    except Exception as exc:
        raise _action_error(exc)
