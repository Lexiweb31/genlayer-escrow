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
from contextlib import asynccontextmanager
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from pathlib import Path
from typing import Any, Literal, Optional

from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys.exceptions import BadSignature
from eth_utils.exceptions import ValidationError
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
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
from dashboard.telemetry import log_event


# ── Network and account configuration ─────────────────────────────────────────
EXPLORER = "https://explorer-bradbury.genlayer.com"
EXPLORER_ADDRESS = EXPLORER + "/address/"
EXPLORER_TX = EXPLORER + "/tx/"
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")
OWNERSHIP_PREFIX = "Merit needs-funding access"
OWNERSHIP_MAX_SECONDS = 15 * 60
_OWNERSHIP_MESSAGE_PATTERN = re.compile(
    r"^Merit needs-funding access\n"
    r"Address: (0x[0-9a-f]{40})\n"
    r"Network: testnet_bradbury\n"
    r"Expires: (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)$"
)

deployments_path = ROOT / "artifacts" / "deployments.json"
deployments = json.loads(deployments_path.read_text()) if deployments_path.exists() else {}
EVAL_ADDR = str(deployments.get("evaluate_submission") or "")
ESCROW_CODE = (ROOT / "contracts" / "freelance_escrow.py").read_text()
BOUNTY_CODE = (ROOT / "contracts" / "bounty_escrow.py").read_text()


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


def _configured_platform_address() -> Optional[str]:
    """Return the explicit public fee recipient, never a signer secret or fallback."""
    address = os.getenv("PLATFORM_FEE_ADDRESS", "").strip()
    if not ADDRESS_PATTERN.fullmatch(address) or int(address, 16) == 0:
        return None
    return address


def _demo_public_config() -> dict[str, Any]:
    platform_address = _configured_platform_address()
    return {
        "mode": "server-signed-demo" if DEMO_ROLES_READY else "simulated-walkthrough",
        "network": "testnet_bradbury",
        "live_actions_enabled": DEMO_ROLES_READY,
        "client_address": str(demo_client_account.address) if demo_client_account else None,
        "worker_address": str(demo_worker_account.address) if demo_worker_account else None,
        "platform_address": platform_address,
        "notice": (
            "Transactions are signed by separate Bradbury demo accounts on the server. "
            "No browser wallet is connected and visitors do not control deposited GEN."
            if DEMO_ROLES_READY
            else DEMO_CONFIG_ERROR
        ),
    }


class OwnedJobsRequest(BaseModel):
    address: str = ""
    message: str = ""
    signature: str = ""
    demo_mode: bool = False


def _ownership_message(address: str, expires_at: datetime) -> str:
    """Build the exact personal-sign message accepted for client recovery."""
    expires = expires_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return "\n".join([
        OWNERSHIP_PREFIX,
        f"Address: {address.lower()}",
        "Network: testnet_bradbury",
        f"Expires: {expires}",
    ])


def _parse_ownership_message(message: str) -> tuple[str, datetime]:
    match = _OWNERSHIP_MESSAGE_PATTERN.fullmatch(message)
    if not match:
        raise HTTPException(status_code=403, detail={
            "code": "OWNERSHIP_PROOF_EXPIRED",
            "message": "Sign a fresh Merit recovery message.",
        })
    try:
        expires_at = datetime.fromisoformat(match.group(2).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail={
            "code": "OWNERSHIP_PROOF_EXPIRED",
            "message": "Sign a fresh Merit recovery message.",
        }) from exc
    return match.group(1), expires_at


def _verify_owned_jobs_request(req: OwnedJobsRequest) -> str:
    if req.demo_mode:
        _require_live_roles()
        return str(demo_client_account.address).lower()
    if not ADDRESS_PATTERN.fullmatch(req.address):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_ROLE_ADDRESS",
            "message": "Invalid client address.",
        })
    address, expires_at = _parse_ownership_message(req.message)
    now = datetime.now(timezone.utc)
    if (
        address.lower() != req.address.lower()
        or expires_at <= now
        or expires_at > now + timedelta(seconds=OWNERSHIP_MAX_SECONDS)
    ):
        raise HTTPException(status_code=403, detail={
            "code": "OWNERSHIP_PROOF_EXPIRED",
            "message": "Sign a fresh Merit recovery message.",
        })
    try:
        recovered = Account.recover_message(encode_defunct(text=req.message), signature=req.signature)
    except (BadSignature, IndexError, TypeError, ValidationError, ValueError):
        raise HTTPException(status_code=403, detail={
            "code": "OWNERSHIP_PROOF_INVALID",
            "message": "The signature does not match this client wallet.",
        }) from None
    if recovered.lower() != req.address.lower():
        raise HTTPException(status_code=403, detail={
            "code": "OWNERSHIP_PROOF_INVALID",
            "message": "The signature does not match this client wallet.",
        })
    return recovered.lower()


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


