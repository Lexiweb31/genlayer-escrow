"""Safety-contract tests for the live Bradbury custody matrix runner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).parents[2] / "scripts" / "custody_matrix.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("custody_matrix", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configured_environment() -> dict[str, str]:
    return {
        "MERIT_API_URL": "https://merit.example",
        "BRADBURY_RPC_URL": "https://rpc.example",
        "CLIENT_PRIVATE_KEY": "0x" + "11" * 32,
        "WORKER_PRIVATE_KEY": "0x" + "22" * 32,
    }


def test_dry_run_uses_public_addresses_and_never_returns_private_keys():
    """Changing a caller to echo configuration secrets must break this test."""
    runner = load_runner()
    environment = configured_environment()

    config = runner.load_configuration(environment, balance_of=lambda _address: 1)
    evidence = runner.dry_run_evidence(config)
    rendered = str(evidence)

    assert evidence["wallets"]["client"] != evidence["wallets"]["worker"]
    assert environment["CLIENT_PRIVATE_KEY"] not in rendered
    assert environment["WORKER_PRIVATE_KEY"] not in rendered


def test_dry_run_rejects_the_same_wallet_for_client_and_worker():
    """Using one wallet for both contract roles would invalidate custody checks."""
    runner = load_runner()
    environment = configured_environment()
    environment["WORKER_PRIVATE_KEY"] = environment["CLIENT_PRIVATE_KEY"]

    with pytest.raises(runner.ConfigurationError, match="different"):
        runner.load_configuration(environment, balance_of=lambda _address: 1)


def test_dry_run_rejects_an_unfunded_required_wallet():
    """Removing the balance check would permit a matrix that cannot execute."""
    runner = load_runner()

    with pytest.raises(runner.ConfigurationError, match="funded"):
        runner.load_configuration(configured_environment(), balance_of=lambda _address: 0)


def test_live_mode_requires_an_explicit_execution_switch():
    """Removing the switch would allow an ordinary command to send live writes."""
    runner = load_runner()

    assert runner.execution_requested([]) is False
    assert runner.execution_requested(["--execute"]) is True


def test_rpc_chain_identity_must_match_bradbury_before_live_execution():
    """Changing the chain check to trust a URL must make this test fail."""
    runner = load_runner()

    assert runner.validate_bradbury_chain(lambda method, params: "0x107d") == 4221
    with pytest.raises(runner.ConfigurationError, match="Bradbury"):
        runner.validate_bradbury_chain(lambda method, params: "0x1")


@pytest.mark.parametrize("url", [
    "http://localhost/proof",
    "https://127.0.0.1/proof",
    "https://[::1]/proof",
    "https://169.254.1.2/proof",
    "https://10.0.0.2/proof",
    "https://100.64.0.1/proof",
    "https://[fec0::1]/proof",
    "https://example.com@127.0.0.1/proof",
    "not-a-url",
])
def test_fixture_urls_reject_non_public_hosts(url):
    """Removing strict host parsing would let evaluators request private network URLs."""
    runner = load_runner()

    with pytest.raises(runner.ConfigurationError, match="public"):
        runner.validate_fixture_url(url, "FIXTURE")


def test_fixture_urls_preserve_a_public_https_url():
    """Rejecting all URLs would make the live matrix unusable for public evidence."""
    runner = load_runner()

    assert runner.validate_fixture_url("https://evidence.example/path?q=1", "FIXTURE") == "https://evidence.example/path?q=1"


@pytest.mark.parametrize("timeout", [0, -1, 3601])
def test_live_timeout_must_be_positive_and_bounded(timeout):
    """Removing timeout validation could leave a post-broadcast runner unrecoverably stuck."""
    runner = load_runner()

    with pytest.raises(runner.ConfigurationError, match="timeout"):
        runner.validate_timeout(timeout)


def test_observed_transition_includes_the_lifecycle_transaction(monkeypatch):
    """Replacing contract observation with hard-coded states must break this evidence check."""
    runner = load_runner()
    monkeypatch.setattr(runner, "_read_contract", lambda *_args: {"status": "OPEN"})

    observation = runner.observe_state(object(), "0xescrow", "0xsender", "OPEN", "0xfund")

    assert observation["state"] == "OPEN"
    assert observation["transaction"] == "0xfund"
    with pytest.raises(runner.VerificationError, match="expected AGREED"):
        runner.observe_state(object(), "0xescrow", "0xsender", "AGREED", "0xaccept")


def test_second_settlement_registration_must_be_marked_replayed():
    """Dropping the replay assertion would allow idempotency regressions to pass the gate."""
    runner = load_runner()

    assert runner.require_replay({"replayed": True}) is True
    with pytest.raises(runner.VerificationError, match="replayed"):
        runner.require_replay({"replayed": False})


def test_evidence_recorder_persists_a_submitted_hash_before_a_wait_failure(tmp_path):
    """Moving persistence after receipt polling would lose recovery evidence on interruption."""
    runner = load_runner()
    path = tmp_path / "evidence.json"
    recorder = runner.EvidenceRecorder(path, {"mode": "live-testnet"})

    recorder.record_transaction("direct-full", "fund", "0xsubmitted")

    evidence = __import__("json").loads(path.read_text())
    assert evidence["scenarios"]["direct-full"]["transactions"]["fund"] == "0xsubmitted"


def test_public_and_authenticated_recovery_fixtures_keep_unfunded_jobs_private(monkeypatch):
    """Removing either public filtering or client scoping must fail this release gate."""
    from datetime import datetime, timedelta, timezone

    from eth_account import Account
    from eth_account.messages import encode_defunct

    from dashboard import api

    client = Account.create()
    other = Account.create()
    mine = {
        "address": "0x1111111111111111111111111111111111111111",
        "title": "My private draft",
        "status": "UNFUNDED",
        "client_address": client.address,
    }
    theirs = {
        "address": "0x2222222222222222222222222222222222222222",
        "title": "Another private draft",
        "status": "UNFUNDED",
        "client_address": other.address,
    }
    public = {
        "address": "0x3333333333333333333333333333333333333333",
        "title": "Funded public job",
        "status": "OPEN",
        "client_address": other.address,
        "amount": "1000",
    }
    monkeypatch.setattr(api, "_list_jobs_snapshot", lambda: {
        "jobs": [mine, theirs, public],
        "stats": {},
        "demo": {"network": "testnet_bradbury"},
    })

    public_response = api._public_jobs_snapshot()
    assert [job["address"] for job in public_response["jobs"]] == [public["address"]]
    assert all(job["status"] != "UNFUNDED" for job in public_response["jobs"])

    message = api._ownership_message(
        client.address,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    signature = Account.sign_message(encode_defunct(text=message), client.key).signature.hex()
    owned_response = api.owned_jobs(api.OwnedJobsRequest(
        address=client.address,
        message=message,
        signature=signature,
    ))

    assert [job["address"] for job in owned_response["jobs"]] == [mine["address"]]
    assert signature not in str(public_response)
    assert signature not in str(owned_response)


def test_custody_runner_refuses_worker_actions_while_contract_remains_unfunded(monkeypatch, tmp_path):
    """Removing the post-funding OPEN observation would permit unsafe worker writes."""
    runner = load_runner()
    address = "0x1111111111111111111111111111111111111111"
    accounts = {
        "client": SimpleNamespace(address="0x2222222222222222222222222222222222222222"),
        "worker": SimpleNamespace(address="0x3333333333333333333333333333333333333333"),
        "bounty_worker": SimpleNamespace(address="0x4444444444444444444444444444444444444444"),
    }
    recorder = runner.EvidenceRecorder(tmp_path / "blocked.json", {"mode": "test"})
    writes: list[str] = []

    monkeypatch.setattr(runner, "_deploy", lambda *_args, **_kwargs: ("0xdeploy", address))
    monkeypatch.setattr(runner, "_register_job", lambda *_args, **_kwargs: {"job": {"address": address}})
    monkeypatch.setattr(runner, "_read_contract", lambda *_args: {"status": "UNFUNDED"})

    def write(*_args, **kwargs):
        writes.append(kwargs["action"])
        return f"0x{kwargs['action']}"

    monkeypatch.setattr(runner, "_write", write)

    with pytest.raises(runner.VerificationError, match="expected OPEN, observed UNFUNDED"):
        runner._direct_scenario(
            SimpleNamespace(), object(), accounts,
            "0x5555555555555555555555555555555555555555",
            name="direct-blocked", submission_url="https://evidence.example/direct",
            min_score=0, partial_floor=0, expected_outcome="ACCEPTED",
            timeout_seconds=30, recorder=recorder,
        )
    assert writes == ["fund"]
    assert "accept_terms" not in writes
    assert "submit_work" not in writes

    writes.clear()
    with pytest.raises(runner.VerificationError, match="expected OPEN, observed UNFUNDED"):
        runner._bounty_scenario(
            SimpleNamespace(), object(), accounts,
            "0x5555555555555555555555555555555555555555",
            name="bounty-blocked", first_url="https://evidence.example/first",
            second_url="https://evidence.example/second", min_score=0,
            expected_outcome="ACCEPTED", timeout_seconds=30, recorder=recorder,
        )
    assert writes == ["fund"]
    assert "submit_first" not in writes
    assert "submit_second" not in writes
