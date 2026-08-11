#!/usr/bin/env python3
"""Testnet-only custody verification for wallet-created Merit escrows.

The default and ``--dry-run`` modes only validate public configuration and
wallet funding.  Sending a transaction requires both ``--execute`` and
``--confirm-testnet-custody``.  Private keys are deliberately kept out of
printed and persisted evidence.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from eth_account import Account


ROOT = Path(__file__).parents[1]
WEI_PER_GEN = 10**18
MIN_FUNDED_WEI = 1
DEFAULT_ESCROW_WEI = 10**15  # 0.001 testnet GEN
BRADBURY_CHAIN_ID = 4221
MAX_TIMEOUT_SECONDS = 3600
REQUIRED_ENV = (
    "MERIT_API_URL",
    "BRADBURY_RPC_URL",
    "CLIENT_PRIVATE_KEY",
    "WORKER_PRIVATE_KEY",
)


class ConfigurationError(ValueError):
    """A non-secret configuration issue that is safe to show to the operator."""


class VerificationError(RuntimeError):
    """A custody assertion failed after testnet execution."""


@dataclass(frozen=True)
class Wallet:
    role: str
    address: str
    private_key: str = field(repr=False)


@dataclass(frozen=True)
class MatrixConfiguration:
    api_url: str
    rpc_url: str
    client: Wallet
    worker: Wallet


class EvidenceRecorder:
    """Write recovery-safe, public evidence as soon as a transaction broadcasts."""

    def __init__(self, path: Path, initial: dict[str, Any]):
        self.path = path
        self.evidence = {**initial, "scenarios": {}}
        self.persist()

    def persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=self.path.parent, delete=False) as handle:
            json.dump(self.evidence, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(self.path)

    def record_transaction(self, scenario: str, action: str, tx_hash: str) -> None:
        item = self.evidence["scenarios"].setdefault(scenario, {"transactions": {}, "state_transitions": []})
        item["transactions"][action] = tx_hash
        self.evidence["writes_sent"] = sum(len(entry["transactions"]) for entry in self.evidence["scenarios"].values())
        self.persist()

    def record_transition(self, scenario: str, observation: dict[str, Any]) -> None:
        item = self.evidence["scenarios"].setdefault(scenario, {"transactions": {}, "state_transitions": []})
        item["state_transitions"].append(observation)
        self.persist()

    def record_failure(self, message: str) -> None:
        self.evidence["failure"] = message
        self.persist()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _private_wallet(role: str, private_key: str) -> Wallet:
    try:
        account = Account.from_key(private_key)
    except Exception as exc:
        # Some account-parser exceptions embed input text, so never re-raise it.
        raise ConfigurationError(f"{role} private key is invalid.") from exc
    return Wallet(role=role, address=str(account.address), private_key=private_key)


def rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    request = Request(
        rpc_url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ConfigurationError("Bradbury RPC could not be reached for wallet validation.") from exc
    if payload.get("error"):
        raise ConfigurationError("Bradbury RPC rejected wallet validation.")
    return payload.get("result")


def rpc_balance(rpc_url: str, address: str) -> int:
    value = rpc_call(rpc_url, "eth_getBalance", [address, "latest"])
    try:
        return int(str(value), 16)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("Bradbury RPC returned an invalid wallet balance.") from exc


def validate_bradbury_chain(call: Callable[[str, list[Any]], Any]) -> int:
    """Prove the exact RPC endpoint is Bradbury; never infer this from its URL."""
    try:
        chain_id = int(str(call("eth_chainId", [])), 16)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("Bradbury RPC returned an invalid chain identity.") from exc
    if chain_id != BRADBURY_CHAIN_ID:
        raise ConfigurationError("BRADBURY_RPC_URL is not the Bradbury testnet (chain 4221).")
    return chain_id


def validate_timeout(timeout_seconds: int) -> int:
    if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ConfigurationError(f"timeout must be between 1 and {MAX_TIMEOUT_SECONDS} seconds.")
    return timeout_seconds


def validate_fixture_url(value: str, name: str) -> str:
    """Allow only a syntactically valid public http(s) evidence location."""
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a public http(s) fixture URL.") from exc
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ConfigurationError(f"{name} must be a public http(s) fixture URL.")
    normalized_host = host.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        raise ConfigurationError(f"{name} must use a public, non-local host.")
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        address = None
    # Python currently labels deprecated IPv6 site-local addresses as global,
    # so retain the explicit site-local guard alongside the global requirement.
    if address and (not address.is_global or address.is_site_local):
        raise ConfigurationError(f"{name} must use a public, non-local host.")
    if port is not None and not 1 <= port <= 65535:
        raise ConfigurationError(f"{name} must use a public http(s) fixture URL.")
    return value.strip()


def load_configuration(
    environ: Mapping[str, str],
    balance_of: Callable[[str], int] | None = None,
) -> MatrixConfiguration:
    missing = [name for name in REQUIRED_ENV if not str(environ.get(name, "")).strip()]
    if missing:
        raise ConfigurationError("Missing required environment variables: " + ", ".join(missing))

    api_url = str(environ["MERIT_API_URL"]).rstrip("/")
    rpc_url = str(environ["BRADBURY_RPC_URL"]).rstrip("/")
    if not api_url.startswith(("https://", "http://")) or not rpc_url.startswith(("https://", "http://")):
        raise ConfigurationError("MERIT_API_URL and BRADBURY_RPC_URL must be http(s) URLs.")

    client = _private_wallet("client", str(environ["CLIENT_PRIVATE_KEY"]).strip())
    worker = _private_wallet("worker", str(environ["WORKER_PRIVATE_KEY"]).strip())
    if client.address.lower() == worker.address.lower():
        raise ConfigurationError("Client and worker wallets must be different.")

    resolve_balance = balance_of or (lambda address: rpc_balance(rpc_url, address))
    unfunded = [wallet.role for wallet in (client, worker) if resolve_balance(wallet.address) < MIN_FUNDED_WEI]
    if unfunded:
        raise ConfigurationError("Required testnet wallets must be funded: " + ", ".join(unfunded))
    return MatrixConfiguration(api_url=api_url, rpc_url=rpc_url, client=client, worker=worker)


def dry_run_evidence(config: MatrixConfiguration) -> dict[str, Any]:
    """Return public, serializable preflight evidence only."""
    return {
        "mode": "dry-run",
        "network": "testnet_bradbury",
        "verified": True,
        "wallets": {"client": config.client.address, "worker": config.worker.address},
        "api_url": config.api_url,
        "rpc_url": config.rpc_url,
        "writes_sent": 0,
        "generated_at": utc_now(),
    }


def execution_requested(argv: list[str]) -> bool:
    """Small pure guard kept explicit so a normal invocation cannot write."""
    return "--execute" in argv


def http_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    encoded = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=encoded, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise VerificationError(f"Merit API request failed: {method} {url}") from exc
    if not isinstance(payload, dict):
        raise VerificationError("Merit API returned a non-object response.")
    return payload


def public_api_preflight(config: MatrixConfiguration) -> str:
    health = http_json(config.api_url + "/api/health")
    if health.get("network") != "testnet_bradbury":
        raise VerificationError("MERIT_API_URL is not reporting the Bradbury testnet.")
    demo = http_json(config.api_url + "/api/demo-mode")
    platform = str(demo.get("platform_address") or "")
    if not (platform.startswith("0x") and len(platform) == 42):
        raise VerificationError("Merit API did not expose a valid public platform fee address.")
    return platform


def _sdk(config: MatrixConfiguration):
    try:
        from genlayer_py import create_account, create_client, testnet_bradbury
    except Exception as exc:
        raise ConfigurationError(
            "GenLayer SDK is unavailable. Use the project Python 3.12 virtual environment and install requirements."
        ) from exc
    return create_client(testnet_bradbury, endpoint=config.rpc_url), create_account


def _wait_for_status(client: Any, tx_hash: str, *, timeout_seconds: int, final: bool) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    wanted = "FINALIZED" if final else "ACCEPTED"
    terminal = {"CANCELED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT", "OUT_OF_FEE", "OUTOFFEE"}
    last = "UNKNOWN"
    while time.monotonic() < deadline:
        result = client.provider.make_request("gen_getTransactionStatus", [{"txId": tx_hash}]).get("result") or {}
        last = str(result.get("status") or result.get("statusCode") or "UNKNOWN").upper()
        if last == wanted or (wanted == "ACCEPTED" and last == "FINALIZED"):
            receipt = dict(client.get_transaction(tx_hash))
            execution = str(receipt.get("tx_execution_result_name") or "").upper()
            if "ERROR" in execution:
                raise VerificationError(f"Transaction {tx_hash} executed with an error.")
            return receipt
        if last in terminal:
            raise VerificationError(f"Transaction {tx_hash} entered terminal status {last}.")
        time.sleep(5)
    raise VerificationError(f"Transaction {tx_hash} did not reach {wanted}; last status was {last}.")


def _read_contract(client: Any, address: str, sender: str, method: str) -> dict[str, Any]:
    import eth_utils
    from genlayer_py.abi.calldata.decoder import decode as calldata_decode
    from genlayer_py.abi.calldata.encoder import encode as calldata_encode
    from genlayer_py.abi.transactions import serialize as tx_serialize
    from genlayer_py.contracts.utils import make_calldata_object

    data = [calldata_encode(make_calldata_object(method=method, args=[], kwargs=None)), b"\x00"]
    raw = client.provider.make_request("gen_call", [{
        "type": "read", "to": address, "from": sender, "data": tx_serialize(data),
        "transaction_hash_variant": "latest-nonfinal",
    }])["result"]
    text = raw["data"] if isinstance(raw, dict) else raw
    return json.loads(calldata_decode(eth_utils.hexadecimal.decode_hex("0x" + text)))


def _write(
    client: Any, account: Any, address: str, method: str, *, args: list[Any] | None = None,
    value: int = 0, timeout_seconds: int, recorder: EvidenceRecorder, scenario: str, action: str,
) -> str:
    tx_hash = str(client.write_contract(address=address, function_name=method, account=account, args=args or [], value=value))
    recorder.record_transaction(scenario, action, tx_hash)
    _wait_for_status(client, tx_hash, timeout_seconds=timeout_seconds, final=False)
    return tx_hash


def _deploy(
    client: Any, account: Any, code: str, args: list[Any], *, timeout_seconds: int,
    recorder: EvidenceRecorder, scenario: str,
) -> tuple[str, str]:
    tx_hash = str(client.deploy_contract(code, account=account, args=args))
    recorder.record_transaction(scenario, "deployment", tx_hash)
    receipt = _wait_for_status(client, tx_hash, timeout_seconds=timeout_seconds, final=False)
    decoded = receipt.get("tx_data_decoded") or {}
    address = str(decoded.get("contract_address") or receipt.get("recipient") or "")
    if not (address.startswith("0x") and len(address) == 42):
        raise VerificationError("Accepted deployment did not include a contract address.")
    return tx_hash, address


def _register_job(config: MatrixConfiguration, payload: dict[str, Any]) -> dict[str, Any]:
    return http_json(config.api_url + "/api/jobs/register", method="POST", body=payload)


def _register_settlement(config: MatrixConfiguration, address: str, tx_hash: str) -> dict[str, Any]:
    return http_json(config.api_url + f"/api/jobs/{address}/register_settlement", method="POST", body={"transaction_hash": tx_hash})


def _registry_final(config: MatrixConfiguration, address: str, *, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = http_json(config.api_url + f"/api/jobs/{address}")
        job = payload.get("job") or {}
        settlement = job.get("settlement") or {}
        if settlement.get("transfer_status") == "FINALIZED":
            return payload
        time.sleep(10)
    raise VerificationError("Registry did not confirm settlement finalization before timeout.")


def observe_state(client: Any, address: str, sender: str, expected_state: str, tx_hash: str) -> dict[str, Any]:
    """Assert a freshly read contract state and attach it to its write evidence."""
    job = _read_contract(client, address, sender, "get_job")
    actual = str(job.get("status") or "UNKNOWN")
    if actual != expected_state:
        raise VerificationError(f"Transaction {tx_hash} expected {expected_state}, observed {actual}.")
    return {"transaction": tx_hash, "state": actual, "observed_at": utc_now()}


def require_replay(response: dict[str, Any]) -> bool:
    if response.get("replayed") is not True:
        raise VerificationError("Second settlement registration was not marked replayed.")
    return True


def _recipient_balances(config: MatrixConfiguration, addresses: list[str]) -> dict[str, int]:
    return {address.lower(): rpc_balance(config.rpc_url, address) for address in addresses}


def _settlement_delta_evidence(
    before: dict[str, int], after: dict[str, int], settlement: dict[str, Any], *, fee_payer: str,
) -> dict[str, Any]:
    expected = {
        str(transfer["recipient"]).lower(): int(transfer["amount"])
        for transfer in settlement.get("transfers", [])
        if isinstance(transfer, dict) and int(transfer.get("amount") or 0) > 0
    }
    observed = {address: after[address] - before[address] for address in before}
    # The finalizing client pays the parent transaction fee.  The transfer is
    # still independently evidenced by finalized external messages, but a raw
    # balance delta for that address is necessarily net of its gas charge.
    mismatches = {
        address: {"expected_wei": amount, "observed_wei": observed.get(address)}
        for address, amount in expected.items()
        if address in observed and address != fee_payer.lower() and observed[address] != amount
    }
    return {
        "expected_recipient_deltas_wei": expected,
        "observed_balance_deltas_wei": observed,
        "mismatches": mismatches,
        "fee_adjusted_recipient": fee_payer.lower() if fee_payer.lower() in expected else None,
    }


def _require_fixture(environ: Mapping[str, str], name: str) -> str:
    value = str(environ.get(name, "")).strip()
    return validate_fixture_url(value, name)


def _direct_scenario(
    config: MatrixConfiguration, client: Any, accounts: dict[str, Any], platform: str, *, name: str,
    submission_url: str, min_score: int, partial_floor: int, expected_outcome: str, timeout_seconds: int,
    recorder: EvidenceRecorder,
) -> dict[str, Any]:
    from genlayer_py.types.calldata import CalldataAddress

    deployment_tx, address = _deploy(
        client, accounts["client"], (ROOT / "contracts" / "freelance_escrow.py").read_text(),
        [f"Custody matrix {name}: evaluate the public fixture against this explicit requirement.", CalldataAddress(accounts["worker"].address), CalldataAddress(platform), 200, min_score, partial_floor],
        timeout_seconds=timeout_seconds, recorder=recorder, scenario=name,
    )
    registration = _register_job(config, {
        "address": address, "client_address": str(accounts["client"].address), "worker_address": str(accounts["worker"].address),
        "deployment_tx": deployment_tx, "title": f"Custody matrix {name}",
        "spec": f"Custody matrix {name}: evaluate the public fixture against this explicit requirement.",
        "fee_bps": 200, "min_score": min_score, "partial_floor": partial_floor, "job_type": "DIRECT_HIRE",
    })
    if str((registration.get("job") or {}).get("address", "")).lower() != address.lower():
        raise VerificationError("Deployment registration did not return the deployed escrow.")
    transactions = {"deployment": deployment_tx}
    observations = []
    def observe(expected: str, tx_hash: str) -> None:
        observation = observe_state(client, address, str(accounts["client"].address), expected, tx_hash)
        observations.append(observation)
        recorder.record_transition(name, observation)
    observe("UNFUNDED", deployment_tx)
    transactions["fund"] = _write(client, accounts["client"], address, "fund", value=DEFAULT_ESCROW_WEI, timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="fund")
    observe("OPEN", transactions["fund"])
    transactions["accept_terms"] = _write(client, accounts["worker"], address, "accept_terms", timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="accept_terms")
    observe("AGREED", transactions["accept_terms"])
    transactions["submit_work"] = _write(client, accounts["worker"], address, "submit_work", args=[submission_url], timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="submit_work")
    observe("SUBMITTED", transactions["submit_work"])
    transactions["evaluate"] = _write(client, accounts["client"], address, "evaluate", timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="evaluate")
    observe("EVALUATED", transactions["evaluate"])
    evaluated = _read_contract(client, address, str(accounts["client"].address), "get_result")
    tracked = [str(accounts["client"].address), str(accounts["worker"].address), platform]
    before = _recipient_balances(config, tracked)
    transactions["finalize"] = _write(client, accounts["client"], address, "finalize", timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="finalize")
    observe("SETTLEMENT_PENDING", transactions["finalize"])
    _register_settlement(config, address, transactions["finalize"])
    registry = _registry_final(config, address, timeout_seconds=timeout_seconds)
    replay = _register_settlement(config, address, transactions["finalize"])
    replayed = require_replay(replay)
    after = _recipient_balances(config, tracked)
    settlement = ((registry.get("job") or {}).get("settlement") or {})
    if settlement.get("outcome") != expected_outcome:
        raise VerificationError(f"{name} expected {expected_outcome}, got {settlement.get('outcome')}.")
    deltas = _settlement_delta_evidence(before, after, settlement, fee_payer=str(accounts["client"].address))
    return {
        "name": name, "job_address": address, "job_type": "DIRECT_HIRE", "verified": replayed and not bool(deltas["mismatches"]),
        "transactions": transactions, "state_transitions": observations,
        "evaluation": {"score": evaluated.get("score"), "status": evaluated.get("status")}, "settlement": settlement,
        "balances": {"starting_wei": before, "ending_wei": after, "recipient_deltas": deltas},
        "replay": {"settlement_replayed": replayed},
    }


def _bounty_scenario(
    config: MatrixConfiguration, client: Any, accounts: dict[str, Any], platform: str, *, name: str,
    first_url: str, second_url: str, min_score: int, expected_outcome: str, timeout_seconds: int,
    recorder: EvidenceRecorder,
) -> dict[str, Any]:
    """Run two distinct entries and prove that only the recorded winner can be paid."""
    from genlayer_py.types.calldata import CalldataAddress

    spec = f"Custody matrix {name}: evaluate two public fixtures under one shared observable rubric."
    deployment_tx, address = _deploy(
        client, accounts["client"], (ROOT / "contracts" / "bounty_escrow.py").read_text(),
        [spec, CalldataAddress(platform), 200, min_score, 2], timeout_seconds=timeout_seconds, recorder=recorder, scenario=name,
    )
    registration = _register_job(config, {
        "address": address, "client_address": str(accounts["client"].address), "deployment_tx": deployment_tx,
        "title": f"Custody matrix {name}", "spec": spec, "fee_bps": 200, "min_score": min_score,
        "partial_floor": min_score, "job_type": "BOUNTY", "max_submissions": 2,
    })
    if str((registration.get("job") or {}).get("address", "")).lower() != address.lower():
        raise VerificationError("Bounty deployment registration did not return the deployed escrow.")
    transactions = {"deployment": deployment_tx}
    observations = []
    def observe(expected: str, tx_hash: str) -> None:
        observation = observe_state(client, address, str(accounts["client"].address), expected, tx_hash)
        observations.append(observation)
        recorder.record_transition(name, observation)
    observe("UNFUNDED", deployment_tx)
    transactions["fund"] = _write(client, accounts["client"], address, "fund", value=DEFAULT_ESCROW_WEI, timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="fund")
    observe("OPEN", transactions["fund"])
    transactions["submit_first"] = _write(client, accounts["worker"], address, "submit_work", args=[first_url], timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="submit_first")
    observe("OPEN", transactions["submit_first"])
    transactions["submit_second"] = _write(client, accounts["bounty_worker"], address, "submit_work", args=[second_url], timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="submit_second")
    observe("OPEN", transactions["submit_second"])
    transactions["close_submissions"] = _write(client, accounts["client"], address, "close_submissions", timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="close_submissions")
    observe("CLOSED", transactions["close_submissions"])
    transactions["evaluate"] = _write(client, accounts["client"], address, "evaluate", timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="evaluate")
    observe("EVALUATED", transactions["evaluate"])
    evaluated = _read_contract(client, address, str(accounts["client"].address), "get_job")
    submissions = evaluated.get("submissions") or []
    winner = str(evaluated.get("winner") or "").lower()
    entrants = {str(item.get("submitter") or "").lower() for item in submissions if isinstance(item, dict)}
    if winner not in entrants:
        raise VerificationError("Bounty evaluation did not record one of the submitted wallets as winner.")
    tracked = [str(accounts["client"].address), str(accounts["worker"].address), str(accounts["bounty_worker"].address), platform]
    before = _recipient_balances(config, tracked)
    transactions["finalize"] = _write(client, accounts["client"], address, "finalize", timeout_seconds=timeout_seconds, recorder=recorder, scenario=name, action="finalize")
    observe("SETTLEMENT_PENDING", transactions["finalize"])
    _register_settlement(config, address, transactions["finalize"])
    registry = _registry_final(config, address, timeout_seconds=timeout_seconds)
    replay = _register_settlement(config, address, transactions["finalize"])
    replayed = require_replay(replay)
    after = _recipient_balances(config, tracked)
    settlement = ((registry.get("job") or {}).get("settlement") or {})
    if settlement.get("outcome") != expected_outcome:
        raise VerificationError(f"{name} expected {expected_outcome}, got {settlement.get('outcome')}.")
    transfers = [item for item in settlement.get("transfers", []) if isinstance(item, dict) and int(item.get("amount") or 0) > 0]
    paid_entrants = {str(item.get("recipient") or "").lower() for item in transfers if str(item.get("recipient") or "").lower() in entrants}
    if expected_outcome == "ACCEPTED" and paid_entrants != {winner}:
        raise VerificationError("Bounty payout did not pay exactly the recorded qualifying winner.")
    if expected_outcome == "REFUNDED" and paid_entrants:
        raise VerificationError("Below-threshold Bounty refund paid an entrant.")
    deltas = _settlement_delta_evidence(before, after, settlement, fee_payer=str(accounts["client"].address))
    return {
        "name": name, "job_address": address, "job_type": "BOUNTY", "verified": replayed and not bool(deltas["mismatches"]),
        "transactions": transactions,
        "state_transitions": observations,
        "winner": winner, "submissions": submissions, "settlement": settlement,
        "balances": {"starting_wei": before, "ending_wei": after, "recipient_deltas": deltas},
        "replay": {"settlement_replayed": replayed},
    }


def run_live_matrix(
    config: MatrixConfiguration, environ: Mapping[str, str], *, timeout_seconds: int, output_path: Path,
) -> dict[str, Any]:
    """Execute the live matrix only after CLI confirmation has passed."""
    validate_timeout(timeout_seconds)
    recorder = EvidenceRecorder(output_path, {
        "mode": "live-testnet", "network": "testnet_bradbury", "generated_at": utc_now(),
        "writes_sent": 0,
    })
    # Validate every external fixture and all required wallets before the first
    # deploy.  This prevents a partially executed matrix from a typo.
    fixtures = {name: _require_fixture(environ, name) for name in (
        "MERIT_FULL_FIXTURE_URL", "MERIT_SPLIT_FIXTURE_URL", "MERIT_REFUND_FIXTURE_URL",
        "MERIT_BOUNTY_WINNER_URL", "MERIT_BOUNTY_LOSER_URL", "MERIT_BOUNTY_REFUND_FIRST_URL", "MERIT_BOUNTY_REFUND_SECOND_URL",
    )}
    bounty_key = str(environ.get("BOUNTY_SECOND_WORKER_PRIVATE_KEY", "")).strip()
    if not bounty_key:
        raise ConfigurationError("BOUNTY_SECOND_WORKER_PRIVATE_KEY is required for two distinct Bounty submissions.")
    bounty_wallet = _private_wallet("bounty second worker", bounty_key)
    if bounty_wallet.address.lower() in {config.client.address.lower(), config.worker.address.lower()}:
        raise ConfigurationError("BOUNTY_SECOND_WORKER_PRIVATE_KEY must resolve to a third distinct wallet.")
    if rpc_balance(config.rpc_url, bounty_wallet.address) < MIN_FUNDED_WEI:
        raise ConfigurationError("Bounty second worker testnet wallet must be funded.")

    # This identity check uses the exact RPC endpoint that later signs and
    # broadcasts transactions; API configuration cannot substitute for it.
    validate_bradbury_chain(lambda method, params: rpc_call(config.rpc_url, method, params))
    try:
        platform = public_api_preflight(config)
        client, create_account = _sdk(config)
        accounts = {
            "client": create_account(config.client.private_key), "worker": create_account(config.worker.private_key),
            "bounty_worker": create_account(bounty_wallet.private_key),
        }
        scenarios = [
            _direct_scenario(config, client, accounts, platform, name="direct-full", submission_url=fixtures["MERIT_FULL_FIXTURE_URL"], min_score=0, partial_floor=0, expected_outcome="ACCEPTED", timeout_seconds=timeout_seconds, recorder=recorder),
            _direct_scenario(config, client, accounts, platform, name="direct-split", submission_url=fixtures["MERIT_SPLIT_FIXTURE_URL"], min_score=100, partial_floor=0, expected_outcome="PARTIAL", timeout_seconds=timeout_seconds, recorder=recorder),
            _direct_scenario(config, client, accounts, platform, name="direct-refund", submission_url=fixtures["MERIT_REFUND_FIXTURE_URL"], min_score=100, partial_floor=100, expected_outcome="REFUNDED", timeout_seconds=timeout_seconds, recorder=recorder),
            _bounty_scenario(config, client, accounts, platform, name="bounty-winner", first_url=fixtures["MERIT_BOUNTY_WINNER_URL"], second_url=fixtures["MERIT_BOUNTY_LOSER_URL"], min_score=0, expected_outcome="ACCEPTED", timeout_seconds=timeout_seconds, recorder=recorder),
            _bounty_scenario(config, client, accounts, platform, name="bounty-refund", first_url=fixtures["MERIT_BOUNTY_REFUND_FIRST_URL"], second_url=fixtures["MERIT_BOUNTY_REFUND_SECOND_URL"], min_score=100, expected_outcome="REFUNDED", timeout_seconds=timeout_seconds, recorder=recorder),
        ]
    except Exception as exc:
        recorder.record_failure("Live matrix stopped after a recoverable verification failure.")
        raise
    return {"mode": "live-testnet", "network": "testnet_bradbury", "generated_at": utc_now(), "scenarios": scenarios}


def write_evidence(path: str | None, evidence: dict[str, Any]) -> None:
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if path:
        Path(path).write_text(rendered)
    else:
        print(rendered, end="")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate only; sends no transactions.")
    parser.add_argument("--execute", action="store_true", help="Enable live testnet writes after explicit confirmation.")
    parser.add_argument("--confirm-testnet-custody", action="store_true", help="Acknowledge that --execute sends testnet GEN transactions.")
    parser.add_argument("--output", help="Write redacted JSON evidence to this path.")
    parser.add_argument("--timeout-seconds", type=int, default=900, help="Per-transaction and registry wait limit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(arguments)
    if args.dry_run and args.execute:
        raise ConfigurationError("Choose either --dry-run or --execute, not both.")
    config = load_configuration(os.environ)
    if not execution_requested(arguments):
        evidence = dry_run_evidence(config)
        evidence["mode"] = "dry-run" if args.dry_run else "safe-preflight"
        write_evidence(args.output, evidence)
        return 0
    if not args.confirm_testnet_custody:
        raise ConfigurationError("Live writes require --confirm-testnet-custody in addition to --execute.")
    validate_timeout(args.timeout_seconds)
    if not args.output:
        raise ConfigurationError("Live execution requires --output so submitted transaction hashes are recoverable.")
    evidence = run_live_matrix(config, os.environ, timeout_seconds=args.timeout_seconds, output_path=Path(args.output))
    write_evidence(args.output, evidence)
    return 0 if all(item.get("verified") for item in evidence.get("scenarios", [])) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ConfigurationError, VerificationError) as exc:
        # Error messages are designed to be public; do not print exception chains.
        print(f"custody matrix: {exc}", file=sys.stderr)
        raise SystemExit(2)