class _TransactionIdentityError(ValueError):
    """A transaction could not be tied to the wallet operation that submitted it."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _verify_transaction_identity(
    tx_hash: str,
    expected_from: str,
    expected_to: str | None,
    expected_action: Literal["DEPLOYMENT", "FUND", "FINALIZE"],
) -> dict[str, Any]:
    """Read a Bradbury transaction and prove it belongs to this wallet action."""
    try:
        transaction = dict(network_client.get_transaction(tx_hash))
    except Exception as exc:
        raise _TransactionIdentityError("NOT_FOUND") from exc

    status = _status_name(transaction)
    execution = str(transaction.get("tx_execution_result_name") or "")
    failed_statuses = {
        "CANCELED",
        "UNDETERMINED",
        "VALIDATORS_TIMEOUT",
        "LEADER_TIMEOUT",
        "OUT_OF_FEE",
        "OUTOFFEE",
    }
    if status in failed_statuses or "ERROR" in execution.upper():
        raise _TransactionIdentityError("REJECTED")
    if status == "UNKNOWN":
        raise _TransactionIdentityError("NOT_READY")

    sender = str(
        transaction.get("sender")
        or transaction.get("from")
        or transaction.get("from_address")
        or ""
    )
    if not sender:
        raise _TransactionIdentityError("SIGNER_UNAVAILABLE")
    if sender.lower() != expected_from.lower():
        raise _TransactionIdentityError("SIGNER_MISMATCH")

    reported_network = str(
        transaction.get("network")
        or transaction.get("network_name")
        or transaction.get("chain")
        or ""
    )
    if reported_network and reported_network.replace("-", "_").lower() != "testnet_bradbury":
        raise _TransactionIdentityError("NETWORK_MISMATCH")

    if expected_to:
        decoded = transaction.get("tx_data_decoded")
        if not isinstance(decoded, dict):
            raise _TransactionIdentityError("ACTION_MISMATCH")
        created_contract = str(decoded.get("contract_address") or "")
        recipient = str(transaction.get("recipient") or "")
        if expected_to.lower() not in {created_contract.lower(), recipient.lower()}:
            raise _TransactionIdentityError("RECIPIENT_MISMATCH")
    else:
        decoded = transaction.get("tx_data_decoded")
        if not isinstance(decoded, dict):
            raise _TransactionIdentityError("ACTION_MISMATCH")

    if expected_action == "DEPLOYMENT":
        if decoded.get("type") != "deploy":
            raise _TransactionIdentityError("ACTION_MISMATCH")
    elif expected_action in {"FUND", "FINALIZE"} and (
        decoded.get("type") != "call"
        or not isinstance(decoded.get("call_data"), dict)
        or decoded["call_data"].get("method") != expected_action.lower()
    ):
        raise _TransactionIdentityError("ACTION_MISMATCH")
    return transaction


def _transaction_replayed(tx_hash: str, job_address: str, kind: str) -> bool:
    existing = store.get_transaction("testnet_bradbury", tx_hash)
    if existing is None:
        return False
    if (
        str(existing["job_address"]).lower() != job_address.lower()
        or str(existing["kind"]) != kind
    ):
        raise HTTPException(status_code=409, detail={
            "code": "TRANSACTION_IDENTITY_CONFLICT",
            "message": "This transaction hash is already associated with another wallet operation.",
        })
    return True


def _record_verified_transaction(
    tx_hash: str, transaction: dict[str, Any], job_address: str, kind: str
) -> None:
    try:
        store.record_transaction({
            "network": "testnet_bradbury",
            "tx_hash": tx_hash,
            "job_address": job_address,
            "kind": kind,
            "status": _status_name(transaction),
            "verified_at": utc_now(),
            "transaction": _json_safe(transaction),
        })
        log_event("registry_write", job=job_address, tx_hash=tx_hash, action="verified_transaction")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "TRANSACTION_IDENTITY_CONFLICT",
            "message": "This transaction hash is already associated with another wallet operation.",
        }) from exc


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


def _expected_state(method: str, job_type: str = "DIRECT_HIRE") -> str:
    if job_type == "BOUNTY":
        return {
            "fund": "UNFUNDED",
            "submit_work": "OPEN",
            "close_submissions": "OPEN",
            "evaluate": "CLOSED",
            "finalize": "EVALUATED",
        }[method]
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
    job_type = str(job.get("job_type") or chain_job.get("job_type") or "DIRECT_HIRE")
    expected_status = _expected_state(method, job_type)
    actual_status = str(chain_job.get("status") or "UNKNOWN")
    if actual_status != expected_status:
        raise HTTPException(status_code=409, detail={
            "code": "STALE_STATE",
            "message": f"Job is {actual_status}; {method} requires {expected_status}.",
            "expected_status": expected_status,
            "actual_status": actual_status,
        })
    signer = _role_address(role)
    if job_type == "BOUNTY" and method == "submit_work":
        if not signer or signer.lower() == str(chain_job.get("client") or "").lower():
            raise HTTPException(status_code=403, detail={
                "code": "WRONG_ROLE",
                "message": "A bounty submission must come from a wallet other than the client.",
            })
        return state
    expected_actor = str(chain_job.get(role) or "")
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
    log_event("bradbury_failure", error_code="ACTION_FAILED")
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
    # The contract is authoritative for outcome and transfer amounts. Stored
    # metadata contributes the parent transaction reference and timestamps,
    # but must never overwrite newer finalized contract state with the stale
    # zero-value snapshot captured when finalize() was first submitted.
    settlement = {**(meta.get("settlement") or {}), **contract_settlement}
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
        # Some Bradbury reads can continue returning the pre-finality contract
        # snapshot even after the finalized transaction has already delivered
        # its EOA messages. Those finalized messages are direct payment proof;
        # reconstruct typed transfer rows only when every recipient is one of
        # the immutable contract parties.
        if not nonzero_transfers and external_messages:
            role_addresses = {
                str(chain_job.get("worker") or "").lower(): "WORKER_PAYOUT",
                str(chain_job.get("client") or "").lower(): "CLIENT_REFUND",
                str(chain_job.get("platform") or "").lower(): "PLATFORM_FEE",
            }
            derived_transfers = [
                {
                    "recipient": message["recipient"],
                    "amount": message["amount"],
                    "settlement_type": role_addresses.get(str(message["recipient"]).lower()),
                }
                for message in external_messages
            ]
            if derived_transfers and all(transfer["settlement_type"] for transfer in derived_transfers):
                nonzero_transfers = derived_transfers
                settlement["transfers"] = derived_transfers
                has_worker = any(transfer["settlement_type"] == "WORKER_PAYOUT" for transfer in derived_transfers)
                has_client = any(transfer["settlement_type"] == "CLIENT_REFUND" for transfer in derived_transfers)
                settlement["outcome"] = "PARTIAL" if has_worker and has_client else "ACCEPTED" if has_worker else "REFUNDED"
                settlement["settlement_type"] = "PROPORTIONAL_SPLIT" if has_worker and has_client else "FULL_WORKER_PAYOUT" if has_worker else "FULL_CLIENT_REFUND"
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
        failed_statuses = {
            "CANCELED", "CANCELLED", "UNDETERMINED", "VALIDATORS_TIMEOUT",
            "LEADER_TIMEOUT", "FAILED", "REJECTED",
        }
        if parent_status in failed_statuses:
            settlement["transfer_status"] = "FAILED_FINALIZATION"
            settlement["status_error"] = f"Bradbury settlement transaction ended with {parent_status}."
        elif parent_status == "FINALIZED" and (triggered or confirmed_external):
            settlement["transfer_status"] = "FINALIZED"
            settlement["finalized_at"] = settlement.get("finalized_at") or utc_now()
        elif parent_status == "FINALIZED":
            settlement["transfer_status"] = "PENDING_TRANSFER_RECORD"
        else:
            settlement["transfer_status"] = "PENDING_FINALIZATION"
        store.update_job(meta["address"], settlement=settlement)
        log_event(
            "registry_write",
            job=meta["address"],
            action="settlement_verification",
            status=settlement.get("transfer_status"),
        )
        log_event(
            "settlement_verification",
            job=meta["address"],
            tx_hash=parent_tx,
            outcome=settlement.get("outcome"),
            status=settlement.get("transfer_status"),
        )
    except Exception as exc:
        settlement["transfer_status"] = settlement.get("transfer_status") or "PENDING_FINALIZATION"
        settlement["status_error"] = str(exc)
        log_event(
            "settlement_verification_failure",
            job=meta["address"],
            tx_hash=parent_tx,
            error_code="VERIFICATION_FAILED",
        )
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
@asynccontextmanager
async def lifespan(_: FastAPI):
    start_marketplace_reconciliation()
    try:
        yield
    finally:
        stop_marketplace_reconciliation()


app = FastAPI(title="Merit Escrow Marketplace", lifespan=lifespan)
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


@app.middleware("http")
async def log_request_latency(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        log_event(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
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
        "release": os.getenv("MERIT_RELEASE", "unknown"),
        "registry": "sqlite",
        "reconciler": _reconciler_health(),
        "oldest_pending_seconds": _oldest_pending_seconds(),
        "last_reconcile_at": _last_reconcile_at,
    }


@app.get("/api/demo-mode")
def demo_mode():
    return _demo_public_config()


MIN_DEMO_AMOUNT_WEI = 10**15  # 0.001 GEN
_ACTIVE_STATUSES = {"UNFUNDED", "OPEN", "CLOSED", "AGREED", "SUBMITTED", "EVALUATED", "SETTLEMENT_PENDING"}
_LOCKED_STATUSES = {"OPEN", "CLOSED", "AGREED", "SUBMITTED", "EVALUATED"}
_EVALUATED_STATUSES = {"EVALUATED", "SETTLEMENT_PENDING", "ACCEPTED", "PARTIAL", "REFUNDED"}
_FINAL_STATUSES = {"ACCEPTED", "PARTIAL", "REFUNDED"}
_MARKETPLACE_REFRESH_LOCK = Lock()
_marketplace_last_refresh = 0.0
_RECONCILE_STOP = Event()
_reconcile_thread: Thread | None = None
_last_reconcile_at: str | None = None


def _reconciliation_error_code(exc: Exception) -> str:
    """Return a stable public category without persisting SDK diagnostics."""
    message = str(exc).lower()
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)) or any(
        term in message for term in ("network", "connection", "timeout", "temporarily unavailable")
    ):
        return "TESTNET_UNAVAILABLE"
    if "rate limit" in message or "too many requests" in message or "429" in message:
        return "TESTNET_RATE_LIMITED"
    if "not found" in message or "404" in message:
        return "TESTNET_NOT_FOUND"
    return "TESTNET_READ_FAILED"


def _reconcile_backoff_seconds() -> int:
    try:
        return min(300, max(10, int(os.getenv("MARKETPLACE_RECONCILE_BACKOFF_SECONDS", "30"))))
    except ValueError:
        return 30


def _is_verified_final_snapshot(record: dict[str, Any]) -> bool:
    snapshot = record.get("state_snapshot") or {}
    settlement = snapshot.get("settlement") or record.get("settlement") or {}
    status = snapshot.get("status") or record.get("lifecycle_status")
    return status in _FINAL_STATUSES and settlement.get("transfer_status") == "FINALIZED"


def _is_reconcile_backing_off(record: dict[str, Any]) -> bool:
    return (
        record.get("reconcile_state") == "BACKING_OFF"
        and isinstance(record.get("reconcile_age_seconds"), int)
        and record["reconcile_age_seconds"] < _reconcile_backoff_seconds()
    )


def _oldest_pending_seconds() -> int | None:
    created_at = store.oldest_pending_transaction_created_at()
    if not created_at:
        return None
    try:
        started = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    except (KeyError, TypeError, ValueError):
        return None


def _reconciler_health() -> str:
    if os.getenv("MARKETPLACE_RECONCILE_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return "disabled"
    return "running" if _reconcile_thread and _reconcile_thread.is_alive() else "stopped"


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


def _job_stats(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate marketplace statistics from precisely the jobs being served."""
    return _marketplace_stats(
        jobs,
        total_jobs=len(jobs),
        degraded_jobs=sum(1 for job in jobs if job.get("_missing_state_snapshot")),
        legacy_jobs=sum(1 for job in jobs if job.get("status") == "LEGACY_UNSAFE"),
    )


@app.get("/api/stats")
def stats():
    return _public_jobs_snapshot()["stats"]


def _refresh_marketplace_snapshots(records: list[dict[str, Any]]) -> None:
    global _marketplace_last_refresh
    if not _MARKETPLACE_REFRESH_LOCK.acquire(blocking=False):
        return
    try:
        live_records = [
            record
            for record in records
            if not record.get("legacy_contract")
            and not _is_verified_final_snapshot(record)
            and not _is_reconcile_backing_off(record)
        ]
        worker_count = min(max(1, int(os.getenv("MARKETPLACE_READ_WORKERS", "6"))), max(1, len(live_records)))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="marketplace-read") as executor:
            state_futures: dict[str, Future[dict[str, Any]]] = {
                record["address"].lower(): executor.submit(_job_state, record["address"])
                for record in live_records
            }
            for meta in live_records:
                try:
                    public = _public_state(meta, state_futures[meta["address"].lower()].result())
                    snapshot = {
                        "status": public["job"].get("status"),
                        "amount": public["job"].get("amount"),
                        "score": public["result"].get("score"),
                        "settlement": public["job"].get("settlement") or {},
                        "job": public["job"],
                        "result": public["result"],
                    }
                    store.update_job(
                        meta["address"],
                        lifecycle_status=str(snapshot["status"] or "UNKNOWN"),
                        settlement=snapshot["settlement"],
                        state_snapshot=snapshot,
                        reconcile_state="CURRENT",
                        reconcile_attempted_at=utc_now(),
                        reconcile_error_code="",
                    )
                    log_event(
                        "registry_write",
                        job=meta["address"],
                        action="reconciliation",
                        status="CURRENT",
                    )
                    log_event("reconciliation_succeeded", job=meta["address"], status=snapshot["status"])
                except Exception as exc:
                    # Preserve the last known-good snapshot when Bradbury has a
                    # transient read failure. The durable backoff timestamp
                    # prevents request-driven refreshes from retrying in a loop
                    # after a process restart.
                    store.update_job(
                        meta["address"],
                        reconcile_state="BACKING_OFF",
                        reconcile_attempted_at=utc_now(),
                        reconcile_error_code=_reconciliation_error_code(exc),
                    )
                    error_code = _reconciliation_error_code(exc)
                    log_event(
                        "registry_write",
                        job=meta["address"],
                        action="reconciliation",
                        status="BACKING_OFF",
                    )
                    log_event("reconciliation_failure", job=meta["address"], error_code=error_code)
                    continue
        _marketplace_last_refresh = time.monotonic()
    finally:
        _MARKETPLACE_REFRESH_LOCK.release()


def _reconcile_once() -> None:
    """Persist current contract state without requiring an open browser."""
    global _last_reconcile_at
    try:
        _refresh_marketplace_snapshots(store.list_jobs())
        log_event("reconciliation_completed", outcome="completed")
    except Exception:
        log_event("reconciliation_failure", error_code="RECONCILE_FAILED")
        raise
    finally:
        _last_reconcile_at = utc_now()


def _reconcile_loop(stop: Event, interval_seconds: int) -> None:
    # Reconcile immediately on service start, then at a bounded interval. The
    # non-blocking marketplace lock prevents overlap with request-triggered
    # refreshes or another reconciliation pass.
    while not stop.is_set():
        try:
            _reconcile_once()
        except Exception:
            # A transient Bradbury failure must not terminate future recovery.
            pass
        stop.wait(interval_seconds)


def start_marketplace_reconciliation() -> None:
    global _reconcile_thread
    if os.getenv("MARKETPLACE_RECONCILE_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        return
    if _reconcile_thread and _reconcile_thread.is_alive():
        return
    try:
        interval = max(10, int(os.getenv("MARKETPLACE_RECONCILE_SECONDS", "30")))
    except ValueError:
        interval = 30
    _RECONCILE_STOP.clear()
    _reconcile_thread = Thread(
        target=_reconcile_loop,
        args=(_RECONCILE_STOP, interval),
        name="merit-chain-reconciler",
        daemon=True,
    )
    _reconcile_thread.start()


def stop_marketplace_reconciliation() -> None:
    _RECONCILE_STOP.set()
    if _reconcile_thread and _reconcile_thread.is_alive():
        _reconcile_thread.join(timeout=2)


def _list_jobs_snapshot() -> dict[str, Any]:
    output: list[dict[str, Any]] = []
    records = store.list_jobs()
    degraded = 0
    for meta in records:
        entry = dict(meta)
        snapshot = entry.pop("state_snapshot", {}) or {}
        if meta.get("legacy_contract"):
            entry.update({
                "status": "LEGACY_UNSAFE",
                "legacy_warning": "Legacy settlement contract — do not fund",
            })
        else:
            entry["status"] = snapshot.get("status") or meta.get("lifecycle_status") or "UNKNOWN"
            entry["amount"] = snapshot.get("amount")
            entry["evaluation_complete"] = entry["status"] in _EVALUATED_STATUSES
            entry["score"] = snapshot.get("score") if entry["evaluation_complete"] else None
            entry["settlement"] = snapshot.get("settlement") or meta.get("settlement") or {}
            entry["stale"] = bool(meta.get("reconcile_error_code"))
            entry["_missing_state_snapshot"] = not bool(snapshot)
            if not snapshot:
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


def _public_jobs_snapshot() -> dict[str, Any]:
    snapshot = _list_jobs_snapshot()
    jobs = [job for job in snapshot["jobs"] if job.get("status") != "UNFUNDED"]
    return {
        **snapshot,
        "jobs": [{key: value for key, value in job.items() if key != "_missing_state_snapshot"} for job in jobs],
        "stats": _job_stats(jobs),
    }


@app.get("/api/jobs")
def list_jobs(background_tasks: BackgroundTasks):
    response = _public_jobs_snapshot()
    if time.monotonic() - _marketplace_last_refresh > 15:
        background_tasks.add_task(_refresh_marketplace_snapshots, store.list_jobs())
    return response


@app.post("/api/jobs/owned")
def owned_jobs(req: OwnedJobsRequest) -> dict[str, Any]:
    proven_client = _verify_owned_jobs_request(req)
    jobs = [
        job
        for job in _list_jobs_snapshot()["jobs"]
        if job.get("status") == "UNFUNDED"
        and str(job.get("client_address", "")).lower() == proven_client
    ]
    return {
        "jobs": [
            {key: value for key, value in job.items() if key != "_missing_state_snapshot"}
            for job in jobs
        ]
    }


def _job_detail_payload(
    meta: dict[str, Any], job: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    funding_transaction = store.latest_transaction_for_job(meta["address"], "FUNDING")
    return {
        "meta": meta,
        "job": job,
        "result": result,
        "funding_transaction": _funding_transaction_for_wire(funding_transaction),
        "addresses": _addresses(meta["address"]),
        "demo": _demo_public_config(),
    }


def _funding_transaction_for_wire(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    network_status = str(record.get("status") or "UNKNOWN").upper()
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    transaction = payload.get("transaction") if isinstance(payload.get("transaction"), dict) else payload
    execution_result = str(
        transaction.get("tx_execution_result_name")
        or transaction.get("execution_result")
        or "UNKNOWN"
    ).upper()
    failed = store.funding_transaction_failed(record)
    return {
        **record,
        "status": "FAILED" if failed else network_status,
        "network_status": network_status,
        "execution_result": execution_result,
        "failed": failed,
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    meta = _find_job(job_id)
    snapshot = meta.get("state_snapshot") or {}
    cached_job = snapshot.get("job")
    cached_result = snapshot.get("result")
    cached_settlement = cached_job.get("settlement") if isinstance(cached_job, dict) else {}
    # A finalized escrow is immutable. Serving its last verified full snapshot
    # avoids multiple slow Bradbury reads while preserving the exact confirmed
    # transaction evidence. Older registry rows without a full snapshot fall
    # through to the live read once and are upgraded below.
    if (
        isinstance(cached_job, dict)
        and isinstance(cached_result, dict)
        and cached_job.get("status") in _FINAL_STATUSES
        and isinstance(cached_settlement, dict)
        and cached_settlement.get("transfer_status") == "FINALIZED"
    ):
        return _job_detail_payload(meta, cached_job, cached_result)
    if _is_reconcile_backing_off(meta) and isinstance(cached_job, dict) and isinstance(cached_result, dict):
        return _job_detail_payload(
            {**meta, "stale": True}, {**cached_job, "stale": True}, cached_result
        )
    try:
        public = _public_state(meta, _job_state(meta["address"]))
        live_status = str(public["job"].get("status") or "UNKNOWN")
        updated_meta = store.update_job(
            meta["address"],
            lifecycle_status=live_status,
            settlement=public["job"].get("settlement") or {},
            state_snapshot={
                "status": live_status,
                "amount": public["job"].get("amount"),
                "score": public["result"].get("score"),
                "settlement": public["job"].get("settlement") or {},
                "job": public["job"],
                "result": public["result"],
            },
            reconcile_state="CURRENT",
            reconcile_attempted_at=utc_now(),
            reconcile_error_code="",
        )
        log_event("registry_write", job=meta["address"], action="job_detail_refresh", status="CURRENT")
        return _job_detail_payload(updated_meta, public["job"], public["result"])
    except Exception as exc:
        updated_meta = meta
        if not meta.get("legacy_contract"):
            try:
                updated_meta = store.update_job(
                    meta["address"],
                    reconcile_state="BACKING_OFF",
                    reconcile_attempted_at=utc_now(),
                    reconcile_error_code=_reconciliation_error_code(exc),
                )
                log_event(
                    "registry_write",
                    job=meta["address"],
                    action="job_detail_refresh",
                    status="BACKING_OFF",
                )
                log_event(
                    "bradbury_failure",
                    job=meta["address"],
                    error_code=_reconciliation_error_code(exc),
                )
            except Exception:
                pass
        if isinstance(cached_job, dict) and isinstance(cached_result, dict):
            stale_meta = {**updated_meta, "stale": True}
            return _job_detail_payload(
                stale_meta, {**cached_job, "stale": True}, cached_result
            )
        if meta.get("legacy_contract"):
            return _job_detail_payload(
                {**meta, "legacy_warning": "Legacy settlement contract — do not fund"},
                {
                    "status": "LEGACY_UNSAFE",
                    "legacy_contract": True,
                    "legacy_warning": "Legacy settlement contract — do not fund",
                },
                {"status": "LEGACY_UNSAFE"},
            )
        raise HTTPException(status_code=502, detail={
            "code": _reconciliation_error_code(exc),
            "message": "Bradbury job state could not be read.",
        })


# ── Create and action routes ──────────────────────────────────────────────────
class CreateJobRequest(BaseModel):
    spec: str
    title: Optional[str] = None
    fee_bps: int = Field(default=200, ge=0, le=1000)
    min_score: int = Field(default=70, ge=0, le=100)
    partial_floor: int = Field(default=40, ge=0, le=100)
    job_type: Literal["DIRECT_HIRE", "BOUNTY"] = "DIRECT_HIRE"
    max_submissions: int = Field(default=5, ge=2, le=5)


class RegisterWalletJobRequest(CreateJobRequest):
    address: str
    client_address: str
    worker_address: Optional[str] = None
    deployment_tx: str


class RegisterWalletSettlementRequest(BaseModel):
    transaction_hash: str


class RegisterWalletFundingRequest(BaseModel):
    transaction_hash: str


@app.post("/api/jobs/register")
def register_wallet_job(req: RegisterWalletJobRequest):
    if not ADDRESS_PATTERN.fullmatch(req.address):
        raise HTTPException(status_code=422, detail={"code": "INVALID_CONTRACT_ADDRESS", "message": "Invalid escrow contract address."})
    if not ADDRESS_PATTERN.fullmatch(req.client_address):
        raise HTTPException(status_code=422, detail={"code": "INVALID_ROLE_ADDRESS", "message": "Invalid client address."})
    if req.job_type == "DIRECT_HIRE":
        if not req.worker_address or not ADDRESS_PATTERN.fullmatch(req.worker_address):
            raise HTTPException(status_code=422, detail={"code": "INVALID_ROLE_ADDRESS", "message": "Invalid worker address."})
        if req.client_address.lower() == req.worker_address.lower():
            raise HTTPException(status_code=422, detail={"code": "SAME_ROLE_ADDRESS", "message": "Client and worker must use different wallets."})
    if not TX_PATTERN.fullmatch(req.deployment_tx):
        raise HTTPException(status_code=422, detail={"code": "INVALID_DEPLOYMENT_TX", "message": "Invalid deployment transaction hash."})
    if req.job_type == "DIRECT_HIRE" and req.partial_floor > req.min_score:
        raise HTTPException(status_code=422, detail={"code": "INVALID_THRESHOLDS", "message": "partial_floor cannot exceed min_score"})
    spec = req.spec.strip()
    if len(spec) < 20:
        raise HTTPException(status_code=422, detail={"code": "INVALID_SPEC", "message": "Spec must be at least 20 characters"})

    platform_address = _configured_platform_address()
    if platform_address is None:
        raise HTTPException(status_code=503, detail={
            "code": "PLATFORM_FEE_ADDRESS_UNAVAILABLE",
            "message": "Wallet-created escrows are unavailable until a valid public Bradbury fee recipient is configured.",
        })

    replayed = _transaction_replayed(req.deployment_tx, req.address, "DEPLOYMENT")
    try:
        deployment = _verify_transaction_identity(
            req.deployment_tx, req.client_address, req.address, "DEPLOYMENT"
        )
    except _TransactionIdentityError as exc:
        if exc.code == "NOT_FOUND":
            raise HTTPException(status_code=422, detail={
                "code": "DEPLOYMENT_TX_NOT_FOUND",
                "message": "The deployment transaction could not be verified on Bradbury.",
            }) from exc
        if exc.code in {"REJECTED", "NOT_READY"}:
            raise HTTPException(status_code=422, detail={
                "code": "DEPLOYMENT_TX_REJECTED",
                "message": "The deployment transaction has not completed successfully on Bradbury.",
            }) from exc
        if exc.code == "RECIPIENT_MISMATCH":
            raise HTTPException(status_code=422, detail={
                "code": "DEPLOYMENT_ADDRESS_MISMATCH",
                "message": "The deployment transaction did not create the submitted escrow address.",
            }) from exc
        if exc.code == "ACTION_MISMATCH":
            raise HTTPException(status_code=422, detail={
                "code": "DEPLOYMENT_ACTION_MISMATCH",
                "message": "The submitted transaction is not an escrow deployment.",
            }) from exc
        raise HTTPException(status_code=422, detail={
            "code": "DEPLOYMENT_TRANSACTION_IDENTITY_MISMATCH",
            "message": "The deployment transaction does not match the connected client wallet or Bradbury network.",
        }) from exc

    deployment_status = _status_name(deployment)
    deployment_execution = str(deployment.get("tx_execution_result_name") or "")
    deployed_address = str((deployment.get("tx_data_decoded") or {}).get("contract_address") or "")
    if deployment_status not in {"ACCEPTED", "FINALIZED"} or "ERROR" in deployment_execution.upper():
        raise HTTPException(status_code=422, detail={
            "code": "DEPLOYMENT_TX_REJECTED",
            "message": "The deployment transaction has not completed successfully on Bradbury.",
        })
    if not deployed_address or deployed_address.lower() != req.address.lower():
        raise HTTPException(status_code=422, detail={
            "code": "DEPLOYMENT_ADDRESS_MISMATCH",
            "message": "The deployment transaction did not create the submitted escrow address.",
        })

    try:
        state = _job_state(req.address)["job"]
    except Exception:
        raise HTTPException(status_code=422, detail={
            "code": "CONTRACT_NOT_READABLE", "message": "The deployed escrow could not be verified on Bradbury."
        })
    expected = {
        "client": req.client_address,
        "platform": platform_address,
        "spec": spec,
        "fee_bps": req.fee_bps,
        "min_score": req.min_score,
        "status": "UNFUNDED",
    }
    if req.job_type == "DIRECT_HIRE":
        expected.update({"worker": req.worker_address, "partial_floor": req.partial_floor})
    else:
        expected.update({"job_type": "BOUNTY", "max_submissions": req.max_submissions})
    for key, value in expected.items():
        actual = state.get(key)
        if key in ("client", "worker", "platform"):
            matches = str(actual).lower() == str(value).lower()
        else:
            matches = actual == value
        if not matches:
            raise HTTPException(status_code=422, detail={"code": "CONTRACT_METADATA_MISMATCH", "message": "The deployed contract does not match the submitted job details."})

    _record_verified_transaction(req.deployment_tx, deployment, req.address, "DEPLOYMENT")
    existing = store.get_job(req.address)
    if existing:
        response = {"job": existing, "tx": req.deployment_tx, "transaction_type": "wallet-signed transaction", "signer_role": "connected Bradbury client wallet", "network": "testnet_bradbury"}
        if replayed:
            response["replayed"] = True
        return response
    record = store.add_job({
        "id": req.address,
        "address": req.address,
        "title": (req.title or spec.split(".")[0]).strip()[:80],
        "spec": spec,
        "fee_bps": req.fee_bps,
        "min_score": req.min_score,
        "partial_floor": req.partial_floor,
        "job_type": req.job_type,
        "max_submissions": req.max_submissions if req.job_type == "BOUNTY" else 0,
        "client_address": req.client_address,
        "worker_address": req.worker_address or "",
        "lifecycle_status": "UNFUNDED",
        "deployment_tx": req.deployment_tx,
        "created_at": utc_now(),
    }, ignore_existing=True)
    log_event("registry_write", job=record["address"], tx_hash=req.deployment_tx, action="register_job")
    response = {"job": record, "tx": req.deployment_tx, "transaction_type": "wallet-signed transaction", "signer_role": "connected Bradbury client wallet", "network": "testnet_bradbury"}
    if replayed:
        response["replayed"] = True
    return response


@app.post("/api/jobs")
def create_job(req: CreateJobRequest):
    _require_live_roles()
    spec = req.spec.strip()
    if len(spec) < 20:
        raise HTTPException(status_code=422, detail={"code": "INVALID_SPEC", "message": "Spec must be at least 20 characters"})
    if req.job_type == "DIRECT_HIRE" and req.partial_floor > req.min_score:
        raise HTTPException(status_code=422, detail={"code": "INVALID_THRESHOLDS", "message": "partial_floor cannot exceed min_score"})
    try:
        if req.job_type == "BOUNTY":
            tx = network_client.deploy_contract(
                BOUNTY_CODE,
                account=demo_client_account,
                args=[
                    spec,
                    CalldataAddress(demo_client_account.address),
                    req.fee_bps,
                    req.min_score,
                    req.max_submissions,
                ],
            )
        else:
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
        "job_type": req.job_type,
        "max_submissions": req.max_submissions if req.job_type == "BOUNTY" else 0,
        "client_address": str(demo_client_account.address),
        "worker_address": "" if req.job_type == "BOUNTY" else str(demo_worker_account.address),
        "lifecycle_status": "UNFUNDED",
        "deployment_tx": tx,
        "created_at": utc_now(),
    })
    log_event("registry_write", job=record["address"], tx_hash=tx, action="create_job")
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


def _reconcile_demo_funding(record: dict[str, Any]) -> dict[str, Any]:
    """Refresh a durable demo-funding hash before deciding whether retry is safe."""
    if store.funding_transaction_failed(record):
        return record
    try:
        transaction = dict(network_client.get_transaction(record["tx_hash"]))
    except Exception:
        # An unavailable receipt is not proof of failure. Keep suppressing a
        # duplicate until Bradbury returns authoritative transaction evidence.
        return record

    network_status = _status_name(transaction)
    status = "FAILED" if network_status in {"OUT_OF_FEE", "OUTOFFEE"} else network_status
    try:
        refreshed = store.record_transaction({
            "network": record["network"],
            "tx_hash": record["tx_hash"],
            "job_address": record["job_address"],
            "kind": record["kind"],
            "status": status,
            "network_status": network_status,
            "transaction": _json_safe(transaction),
        })
    except ValueError:
        # Unknown/intermediate SDK statuses are not terminal evidence. Retain
        # the prior durable row and continue treating the hash as in flight.
        return record
    log_event(
        "registry_write",
        job=record["job_address"],
        tx_hash=record["tx_hash"],
        action="reconcile_funding",
        status=status,
    )
    return refreshed


def _run_action(
    job_id: str,
    method: str,
    role: str,
    args: list[Any] | None = None,
    value: int = 0,
    *,
    funding_reserved: bool = False,
) -> dict[str, Any]:
    job = _find_job(job_id)
    tx: str | None = None
    try:
        _preflight(job, method, role)
        tx = _call_write(job["address"], method, role, args=args, value=value)
        if method == "fund" and funding_reserved:
            store.record_transaction({
                "network": "testnet_bradbury",
                "tx_hash": tx,
                "job_address": job["address"],
                "kind": "FUNDING",
                "status": "SUBMITTED",
                "method": method,
            })
            store.release_funding_reservation(job["address"])
        receipt = _wait(tx)
        if method == "fund":
            _record_verified_transaction(tx, receipt, job["address"], "FUNDING")
        state = _job_state(job["address"])
        chain_status = state["job"].get("status")
        store.update_job(job["address"], lifecycle_status=str(chain_status or "UNKNOWN"))
        log_event(
            "registry_write",
            job=job["address"],
            tx_hash=tx,
            action=method,
            status=chain_status,
        )
        return {
            "tx": tx,
            "status": receipt.get("status_name") or receipt.get("status"),
            "job_status": chain_status,
            "transaction_type": "server-signed demo transaction",
            "signer_role": f"Bradbury demo {role} account",
        }
    except Exception as exc:
        if method == "fund" and funding_reserved and tx is None:
            store.release_funding_reservation(job["address"])
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
    job = _find_job(job_id)
    latest_funding = store.latest_transaction_for_job(job["address"], "FUNDING")
    if latest_funding:
        latest_funding = _reconcile_demo_funding(latest_funding)
    live_status = str(_job_state(job["address"])["job"].get("status") or "UNKNOWN")
    if live_status != "UNFUNDED":
        raise HTTPException(status_code=409, detail={
            "code": "FUNDING_STATE_UNVERIFIED" if live_status == "UNKNOWN" else "STALE_STATE",
            "message": "Funding requires an authoritative UNFUNDED escrow state.",
            "action": "Refresh the Bradbury state before retrying.",
        })
    if latest_funding and not store.funding_transaction_failed(latest_funding):
        raise HTTPException(status_code=409, detail={
            "code": "FUNDING_ALREADY_PENDING",
            "message": "A submitted funding transaction is still reconciling for this escrow.",
            "action": "Wait for Bradbury confirmation or inspect the existing transaction before retrying.",
        })
    if not store.reserve_funding(job["address"]):
        raise HTTPException(status_code=409, detail={
            "code": "FUNDING_ALREADY_PENDING",
            "message": "Another funding request already reserved this escrow.",
            "action": "Wait for the existing funding attempt before retrying.",
        })
    return _run_action(
        job_id, "fund", "client", value=amount_wei, funding_reserved=True
    )


@app.post("/api/jobs/{job_id}/accept_terms")
def accept_terms(job_id: str):
    return _run_action(job_id, "accept_terms", "worker")


@app.post("/api/jobs/{job_id}/submit")
def submit_work(job_id: str, req: SubmitRequest):
    if not req.url.startswith("http"):
        raise HTTPException(status_code=422, detail={"code": "INVALID_URL", "message": "URL must start with http"})
    return _run_action(job_id, "submit_work", "worker", args=[req.url])


@app.post("/api/jobs/{job_id}/close_submissions")
def close_submissions(job_id: str):
    job = _find_job(job_id)
    if str(job.get("job_type") or "DIRECT_HIRE") != "BOUNTY":
        raise HTTPException(status_code=409, detail={
            "code": "NOT_A_BOUNTY",
            "message": "Only Bounty jobs have an open submission round.",
        })
    return _run_action(job_id, "close_submissions", "client")


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
        log_event(
            "registry_write",
            job=job["address"],
            tx_hash=tx,
            action="finalize",
            status="SETTLEMENT_PENDING",
        )
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


@app.post("/api/jobs/{job_id}/register_funding")
def register_wallet_funding(job_id: str, req: RegisterWalletFundingRequest):
    """Persist a wallet-signed funding call and reconcile its contract state."""
    job = _find_job(job_id)
    _require_safe_job(job)
    tx_hash = req.transaction_hash.strip()
    if not TX_PATTERN.fullmatch(tx_hash):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_FUNDING_TX",
            "message": "Invalid funding transaction hash.",
        })
    replayed = _transaction_replayed(tx_hash, job["address"], "FUNDING")
    try:
        transaction = _verify_transaction_identity(
            tx_hash, str(job["client_address"]), str(job["address"]), "FUND"
        )
    except _TransactionIdentityError as exc:
        codes = {
            "NOT_FOUND": ("FUNDING_TX_NOT_FOUND", "The funding transaction could not be verified on Bradbury."),
            "NOT_READY": ("FUNDING_TX_NOT_READY", "Bradbury has not indexed the funding transaction yet."),
            "REJECTED": ("FUNDING_TX_REJECTED", "The funding transaction failed on Bradbury."),
            "RECIPIENT_MISMATCH": ("FUNDING_CONTRACT_MISMATCH", "This funding transaction does not belong to the selected escrow."),
            "ACTION_MISMATCH": ("FUNDING_ACTION_MISMATCH", "The transaction is not an escrow fund call."),
            "SIGNER_UNAVAILABLE": ("FUNDING_SIGNER_UNAVAILABLE", "Bradbury did not return the wallet signer for this funding transaction."),
            "SIGNER_MISMATCH": ("FUNDING_SIGNER_MISMATCH", "Only the assigned client wallet can register this funding transaction."),
            "NETWORK_MISMATCH": ("FUNDING_NETWORK_MISMATCH", "The funding transaction is not on Bradbury."),
        }
        code, message = codes.get(exc.code, (
            "FUNDING_TRANSACTION_IDENTITY_MISMATCH",
            "The funding transaction identity could not be verified.",
        ))
        raise HTTPException(status_code=422, detail={"code": code, "message": message}) from exc

    status = _status_name(transaction)
    execution = str(transaction.get("tx_execution_result_name") or "").upper()
    result = str(transaction.get("result_name") or transaction.get("result") or "").upper()
    successful_execution = execution == "SUCCESS" or execution.endswith("FINISHED_WITH_RETURN")
    if status not in {"ACCEPTED", "FINALIZED"} or not successful_execution or "FAIL" in result:
        raise HTTPException(status_code=422, detail={
            "code": "FUNDING_TX_REJECTED",
            "message": "The funding transaction has not completed successfully on Bradbury.",
        })
    if str(transaction.get("recipient") or "").lower() != str(job["address"]).lower():
        raise HTTPException(status_code=422, detail={
            "code": "FUNDING_CONTRACT_MISMATCH",
            "message": "This funding transaction does not belong to the selected escrow.",
        })

    _record_verified_transaction(tx_hash, transaction, job["address"], "FUNDING")
    state = _job_state(job["address"])
    chain_job = state["job"]
    chain_status = str(chain_job.get("status") or "UNKNOWN")
    store.update_job(
        job["address"],
        lifecycle_status=chain_status,
        state_snapshot={
            "status": chain_status,
            "amount": chain_job.get("amount"),
            "job": chain_job,
            "result": state.get("result") or {"status": chain_status},
        },
    )
    log_event(
        "registry_write",
        job=job["address"],
        tx_hash=tx_hash,
        action="register_funding",
        status=chain_status,
    )
    response = {
        "tx": tx_hash,
        "status": status,
        "job_status": chain_status,
        "transaction_type": "wallet-signed transaction",
        "signer_role": "connected Bradbury client wallet",
        "network": "testnet_bradbury",
    }
    if replayed:
        response["replayed"] = True
    return response


@app.post("/api/jobs/{job_id}/register_settlement")
def register_wallet_settlement(job_id: str, req: RegisterWalletSettlementRequest):
    """Attach a wallet-signed finalize transaction to its verified escrow.

    Wallet Mode signs in the browser, so the backend cannot infer the parent
    transaction hash from contract storage. Persisting the verified hash lets
    later requests finish settlement checks without keeping the browser open.
    """
    job = _find_job(job_id)
    _require_safe_job(job)
    tx_hash = req.transaction_hash.strip()
    if not TX_PATTERN.fullmatch(tx_hash):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_SETTLEMENT_TX",
            "message": "Invalid settlement transaction hash.",
        })
    replayed = _transaction_replayed(tx_hash, job["address"], "SETTLEMENT")
    try:
        transaction = _verify_transaction_identity(
            tx_hash, str(job["client_address"]), str(job["address"]), "FINALIZE"
        )
    except _TransactionIdentityError as exc:
        if exc.code == "NOT_FOUND":
            raise HTTPException(status_code=422, detail={
                "code": "SETTLEMENT_TX_NOT_FOUND",
                "message": "The settlement transaction could not be verified on Bradbury.",
            }) from exc
        if exc.code == "REJECTED":
            raise HTTPException(status_code=422, detail={
                "code": "SETTLEMENT_TX_REJECTED",
                "message": "The settlement transaction failed on Bradbury.",
            }) from exc
        if exc.code == "NOT_READY":
            raise HTTPException(status_code=422, detail={
                "code": "SETTLEMENT_TX_NOT_READY",
                "message": "Bradbury has not indexed the settlement transaction yet. Merit will retry it from this browser.",
            }) from exc
        if exc.code == "RECIPIENT_MISMATCH":
            raise HTTPException(status_code=422, detail={
                "code": "SETTLEMENT_CONTRACT_MISMATCH",
                "message": "This transaction does not belong to the selected escrow.",
            }) from exc
        if exc.code == "ACTION_MISMATCH":
            raise HTTPException(status_code=422, detail={
                "code": "SETTLEMENT_ACTION_MISMATCH",
                "message": "The settlement transaction is not an escrow finalize call.",
            }) from exc
        if exc.code == "SIGNER_UNAVAILABLE":
            raise HTTPException(status_code=422, detail={
                "code": "SETTLEMENT_SIGNER_UNAVAILABLE",
                "message": "Bradbury did not return the wallet signer for this settlement transaction.",
            }) from exc
        if exc.code == "SIGNER_MISMATCH":
            raise HTTPException(status_code=422, detail={
                "code": "SETTLEMENT_SIGNER_MISMATCH",
                "message": "Only the assigned client wallet can register this settlement transaction.",
            }) from exc
        raise HTTPException(status_code=422, detail={
            "code": "SETTLEMENT_TRANSACTION_IDENTITY_MISMATCH",
            "message": "The settlement transaction does not match the Bradbury network.",
        }) from exc

    status = _status_name(transaction)
    recipient = str(transaction.get("recipient") or "")
    # Wallet Mode reports the hash as soon as the browser broadcasts it. Save
    # that reference while Bradbury is still processing so a refresh, closed
    # tab, or short API timing race cannot orphan an otherwise valid refund.
    if recipient.lower() != str(job["address"]).lower():
        raise HTTPException(status_code=422, detail={
            "code": "SETTLEMENT_CONTRACT_MISMATCH",
            "message": "This transaction does not belong to the selected escrow.",
        })
    state = _job_state(job["address"])
    chain_job = state["job"]
    contract_settlement = chain_job.get("settlement") or {}
    if str(chain_job.get("status") or "") not in {"SETTLEMENT_PENDING", "ACCEPTED", "PARTIAL", "REFUNDED"}:
        raise HTTPException(status_code=409, detail={
            "code": "SETTLEMENT_STATE_MISMATCH",
            "message": "The escrow is not awaiting settlement verification.",
        })
    settlement = {
        **contract_settlement,
        **(job.get("settlement") or {}),
        "parent_transaction": tx_hash,
        "parent_status": status,
        "transfer_status": "PENDING_FINALIZATION",
        "transfer_reference": [tx_hash],
        "explorer": EXPLORER_TX + tx_hash,
        "submitted_at": (job.get("settlement") or {}).get("submitted_at") or utc_now(),
    }
    _record_verified_transaction(tx_hash, transaction, job["address"], "SETTLEMENT")
    store.update_job(job["address"], lifecycle_status="SETTLEMENT_PENDING", settlement=settlement)
    log_event(
        "registry_write",
        job=job["address"],
        tx_hash=tx_hash,
        action="register_settlement",
        status="SETTLEMENT_PENDING",
    )
    settlement = _refresh_settlement({**job, "settlement": settlement}, chain_job)
    response = {
        "tx": tx_hash,
        "status": settlement.get("transfer_status") or "PENDING_FINALIZATION",
        "settlement": _settlement_for_wire(settlement),
        "transaction_type": "wallet-signed transaction",
        "signer_role": "connected Bradbury client wallet",
        "network": "testnet_bradbury",
    }
    if replayed:
        response["replayed"] = True
    return response
