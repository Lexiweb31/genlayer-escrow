from types import SimpleNamespace
import time
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock, Thread

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException

from dashboard.store import JobStore
from dashboard.telemetry import log_event
import dashboard.api as api
from genlayer_py.types.transactions import TransactionStatus


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path)


def _record(address: str = "0xabc") -> dict:
    return {
        "address": address,
        "title": "Durable escrow",
        "spec": "Deliver a public page with a visible evidence section.",
        "fee_bps": 200,
        "min_score": 70,
        "partial_floor": 40,
        "client_address": "0xclient",
        "worker_address": "0xworker",
        "lifecycle_status": "UNFUNDED",
        "deployment_tx": "0xdeploy",
    }


def test_log_event_redacts_secret_fields(caplog):
    """A caller adding a secret field must not expose it in production logs."""
    log_event(
        "wallet_error",
        private_key="secret",
        authorization="Bearer secret",
        job="0xjob",
    )

    assert "secret" not in caplog.text
    assert "0xjob" in caplog.text


def test_health_reports_release_and_reconciliation_evidence(monkeypatch):
    """Operators need non-secret evidence that the durable reconciler is healthy."""
    monkeypatch.setenv("MERIT_RELEASE", "test-release")
    monkeypatch.setattr(api, "_oldest_pending_seconds", lambda: 42, raising=False)
    monkeypatch.setattr(api, "_last_reconcile_at", "2026-08-10T00:00:00+00:00", raising=False)
    monkeypatch.setattr(api, "_reconciler_health", lambda: "running", raising=False)

    response = api.health()

    assert response["release"] == "test-release"
    assert response["registry"] == "sqlite"
    assert response["reconciler"] == "running"
    assert response["oldest_pending_seconds"] == 42
    assert response["last_reconcile_at"] == "2026-08-10T00:00:00+00:00"


def test_health_uses_the_oldest_pending_transaction_creation_time(monkeypatch, tmp_path):
    """Refreshing an old pending transaction must not make it appear younger."""
    durable_store = JobStore(tmp_path)
    oldest = "0xoldest"
    newer = "0xnewer"
    for tx_hash in (oldest, newer):
        durable_store.record_transaction({
            "network": "testnet_bradbury",
            "tx_hash": tx_hash,
            "job_address": "0xjob",
            "kind": "SETTLEMENT",
            "status": "PENDING",
        })
    now = datetime.now(timezone.utc)
    with durable_store._connect() as conn:
        conn.execute(
            "UPDATE transactions SET created_at = ?, updated_at = ? WHERE tx_hash = ?",
            ((now - timedelta(seconds=120)).isoformat(), now.isoformat(), oldest),
        )
        conn.execute(
            "UPDATE transactions SET created_at = ?, updated_at = ? WHERE tx_hash = ?",
            ((now - timedelta(seconds=60)).isoformat(), (now - timedelta(seconds=60)).isoformat(), newer),
        )
    monkeypatch.setattr(api, "store", durable_store)

    assert api.health()["oldest_pending_seconds"] >= 110


def test_transaction_hash_is_idempotent(store):
    item = {
        "network": "testnet_bradbury",
        "tx_hash": "0xabc",
        "job_address": "0xjob",
        "kind": "DEPLOYMENT",
        "status": "ACCEPTED",
    }
    first = store.record_transaction(item)
    second = store.record_transaction(item)
    assert first["id"] == second["id"]
    assert len(store.list_pending_transactions()) == 1


def test_transaction_status_can_advance_but_not_regress(store):
    base = {
        "network": "testnet_bradbury",
        "tx_hash": "0xdef",
        "job_address": "0xjob",
        "kind": "SETTLEMENT",
        "status": "ACCEPTED",
    }
    store.record_transaction(base)
    store.record_transaction({
        **base,
        "status": "FINALIZED",
        "verified_at": "2026-08-10T00:00:00+00:00",
    })
    store.record_transaction(base)
    assert store.get_transaction("testnet_bradbury", "0xdef")["status"] == "FINALIZED"


def test_transaction_supports_sdk_intermediate_state_and_cancellation(store):
    base = {
        "network": "testnet_bradbury",
        "tx_hash": "0xlifecycle",
        "job_address": "0xjob",
        "kind": "SETTLEMENT",
        "status": "PENDING",
    }
    store.record_transaction(base)
    proposing = store.record_transaction({
        **base,
        "status": TransactionStatus.PROPOSING,
    })
    cancelled = store.record_transaction({**base, "status": "CANCELLED"})

    assert proposing["status"] == "PROPOSING"
    assert cancelled["status"] == "CANCELED"
    assert store.list_pending_transactions() == []


def test_transaction_hash_case_variants_are_idempotent(store):
    base = {
        "network": "testnet_bradbury",
        "tx_hash": "0xAbC",
        "job_address": "0xjob",
        "kind": "DEPLOYMENT",
        "status": "PENDING",
    }
    first = store.record_transaction(base)
    second = store.record_transaction({**base, "tx_hash": "0xabc"})

    assert first["id"] == second["id"]
    assert first["tx_hash"] == "0xabc"
    assert store.get_transaction("testnet_bradbury", "0xABC")["id"] == first["id"]
    assert len(store.list_pending_transactions()) == 1


def test_latest_funding_transaction_is_scoped_to_job_and_kind(store):
    store.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": "0xold",
        "job_address": "0xjob",
        "kind": "FUNDING",
        "status": "CANCELED",
    })
    store.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": "0xsettlement",
        "job_address": "0xjob",
        "kind": "SETTLEMENT",
        "status": "ACCEPTED",
    })
    store.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": "0xnew",
        "job_address": "0xjob",
        "kind": "FUNDING",
        "status": "ACCEPTED",
    })
    store.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": "0xother",
        "job_address": "0xother-job",
        "kind": "FUNDING",
        "status": "FINALIZED",
    })

    latest = store.latest_transaction_for_job("0xJOB", "FUNDING")

    assert latest is not None
    assert latest["tx_hash"] == "0xnew"
    assert store.get_transaction("testnet_bradbury", "0xold")["status"] == "CANCELED"


@pytest.mark.parametrize(
    ("network_status", "execution_result"),
    [
        ("UNDETERMINED", "UNKNOWN"),
        ("VALIDATORS_TIMEOUT", "UNKNOWN"),
        ("LEADER_TIMEOUT", "UNKNOWN"),
        ("FINALIZED", "FINISHED_WITH_ERROR"),
    ],
)
def test_job_detail_normalizes_terminal_funding_failure_without_losing_evidence(
    monkeypatch, tmp_path, network_status, execution_result
):
    job = _record("0x" + "1" * 40)
    journal = JobStore(tmp_path)
    journal.add_job(job)
    journal.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": "0x" + "f" * 64,
        "job_address": job["address"],
        "kind": "FUNDING",
        "status": network_status,
        "transaction": {"tx_execution_result_name": execution_result},
    })
    monkeypatch.setattr(api, "store", journal)

    response = api._job_detail_payload(
        journal.get_job(job["address"]),
        {"status": "UNFUNDED"},
        {"status": "UNFUNDED"},
    )

    assert response["funding_transaction"]["status"] == "FAILED"
    assert response["funding_transaction"]["network_status"] == network_status
    assert response["funding_transaction"]["execution_result"] == execution_result
    assert response["funding_transaction"]["tx_hash"] == "0x" + "f" * 64


def test_sqlite_jobs_survive_store_reopen(tmp_path):
    first = JobStore(tmp_path)
    first.add_job(_record())
    first.update_job(
        "0xabc",
        lifecycle_status="SETTLEMENT_PENDING",
        settlement={"transfer_status": "PENDING_FINALIZATION", "parent_transaction": "0xfinalize"},
        state_snapshot={"status": "SETTLEMENT_PENDING", "amount": "1000"},
    )

    restarted = JobStore(tmp_path)
    job = restarted.get_job("0xABC")
    assert job is not None
    assert job["client_address"] == "0xclient"
    assert job["worker_address"] == "0xworker"
    assert job["deployment_tx"] == "0xdeploy"
    assert job["lifecycle_status"] == "SETTLEMENT_PENDING"
    assert job["settlement"]["parent_transaction"] == "0xfinalize"
    assert job["state_snapshot"]["amount"] == "1000"


def test_bounty_registry_fields_survive_store_reopen(tmp_path):
    first = JobStore(tmp_path)
    first.add_job({
        **_record("0xbounty"),
        "job_type": "BOUNTY",
        "max_submissions": 5,
        "worker_address": "",
    })
    bounty = JobStore(tmp_path).get_job("0xbounty")
    assert bounty is not None
    assert bounty["job_type"] == "BOUNTY"
    assert bounty["max_submissions"] == 5
    assert bounty["worker_address"] == ""


def test_bounty_state_machine_uses_open_submission_round():
    assert api._expected_state("fund", "BOUNTY") == "UNFUNDED"
    assert api._expected_state("submit_work", "BOUNTY") == "OPEN"
    assert api._expected_state("close_submissions", "BOUNTY") == "OPEN"
    assert api._expected_state("evaluate", "BOUNTY") == "CLOSED"
    assert api._expected_state("finalize", "BOUNTY") == "EVALUATED"


def test_background_reconciliation_reads_the_durable_registry(monkeypatch):
    records = [_record("0xbackground")]
    received = []
    monkeypatch.setattr(api.store, "list_jobs", lambda: records)
    monkeypatch.setattr(api, "_refresh_marketplace_snapshots", lambda jobs: received.extend(jobs))

    api._reconcile_once()

    assert received == records


def test_reconcile_failure_is_durable_and_serves_the_last_verified_snapshot(monkeypatch, tmp_path):
    durable_store = JobStore(tmp_path)
    durable_store.add_job({
        **_record("0xstale"),
        "lifecycle_status": "SETTLEMENT_PENDING",
        "state_snapshot": {
            "status": "SETTLEMENT_PENDING",
            "amount": "1000",
            "score": 60,
            "settlement": {"parent_transaction": "0xparent", "transfer_status": "PENDING_FINALIZATION"},
            "job": {"status": "SETTLEMENT_PENDING", "amount": "1000"},
            "result": {"status": "SETTLEMENT_PENDING", "score": 60},
        },
    })
    monkeypatch.setattr(api, "store", durable_store)
    monkeypatch.setattr(api, "_job_state", lambda _address: (_ for _ in ()).throw(ConnectionError("network unavailable")))

    api._refresh_marketplace_snapshots(durable_store.list_jobs())

    restarted = JobStore(tmp_path).get_job("0xstale")
    assert restarted is not None
    assert restarted["state_snapshot"]["status"] == "SETTLEMENT_PENDING"
    assert restarted["reconcile_state"] == "BACKING_OFF"
    assert restarted["reconcile_error_code"] == "TESTNET_UNAVAILABLE"
    assert restarted["reconcile_attempted_at"]
    assert restarted["reconcile_age_seconds"] >= 0

    response = api._list_jobs_snapshot()
    assert response["jobs"][0]["status"] == "SETTLEMENT_PENDING"
    assert response["jobs"][0]["stale"] is True


def test_reconcile_never_attempts_a_verified_final_snapshot(monkeypatch):
    record = {
        **_record("0xfinal"),
        "state_snapshot": {
            "status": "ACCEPTED",
            "settlement": {"transfer_status": "FINALIZED"},
            "job": {"status": "ACCEPTED", "settlement": {"transfer_status": "FINALIZED"}},
            "result": {"status": "ACCEPTED"},
        },
    }
    monkeypatch.setattr(api, "_job_state", lambda _address: pytest.fail("finalized snapshot should not be reconciled"))

    api._refresh_marketplace_snapshots([record])


def test_detail_read_without_snapshot_classifies_and_suppresses_network_diagnostics(monkeypatch, tmp_path):
    durable_store = JobStore(tmp_path)
    durable_store.add_job(_record("0xno-snapshot"))
    monkeypatch.setattr(api, "store", durable_store)
    secret = "https://private-rpc.example/internal-token"
    monkeypatch.setattr(api, "_job_state", lambda _address: (_ for _ in ()).throw(ConnectionError(secret)))

    with pytest.raises(HTTPException) as exc:
        api.get_job("0xno-snapshot")

    assert exc.value.status_code == 502
    assert exc.value.detail == {
        "code": "TESTNET_UNAVAILABLE",
        "message": "Bradbury job state could not be read.",
    }
    assert secret not in str(exc.value.detail)


def test_detail_read_failure_returns_updated_stale_reconciliation_metadata(monkeypatch, tmp_path):
    durable_store = JobStore(tmp_path)
    durable_store.add_job({
        **_record("0xdetail-stale"),
        "state_snapshot": {
            "status": "SETTLEMENT_PENDING",
            "settlement": {"parent_transaction": "0xparent", "transfer_status": "PENDING_FINALIZATION"},
            "job": {"status": "SETTLEMENT_PENDING"},
            "result": {"status": "SETTLEMENT_PENDING"},
        },
    })
    monkeypatch.setattr(api, "store", durable_store)
    monkeypatch.setattr(api, "_job_state", lambda _address: (_ for _ in ()).throw(ConnectionError("network unavailable")))

    response = api.get_job("0xdetail-stale")

    assert response["meta"]["reconcile_state"] == "BACKING_OFF"
    assert response["meta"]["reconcile_error_code"] == "TESTNET_UNAVAILABLE"
    assert response["meta"]["stale"] is True
    assert response["job"]["status"] == "SETTLEMENT_PENDING"


def test_detail_read_recovery_returns_cleared_reconciliation_metadata(monkeypatch, tmp_path):
    durable_store = JobStore(tmp_path)
    durable_store.add_job({
        **_record("0xdetail-current"),
        "reconcile_state": "BACKING_OFF",
        "reconcile_attempted_at": "2020-01-01T00:00:00+00:00",
        "reconcile_error_code": "TESTNET_UNAVAILABLE",
        "state_snapshot": {
            "status": "SETTLEMENT_PENDING",
            "settlement": {"transfer_status": "PENDING_FINALIZATION"},
            "job": {"status": "SETTLEMENT_PENDING"},
            "result": {"status": "SETTLEMENT_PENDING"},
        },
    })
    monkeypatch.setattr(api, "store", durable_store)
    monkeypatch.setattr(api, "_job_state", lambda _address: {
        "job": {"status": "OPEN", "amount": 1000, "settlement": {}},
        "result": {"status": "OPEN"},
    })

    response = api.get_job("0xdetail-current")

    assert response["meta"]["reconcile_state"] == "CURRENT"
    assert response["meta"]["reconcile_error_code"] == ""
    assert response["meta"].get("stale") is not True
    assert response["job"]["status"] == "OPEN"


def test_legacy_import_is_read_only_and_does_not_overwrite_new_record(tmp_path):
    store = JobStore(tmp_path)
    store.add_job(_record())
    store.import_legacy_records([{"address": "0xabc", "title": "old", "spec": "old"}])
    current = store.get_job("0xabc")
    assert current is not None
    assert current["legacy_contract"] is False
    assert current["title"] == "Durable escrow"

    store.import_legacy_records([{"address": "0xlegacy", "title": "old", "spec": "old"}])
    legacy = store.get_job("0xlegacy")
    assert legacy is not None
    assert legacy["legacy_contract"] is True
    assert legacy["lifecycle_status"] == "LEGACY_UNSAFE"
    assert legacy["settlement"]["transfer_status"] == "LEGACY_UNSAFE"


def test_demo_roles_are_disabled_when_keys_are_missing(monkeypatch):
    monkeypatch.delenv("DEMO_CLIENT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("DEMO_WORKER_PRIVATE_KEY", raising=False)
    client, worker, error = api._configure_demo_accounts()
    assert client is None and worker is None
    assert "disabled" in error.lower()


def test_demo_roles_require_both_keys(monkeypatch):
    monkeypatch.setenv("DEMO_CLIENT_PRIVATE_KEY", "client-key")
    monkeypatch.delenv("DEMO_WORKER_PRIVATE_KEY", raising=False)
    client, worker, error = api._configure_demo_accounts()
    assert client is None and worker is None
    assert "both" in error.lower()


def test_platform_fee_address_must_be_explicit_public_address(monkeypatch):
    monkeypatch.delenv("PLATFORM_FEE_ADDRESS", raising=False)
    assert api._configured_platform_address() is None
    monkeypatch.setenv("PLATFORM_FEE_ADDRESS", "0x" + "0" * 40)
    assert api._configured_platform_address() is None
    address = "0x" + "4" * 40
    monkeypatch.setenv("PLATFORM_FEE_ADDRESS", address)
    assert api._configured_platform_address() == address


def test_demo_role_addresses_must_differ(monkeypatch):
    monkeypatch.setenv("DEMO_CLIENT_PRIVATE_KEY", "client-key")
    monkeypatch.setenv("DEMO_WORKER_PRIVATE_KEY", "worker-key")
    monkeypatch.setattr(api, "create_account", lambda _: SimpleNamespace(address="0xsame"))
    client, worker, error = api._configure_demo_accounts()
    assert client is None and worker is None
    assert "same address" in error.lower()


def test_invalid_demo_key_is_never_reflected(monkeypatch):
    secret = "0xDO_NOT_ECHO_THIS_PRIVATE_KEY"
    monkeypatch.setenv("DEMO_CLIENT_PRIVATE_KEY", secret)
    monkeypatch.setenv("DEMO_WORKER_PRIVATE_KEY", "different-secret")
    monkeypatch.setattr(api, "create_account", lambda _: (_ for _ in ()).throw(ValueError(secret)))
    client, worker, error = api._configure_demo_accounts()
    assert client is None and worker is None
    assert secret not in error
    assert "invalid" in error.lower()


def test_legacy_job_writes_are_rejected():
    with pytest.raises(HTTPException) as exc:
        api._require_safe_job({"legacy_contract": True})
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LEGACY_SETTLEMENT_CONTRACT"


def test_fund_request_preserves_exact_decimal_wei_string():
    amount = "1000000000000000001"
    assert api.FundRequest(amount_wei=amount).amount_wei == amount


def test_fund_rejects_below_demo_minimum_before_chain_call():
    with pytest.raises(HTTPException) as exc:
        api.fund("0xunused", api.FundRequest(amount_wei="999999999999999"))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "BELOW_MINIMUM_DEMO_AMOUNT"
    assert exc.value.detail["minimum_wei"] == "1000000000000000"


def test_demo_fund_rejects_duplicate_while_verified_transaction_is_nonterminal(monkeypatch, tmp_path):
    job = {
        **_record("0x" + "1" * 40),
        "client_address": "0x" + "2" * 40,
    }
    journal = JobStore(tmp_path)
    journal.add_job(job)
    journal.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": "0x" + "a" * 64,
        "job_address": job["address"],
        "kind": "FUNDING",
        "status": "ACCEPTED",
    })
    monkeypatch.setattr(api, "store", journal)
    monkeypatch.setattr(api, "_job_state", lambda _address: {
        "job": {"status": "UNFUNDED", "client": job["client_address"]},
        "result": {"status": "UNFUNDED"},
    })
    monkeypatch.setattr(api, "_preflight", lambda *_args, **_kwargs: {
        "job": {"status": "UNFUNDED", "client": job["client_address"]},
        "result": {"status": "UNFUNDED"},
    })
    monkeypatch.setattr(api, "_call_write", lambda *_args, **_kwargs: pytest.fail("duplicate funding submitted"))

    with pytest.raises(HTTPException) as exc:
        api.fund(job["address"], api.FundRequest(amount_wei="1000000000000000"))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "FUNDING_ALREADY_PENDING"


def test_concurrent_demo_funding_reserves_job_before_submitting(monkeypatch, tmp_path):
    job = {**_record("0x" + "1" * 40), "client_address": "0x" + "2" * 40}
    journal = JobStore(tmp_path)
    journal.add_job(job)
    monkeypatch.setattr(api, "store", journal)
    chain_state = {
        "job": {"status": "UNFUNDED", "client": job["client_address"]},
        "result": {"status": "UNFUNDED"},
    }
    monkeypatch.setattr(api, "_job_state", lambda _address: chain_state)
    monkeypatch.setattr(api, "_preflight", lambda *_args, **_kwargs: chain_state)
    first_submitted = Event()
    release_first = Event()
    calls = []

    def submit_once(*_args, **_kwargs):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            first_submitted.set()
            assert release_first.wait(timeout=2)
            return "0x" + "a" * 64
        return "0x" + "b" * 64

    monkeypatch.setattr(api, "_call_write", submit_once)
    monkeypatch.setattr(api, "_wait", lambda tx_hash: {
        "status_name": "ACCEPTED",
        "tx_execution_result_name": "SUCCESS",
        "tx_hash": tx_hash,
    })
    first_errors = []

    def fund_first():
        try:
            api.fund(job["address"], api.FundRequest(amount_wei="1000000000000000"))
        except Exception as exc:
            first_errors.append(exc)

    first = Thread(target=fund_first)
    first.start()
    assert first_submitted.wait(timeout=2)
    try:
        with pytest.raises(HTTPException) as exc:
            api.fund(job["address"], api.FundRequest(amount_wei="1000000000000000"))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "FUNDING_ALREADY_PENDING"
    finally:
        release_first.set()
        first.join(timeout=5)

    assert not first.is_alive()
    assert first_errors == []
    assert calls == [1]


def test_demo_funding_journals_hash_before_waiting_for_consensus(monkeypatch, tmp_path):
    job = {**_record("0x" + "1" * 40), "client_address": "0x" + "2" * 40}
    tx_hash = "0x" + "c" * 64
    journal = JobStore(tmp_path)
    journal.add_job(job)
    monkeypatch.setattr(api, "store", journal)
    chain_state = {
        "job": {"status": "UNFUNDED", "client": job["client_address"]},
        "result": {"status": "UNFUNDED"},
    }
    monkeypatch.setattr(api, "_job_state", lambda _address: chain_state)
    monkeypatch.setattr(api, "_preflight", lambda *_args, **_kwargs: chain_state)
    monkeypatch.setattr(api, "_call_write", lambda *_args, **_kwargs: tx_hash)
    monkeypatch.setattr(api, "_wait", lambda _tx: (_ for _ in ()).throw(RuntimeError("poll interrupted")))

    with pytest.raises(HTTPException):
        api.fund(job["address"], api.FundRequest(amount_wei="1000000000000000"))

    funding = journal.latest_transaction_for_job(job["address"], "FUNDING")
    assert funding is not None
    assert funding["tx_hash"] == tx_hash
    assert funding["status"] == "SUBMITTED"


def test_demo_funding_releases_reservation_when_submission_fails_before_hash(monkeypatch, tmp_path):
    job = {**_record("0x" + "1" * 40), "client_address": "0x" + "2" * 40}
    tx_hash = "0x" + "d" * 64
    journal = JobStore(tmp_path)
    journal.add_job(job)
    monkeypatch.setattr(api, "store", journal)
    chain_state = {
        "job": {"status": "UNFUNDED", "client": job["client_address"]},
        "result": {"status": "UNFUNDED"},
    }
    monkeypatch.setattr(api, "_job_state", lambda _address: chain_state)
    monkeypatch.setattr(api, "_preflight", lambda *_args, **_kwargs: chain_state)
    submissions = iter([RuntimeError("wallet unavailable before hash"), tx_hash])

    def submit(*_args, **_kwargs):
        result = next(submissions)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(api, "_call_write", submit)
    monkeypatch.setattr(api, "_wait", lambda _tx: {
        "status_name": "ACCEPTED",
        "tx_execution_result_name": "SUCCESS",
    })

    with pytest.raises(HTTPException):
        api.fund(job["address"], api.FundRequest(amount_wei="1000000000000000"))
    response = api.fund(job["address"], api.FundRequest(amount_wei="1000000000000000"))

    assert response["tx"] == tx_hash
    assert journal.latest_transaction_for_job(job["address"], "FUNDING")["tx_hash"] == tx_hash


def test_stale_funding_reservation_can_be_reclaimed_after_process_interruption(store):
    assert store.reserve_funding("0xjob") is True
    with store._connect() as conn:
        conn.execute(
            "UPDATE funding_reservations SET created_at = ? WHERE lower(job_address) = lower(?)",
            ((datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(), "0xjob"),
        )

    assert store.reserve_funding("0xJOB") is True


def test_demo_funding_allows_retry_after_finalized_execution_failure(monkeypatch, tmp_path):
    job = {**_record("0x" + "1" * 40), "client_address": "0x" + "2" * 40}
    failed_hash = "0x" + "e" * 64
    retry_hash = "0x" + "f" * 64
    journal = JobStore(tmp_path)
    journal.add_job(job)
    journal.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": failed_hash,
        "job_address": job["address"],
        "kind": "FUNDING",
        "status": "FINALIZED",
        "transaction": {"tx_execution_result_name": "FINISHED_WITH_ERROR"},
    })
    monkeypatch.setattr(api, "store", journal)
    chain_state = {
        "job": {"status": "UNFUNDED", "client": job["client_address"]},
        "result": {"status": "UNFUNDED"},
    }
    monkeypatch.setattr(api, "_job_state", lambda _address: chain_state)
    monkeypatch.setattr(api, "_preflight", lambda *_args, **_kwargs: chain_state)
    monkeypatch.setattr(api, "_call_write", lambda *_args, **_kwargs: retry_hash)
    monkeypatch.setattr(api, "_wait", lambda _tx: {
        "status_name": "ACCEPTED",
        "tx_execution_result_name": "SUCCESS",
    })

    response = api.fund(job["address"], api.FundRequest(amount_wei="1000000000000000"))

    assert response["tx"] == retry_hash
    assert journal.latest_transaction_for_job(job["address"], "FUNDING")["tx_hash"] == retry_hash
    assert journal.get_transaction("testnet_bradbury", failed_hash)["status"] == "FINALIZED"


def test_marketplace_stats_separate_locked_pending_and_finalized():
    jobs = [
        {"status": "SUBMITTED", "amount": "1", "settlement": {}},
        {
            "status": "SETTLEMENT_PENDING",
            "amount": "1000",
            "settlement": {
                "transfers": [
                    {"amount": "700", "settlement_type": "WORKER_PAYOUT"},
                    {"amount": "300", "settlement_type": "CLIENT_REFUND"},
                ]
            },
        },
        {
            "status": "REFUNDED",
            "amount": "0",
            "settlement": {
                "transfer_status": "FINALIZED",
                "transfers": [{"amount": "2000", "settlement_type": "CLIENT_REFUND"}],
            },
        },
    ]
    summary = api._marketplace_stats(
        jobs, total_jobs=4, degraded_jobs=0, legacy_jobs=1
    )
    assert summary["locked_wei"] == "1"
    assert summary["pending_settlement_wei"] == "1000"
    assert summary["protected_wei"] == "1001"
    assert summary["settlement_pending"] == 1
    assert summary["finalized_settlements"] == 1
    assert summary["finalized_settlement_wei"] == "2000"


def test_public_jobs_exclude_unfunded_direct_hire_and_bounty(monkeypatch):
    monkeypatch.setattr(api.store, "list_jobs", lambda: [
        {**_record("0xdirect"), "job_type": "DIRECT_HIRE"},
        {**_record("0xbounty"), "job_type": "BOUNTY"},
        {
            **_record("0xopen"),
            "lifecycle_status": "OPEN",
            "state_snapshot": {"status": "OPEN", "amount": "1000"},
        },
        {**_record("0xdegraded"), "lifecycle_status": "OPEN"},
        {**_record("0xlegacy"), "legacy_contract": True},
    ])

    response = api._public_jobs_snapshot()

    assert [job["address"] for job in response["jobs"]] == [
        "0xopen",
        "0xdegraded",
        "0xlegacy",
    ]
    assert {key: value for key, value in response["stats"].items() if key != "generated_at"} == {
        "network": "testnet_bradbury",
        "total_jobs": 3,
        "active_jobs": 2,
        "open_opportunities": 2,
        "locked_wei": "1000",
        "pending_settlement_wei": "0",
        "protected_wei": "1000",
        "settlement_pending": 0,
        "finalized_settlements": 0,
        "finalized_settlement_wei": "0",
        "escrow_wei": "1000",
        "escrow_gen": 1000 / 10**18,
        "degraded_jobs": 1,
        "legacy_jobs": 1,
    }


def test_owned_jobs_requires_a_signature_matching_the_recorded_client(monkeypatch):
    account = Account.create()
    other = Account.create()
    monkeypatch.setattr(
        api.store,
        "list_jobs",
        lambda: [{**_record("0xmine"), "client_address": account.address}],
    )
    message = api._ownership_message(
        account.address,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()

    owned = api.owned_jobs(
        api.OwnedJobsRequest(address=account.address, message=message, signature=signature)
    )

    assert [job["address"] for job in owned["jobs"]] == ["0xmine"]
    with pytest.raises(HTTPException) as error:
        api.owned_jobs(
            api.OwnedJobsRequest(address=other.address, message=message, signature=signature)
        )
    assert error.value.status_code == 403


def test_owned_jobs_rejects_a_malformed_signature():
    account = Account.create()
    message = api._ownership_message(
        account.address,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    with pytest.raises(HTTPException) as error:
        api._verify_owned_jobs_request(
            api.OwnedJobsRequest(address=account.address, message=message, signature="0x")
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "OWNERSHIP_PROOF_INVALID"


def test_owned_jobs_endpoint_rejects_an_invalid_65_byte_signature():
    account = Account.create()
    message = api._ownership_message(
        account.address,
        datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    with pytest.raises(HTTPException) as error:
        api.owned_jobs(
            api.OwnedJobsRequest(
                address=account.address,
                message=message,
                signature="0x" + "00" * 65,
            )
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "OWNERSHIP_PROOF_INVALID"


def test_submitted_job_is_not_reported_as_evaluated(monkeypatch):
    record = _record("0xsubmitted")
    record["state_snapshot"] = {
        "status": "SUBMITTED",
        "amount": "1",
        "score": 0,
        "settlement": {"transfer_status": "NOT_STARTED", "transfers": []},
    }
    monkeypatch.setattr(api.store, "list_jobs", lambda: [record])
    response = api._list_jobs_snapshot()
    assert response["jobs"][0]["amount"] == "1"
    assert response["jobs"][0]["evaluation_complete"] is False
    assert response["jobs"][0]["score"] is None
    assert response["stats"]["locked_wei"] == "1"


def test_marketplace_starts_independent_chain_reads_concurrently(monkeypatch):
    records = [_record("0xfirst"), _record("0xsecond"), _record("0xthird")]
    monkeypatch.setattr(api.store, "list_jobs", lambda: records)
    monkeypatch.setattr(api.store, "update_job", lambda *_args, **_kwargs: None)
    started = []

    def read_state(address):
        started.append(address)
        # Every task must have started before any one is allowed to finish.
        deadline = time.monotonic() + 1
        while len(started) < len(records) and time.monotonic() < deadline:
            time.sleep(0.005)
        return {
            "job": {"status": "OPEN", "amount": 1, "settlement": {}},
            "result": {"status": "OPEN", "score": 0},
        }

    monkeypatch.setattr(api, "_job_state", read_state)
    api._refresh_marketplace_snapshots(records)
    assert len(started) == 3


def test_finalized_job_detail_uses_verified_full_snapshot(monkeypatch):
    record = _record("0xfinalized")
    record["state_snapshot"] = {
        "status": "PARTIAL",
        "amount": "0",
        "score": 60,
        "settlement": {"outcome": "PARTIAL", "transfer_status": "FINALIZED"},
        "job": {
            "address": "0xfinalized",
            "status": "PARTIAL",
            "amount": "0",
            "settlement": {"outcome": "PARTIAL", "transfer_status": "FINALIZED"},
        },
        "result": {"status": "PARTIAL", "score": 60},
    }
    monkeypatch.setattr(api, "_find_job", lambda _job_id: record)
    monkeypatch.setattr(api, "_job_state", lambda _address: pytest.fail("finalized state should be served from its verified snapshot"))

    response = api.get_job("0xfinalized")

    assert response["job"]["status"] == "PARTIAL"
    assert response["result"]["score"] == 60


def test_wire_settlement_amounts_are_exact_strings():
    settlement = api._settlement_for_wire({
        "transfers": [{"amount": 10**18 + 1, "recipient": "0xworker"}],
        "transfer_evidence": [{"amount": 10**18 + 1, "reference": "0xtx"}],
    })
    assert settlement["transfers"][0]["amount"] == "1000000000000000001"
    assert settlement["transfer_evidence"][0]["amount"] == "1000000000000000001"


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("insufficient funds for gas", "INSUFFICIENT_DEMO_GEN"),
        ("[EXPECTED] Job already funded (status: OPEN)", "STALE_STATE"),
        ("validator rejected payload", "TESTNET_REJECTION"),
    ],
)
def test_action_errors_keep_real_failure_category(message, code):
    error = api._action_error(RuntimeError(message))
    assert error.detail["code"] == code
    assert message in error.detail["testnet_detail"]


def test_status_name_handles_sdk_enum_values():
    assert api._status_name({"status": TransactionStatus.FINALIZED}) == "FINALIZED"
    assert api._status_name({"status_name": TransactionStatus.ACCEPTED}) == "ACCEPTED"


def _wallet_registration_request() -> api.RegisterWalletJobRequest:
    return api.RegisterWalletJobRequest(
        address="0x" + "1" * 40,
        client_address="0x" + "2" * 40,
        worker_address="0x" + "3" * 40,
        deployment_tx="0x" + "5" * 64,
        title="Verified wallet job",
        spec="Deliver a public page with inspectable evidence.",
        fee_bps=200,
        min_score=70,
        partial_floor=40,
    )


def _configure_valid_wallet_registration(monkeypatch):
    request = _wallet_registration_request()
    platform = "0x" + "4" * 40
    monkeypatch.setenv("PLATFORM_FEE_ADDRESS", platform)
    monkeypatch.setattr(
        api,
        "network_client",
        SimpleNamespace(get_transaction=lambda _tx: {
            "status_name": TransactionStatus.ACCEPTED,
            "tx_execution_result_name": "SUCCESS",
            "sender": request.client_address,
            "network": "testnet_bradbury",
            "tx_data_decoded": {"type": "deploy", "contract_address": request.address},
        }),
    )
    monkeypatch.setattr(api, "_job_state", lambda _address: {"job": {
        "client": request.client_address,
        "worker": request.worker_address,
        "platform": platform,
        "spec": request.spec,
        "fee_bps": request.fee_bps,
        "min_score": request.min_score,
        "partial_floor": request.partial_floor,
        "status": "UNFUNDED",
    }})
    return request, platform


def test_wallet_registration_verifies_transaction_contract_and_platform(monkeypatch):
    request, _platform = _configure_valid_wallet_registration(monkeypatch)
    monkeypatch.setattr(api.store, "get_job", lambda _address: None)
    monkeypatch.setattr(api.store, "get_transaction", lambda *_args: None)
    monkeypatch.setattr(api.store, "record_transaction", lambda record: record)
    saved = {}
    monkeypatch.setattr(api.store, "add_job", lambda record, **_kwargs: saved.update(record) or record)
    response = api.register_wallet_job(request)
    assert response["job"]["address"] == request.address
    assert saved["client_address"] == request.client_address
    assert saved["worker_address"] == request.worker_address
    assert saved["deployment_tx"] == request.deployment_tx


def test_wallet_registration_replay_returns_the_registered_job(monkeypatch, tmp_path):
    request, _platform = _configure_valid_wallet_registration(monkeypatch)
    monkeypatch.setattr(
        api,
        "network_client",
        SimpleNamespace(get_transaction=lambda _tx: {
            "status_name": TransactionStatus.ACCEPTED,
            "tx_execution_result_name": "SUCCESS",
            "sender": request.client_address,
            "network": "testnet_bradbury",
            "tx_data_decoded": {"type": "deploy", "contract_address": request.address},
        }),
    )
    monkeypatch.setattr(api, "store", JobStore(tmp_path))

    first = api.register_wallet_job(request)
    second = api.register_wallet_job(request)

    assert second["job"]["address"] == first["job"]["address"]
    assert second["replayed"] is True


def test_wallet_registration_rejects_non_deployment_action(monkeypatch):
    request, _platform = _configure_valid_wallet_registration(monkeypatch)
    monkeypatch.setattr(
        api,
        "network_client",
        SimpleNamespace(get_transaction=lambda _tx: {
            "status_name": TransactionStatus.ACCEPTED,
            "tx_execution_result_name": "SUCCESS",
            "sender": request.client_address,
            "network": "testnet_bradbury",
            "tx_data_decoded": {
                "type": "call",
                "contract_address": request.address,
                "call_data": {"method": "evaluate"},
            },
        }),
    )
    monkeypatch.setattr(api.store, "get_transaction", lambda *_args: None)

    with pytest.raises(HTTPException) as exc:
        api.register_wallet_job(request)

    assert exc.value.detail["code"] == "DEPLOYMENT_ACTION_MISMATCH"


def test_concurrent_wallet_registration_retries_return_the_registered_job(monkeypatch, tmp_path):
    request, _platform = _configure_valid_wallet_registration(monkeypatch)
    journal = JobStore(tmp_path)
    original_get_job = journal.get_job
    concurrent_reads = Barrier(2)
    read_lock = Lock()
    reads = 0

    def synchronized_get_job(job_id):
        nonlocal reads
        with read_lock:
            synchronize = str(job_id).lower() == request.address.lower() and reads < 2
            reads += int(synchronize)
        if synchronize:
            concurrent_reads.wait(timeout=2)
        return original_get_job(job_id)

    monkeypatch.setattr(journal, "get_job", synchronized_get_job)
    monkeypatch.setattr(api, "store", journal)
    responses = []
    errors = []

    def register():
        try:
            responses.append(api.register_wallet_job(request))
        except Exception as exc:
            errors.append(exc)

    first = Thread(target=register)
    second = Thread(target=register)
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert len(responses) == 2
    assert {response["job"]["address"] for response in responses} == {request.address}
    assert len(journal.list_jobs()) == 1


def test_wallet_registration_rejects_unverified_deployment_transaction(monkeypatch):
    request, _platform = _configure_valid_wallet_registration(monkeypatch)
    monkeypatch.setattr(
        api,
        "network_client",
        SimpleNamespace(get_transaction=lambda _tx: (_ for _ in ()).throw(RuntimeError("missing"))),
    )
    with pytest.raises(HTTPException) as exc:
        api.register_wallet_job(request)
    assert exc.value.detail["code"] == "DEPLOYMENT_TX_NOT_FOUND"


def test_wallet_registration_rejects_wrong_platform_recipient(monkeypatch):
    request, platform = _configure_valid_wallet_registration(monkeypatch)
    monkeypatch.setattr(api, "_job_state", lambda _address: {"job": {
        "client": request.client_address,
        "worker": request.worker_address,
        "platform": "0x" + "6" * 40,
        "spec": request.spec,
        "fee_bps": request.fee_bps,
        "min_score": request.min_score,
        "partial_floor": request.partial_floor,
        "status": "UNFUNDED",
    }})
    assert platform != "0x" + "6" * 40
    with pytest.raises(HTTPException) as exc:
        api.register_wallet_job(request)
    assert exc.value.detail["code"] == "CONTRACT_METADATA_MISMATCH"


def _wallet_funding_job() -> dict:
    return {
        **_record("0x" + "1" * 40),
        "client_address": "0x" + "2" * 40,
        "state_snapshot": {"status": "UNFUNDED"},
    }


def _accepted_funding_transaction(job: dict) -> dict:
    return {
        "status_name": "Accepted",
        "tx_execution_result_name": "SUCCESS",
        "recipient": job["address"],
        "sender": job["client_address"],
        "network": "testnet_bradbury",
        "tx_data_decoded": {"type": "call", "call_data": {"method": "fund"}},
    }


def test_register_wallet_funding_persists_verified_hash_and_returns_refreshed_open_status(monkeypatch, tmp_path):
    job = _wallet_funding_job()
    tx_hash = "0x" + "9" * 64
    journal = JobStore(tmp_path)
    journal.add_job(job)
    monkeypatch.setattr(api, "store", journal)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(
        get_transaction=lambda _tx: _accepted_funding_transaction(job)
    ))
    monkeypatch.setattr(api, "_job_state", lambda _address: {
        "job": {"status": "OPEN", "client": job["client_address"], "amount": 10**15},
        "result": {"status": "OPEN"},
    })

    response = api.register_wallet_funding(
        job["address"], api.RegisterWalletFundingRequest(transaction_hash=tx_hash)
    )

    assert response["tx"] == tx_hash
    assert response["job_status"] == "OPEN"
    assert journal.get_job(job["address"])["lifecycle_status"] == "OPEN"
    assert journal.latest_transaction_for_job(job["address"], "FUNDING")["tx_hash"] == tx_hash


def test_register_wallet_funding_keeps_finalized_hash_confirming_when_snapshot_is_unfunded(monkeypatch, tmp_path):
    job = _wallet_funding_job()
    tx_hash = "0x" + "8" * 64
    journal = JobStore(tmp_path)
    journal.add_job(job)
    transaction = {**_accepted_funding_transaction(job), "status_name": "Finalized"}
    monkeypatch.setattr(api, "store", journal)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(get_transaction=lambda _tx: transaction))
    monkeypatch.setattr(api, "_job_state", lambda _address: {
        "job": {"status": "UNFUNDED", "client": job["client_address"], "amount": 0},
        "result": {"status": "UNFUNDED"},
    })

    response = api.register_wallet_funding(
        job["address"], api.RegisterWalletFundingRequest(transaction_hash=tx_hash)
    )

    assert response["job_status"] == "UNFUNDED"
    assert journal.latest_transaction_for_job(job["address"], "FUNDING")["status"] == "FINALIZED"
    assert journal.get_job(job["address"])["lifecycle_status"] == "UNFUNDED"


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"sender": "0x" + "3" * 40}, "FUNDING_SIGNER_MISMATCH"),
        ({"recipient": "0x" + "4" * 40}, "FUNDING_CONTRACT_MISMATCH"),
        ({"network": "testnet_asimov"}, "FUNDING_NETWORK_MISMATCH"),
        ({"tx_data_decoded": {"type": "call", "call_data": {"method": "evaluate"}}}, "FUNDING_ACTION_MISMATCH"),
        ({"tx_execution_result_name": "FINISHED_WITH_ERROR"}, "FUNDING_TX_REJECTED"),
    ],
)
def test_register_wallet_funding_rejects_untrusted_transaction_identity(monkeypatch, changes, expected_code):
    job = _wallet_funding_job()
    transaction = {**_accepted_funding_transaction(job), **changes}
    monkeypatch.setattr(api, "_find_job", lambda _job_id: job)
    monkeypatch.setattr(api.store, "get_transaction", lambda *_args: None)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(get_transaction=lambda _tx: transaction))

    with pytest.raises(HTTPException) as exc:
        api.register_wallet_funding(
            job["address"],
            api.RegisterWalletFundingRequest(transaction_hash="0x" + "7" * 64),
        )

    assert exc.value.detail["code"] == expected_code


def test_register_wallet_funding_rejects_hash_attached_to_another_operation(monkeypatch, tmp_path):
    job = _wallet_funding_job()
    tx_hash = "0x" + "6" * 64
    journal = JobStore(tmp_path)
    journal.add_job(job)
    journal.record_transaction({
        "network": "testnet_bradbury",
        "tx_hash": tx_hash,
        "job_address": job["address"],
        "kind": "SETTLEMENT",
        "status": "ACCEPTED",
    })
    monkeypatch.setattr(api, "store", journal)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(
        get_transaction=lambda _tx: _accepted_funding_transaction(job)
    ))

    with pytest.raises(HTTPException) as exc:
        api.register_wallet_funding(
            job["address"], api.RegisterWalletFundingRequest(transaction_hash=tx_hash)
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "TRANSACTION_IDENTITY_CONFLICT"


def test_wallet_settlement_registration_persists_activated_transaction(monkeypatch):
    tx_hash = "0x" + "9" * 64
    job = {
        **_record("0x" + "1" * 40),
        "client_address": "0x" + "2" * 40,
        "settlement": {},
    }
    transaction = {
        "status_name": "Activated",
        "recipient": job["address"],
        "sender": job["client_address"],
        "activator": "0x" + "8" * 40,
        "tx_data_decoded": {"type": "call", "call_data": {"method": "finalize"}},
    }
    monkeypatch.setattr(api, "_find_job", lambda _job_id: job)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(get_transaction=lambda _tx: transaction))
    monkeypatch.setattr(api, "_job_state", lambda _address: {"job": {
        "status": "SETTLEMENT_PENDING",
        "settlement": {"outcome": "REFUNDED", "transfer_status": "PENDING_FINALIZATION"},
    }})
    saved = {}
    monkeypatch.setattr(api.store, "update_job", lambda _address, **changes: saved.update(changes))
    monkeypatch.setattr(api.store, "get_transaction", lambda *_args: None)
    monkeypatch.setattr(api.store, "record_transaction", lambda record: record)
    monkeypatch.setattr(api, "_refresh_settlement", lambda meta, _chain_job: meta["settlement"])

    response = api.register_wallet_settlement(
        job["address"], api.RegisterWalletSettlementRequest(transaction_hash=tx_hash)
    )

    assert saved["settlement"]["parent_transaction"] == tx_hash
    assert saved["settlement"]["parent_status"] == "ACTIVATED"
    assert response["status"] == "PENDING_FINALIZATION"


def test_wallet_settlement_registration_rejects_non_finalize_action(monkeypatch):
    tx_hash = "0x" + "8" * 64
    job = {
        **_record("0x" + "1" * 40),
        "client_address": "0x" + "2" * 40,
        "settlement": {},
    }
    monkeypatch.setattr(api, "_find_job", lambda _job_id: job)
    monkeypatch.setattr(api.store, "get_transaction", lambda *_args: None)
    monkeypatch.setattr(api.store, "record_transaction", lambda record: record)
    monkeypatch.setattr(api.store, "update_job", lambda *_args, **_kwargs: job)
    monkeypatch.setattr(api, "_refresh_settlement", lambda meta, _chain_job: meta["settlement"])
    monkeypatch.setattr(api, "_job_state", lambda _address: {"job": {
        "status": "SETTLEMENT_PENDING",
        "settlement": {"outcome": "REFUNDED", "transfer_status": "PENDING_FINALIZATION"},
    }})
    monkeypatch.setattr(api, "network_client", SimpleNamespace(get_transaction=lambda _tx: {
        "status_name": "Activated",
        "recipient": job["address"],
        "sender": job["client_address"],
        "network": "testnet_bradbury",
        "tx_data_decoded": {"type": "call", "call_data": {"method": "evaluate"}},
    }))

    with pytest.raises(HTTPException) as exc:
        api.register_wallet_settlement(
            job["address"], api.RegisterWalletSettlementRequest(transaction_hash=tx_hash)
        )

    assert exc.value.detail["code"] == "SETTLEMENT_ACTION_MISMATCH"


def test_settlement_transaction_identity_conflict_cannot_attach_to_another_job(monkeypatch, tmp_path):
    job_a = {
        **_record("0x" + "1" * 40),
        "client_address": "0x" + "2" * 40,
        "settlement": {},
    }
    job_b = {
        **_record("0x" + "3" * 40),
        "client_address": job_a["client_address"],
        "settlement": {},
    }
    tx_hash = "0x" + "9" * 64
    journal = JobStore(tmp_path)
    journal.add_job(job_a)
    journal.add_job(job_b)
    monkeypatch.setattr(api, "store", journal)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(get_transaction=lambda _tx: {
        "status_name": "Activated",
        "recipient": job_a["address"],
        "sender": job_a["client_address"],
        "network": "testnet_bradbury",
        "tx_data_decoded": {"type": "call", "call_data": {"method": "finalize"}},
    }))
    monkeypatch.setattr(api, "_job_state", lambda _address: {"job": {
        "status": "SETTLEMENT_PENDING",
        "settlement": {"outcome": "REFUNDED", "transfer_status": "PENDING_FINALIZATION"},
    }})
    monkeypatch.setattr(api, "_refresh_settlement", lambda meta, _chain_job: meta["settlement"])

    api.register_wallet_settlement(
        job_a["address"], api.RegisterWalletSettlementRequest(transaction_hash=tx_hash)
    )
    with pytest.raises(HTTPException) as exc:
        api.register_wallet_settlement(
            job_b["address"], api.RegisterWalletSettlementRequest(transaction_hash=tx_hash)
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "TRANSACTION_IDENTITY_CONFLICT"


def test_wallet_settlement_registration_rejects_wrong_client(monkeypatch):
    job = {
        **_record("0x" + "1" * 40),
        "client_address": "0x" + "2" * 40,
    }
    monkeypatch.setattr(api, "_find_job", lambda _job_id: job)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(get_transaction=lambda _tx: {
        "status_name": "Accepted",
        "recipient": job["address"],
        "sender": "0x" + "3" * 40,
        "activator": job["client_address"],
    }))

    with pytest.raises(HTTPException) as exc:
        api.register_wallet_settlement(
            job["address"],
            api.RegisterWalletSettlementRequest(transaction_hash="0x" + "9" * 64),
        )

    assert exc.value.detail["code"] == "SETTLEMENT_SIGNER_MISMATCH"


def test_wallet_settlement_registration_rejects_missing_wallet_signer(monkeypatch):
    job = {
        **_record("0x" + "1" * 40),
        "client_address": "0x" + "2" * 40,
    }
    monkeypatch.setattr(api, "_find_job", lambda _job_id: job)
    monkeypatch.setattr(api, "network_client", SimpleNamespace(get_transaction=lambda _tx: {
        "status_name": "Finalized",
        "recipient": job["address"],
        # A Bradbury activator is not evidence of the wallet that signed the
        # transaction, so it must not be accepted as a signer fallback.
        "activator": job["client_address"],
    }))

    with pytest.raises(HTTPException) as exc:
        api.register_wallet_settlement(
            job["address"], api.RegisterWalletSettlementRequest(transaction_hash="0x" + "9" * 64),
        )

    assert exc.value.detail["code"] == "SETTLEMENT_SIGNER_UNAVAILABLE"


def test_wait_tolerates_unknown_bradbury_intermediate_status(monkeypatch):
    class FakeProvider:
        def __init__(self):
            self.statuses = iter(["Activated", "Accepted"])

        def make_request(self, *, method, params):
            assert method == "gen_getTransactionStatus"
            assert params == [{"txId": "0xtx"}]
            return {"result": {"status": next(self.statuses), "statusCode": 14}}

    class FakeClient:
        provider = FakeProvider()

        def get_transaction(self, transaction_hash):
            assert transaction_hash == "0xtx"
            return {
                "status_name": TransactionStatus.ACCEPTED,
                "tx_execution_result_name": "SUCCESS",
            }

    monkeypatch.setattr(api, "network_client", FakeClient())
    monkeypatch.setattr(api.time, "sleep", lambda _seconds: None)
    receipt = api._wait("0xtx")
    assert receipt["status_name"] == TransactionStatus.ACCEPTED


def test_wait_classifies_out_of_fee_as_insufficient_demo_gen(monkeypatch):
    class FakeProvider:
        def make_request(self, **_kwargs):
            return {"result": {"status": "Out of fee", "statusCode": 14}}

    monkeypatch.setattr(api, "network_client", SimpleNamespace(provider=FakeProvider()))
    with pytest.raises(RuntimeError, match="Insufficient demo GEN"):
        api._wait("0xtx")


@pytest.mark.parametrize(
    ("parent_status", "messages", "triggered", "expected"),
    [
        ("ACCEPTED", [[0, "0xclient", 1000, "0x", False, 0]], [], "PENDING_FINALIZATION"),
        ("FINALIZED", [], [], "PENDING_TRANSFER_RECORD"),
        ("FINALIZED", [[0, "0xother", 1000, "0x", False, 0]], [], "PENDING_TRANSFER_RECORD"),
        ("FINALIZED", [[0, "0xclient", 1000, "0x", False, 0]], [], "FINALIZED"),
        ("FINALIZED", [], ["0xchild"], "FINALIZED"),
    ],
)
def test_settlement_requires_inspectable_transfer_record(
    monkeypatch, parent_status, messages, triggered, expected
):
    class FakeClient:
        def get_transaction(self, _transaction):
            return {"status": parent_status, "messages": messages}

        def get_triggered_transaction_ids(self, _transaction):
            return triggered

    monkeypatch.setattr(api, "network_client", FakeClient())
    monkeypatch.setattr(api.store, "update_job", lambda *_args, **_kwargs: None)
    settlement = api._refresh_settlement(
        {
            "address": "0xescrow",
            "settlement": {"parent_transaction": "0xparent"},
        },
        {
            "settlement": {
                "transfers": [
                    {
                        "recipient": "0xclient",
                        "amount": 1000,
                        "settlement_type": "CLIENT_REFUND",
                    }
                ]
            }
        },
    )
    assert settlement["transfer_status"] == expected
    if triggered:
        assert settlement["transfer_reference"] == ["0xchild"]
        assert settlement["explorer"].endswith("/tx/0xchild")
        assert settlement["transfer_evidence"] == [
            {
                "reference": "0xchild",
                "status": "CONFIRMED",
                "explorer": "https://explorer-bradbury.genlayer.com/tx/0xchild",
                "recipient_role": "client",
                "recipient": "0xclient",
                "amount": 1000,
                "settlement_type": "CLIENT_REFUND",
            }
        ]
    elif expected == "FINALIZED":
        assert settlement["confirmation_basis"] == "FINALIZED_EXTERNAL_MESSAGE"
        assert settlement["transfer_reference"] == ["0xparent"]
        assert settlement["transfer_evidence"][0]["recipient"] == "0xclient"
        assert settlement["transfer_evidence"][0]["amount"] == 1000


def test_finalized_messages_recover_stale_zero_value_contract_snapshot(monkeypatch):
    class FakeClient:
        def get_transaction(self, _transaction):
            return {
                "status": "FINALIZED",
                "messages": [
                    [0, "0xworker", 700, "0x", False, 0],
                    [0, "0xclient", 290, "0x", False, 0],
                    [0, "0xplatform", 10, "0x", False, 0],
                ],
            }

        def get_triggered_transaction_ids(self, _transaction):
            return []

    monkeypatch.setattr(api, "network_client", FakeClient())
    monkeypatch.setattr(api.store, "update_job", lambda *_args, **_kwargs: None)
    settlement = api._refresh_settlement(
        {
            "address": "0xescrow",
            "settlement": {
                "parent_transaction": "0xparent",
                "outcome": "",
                "transfers": [
                    {"recipient": "0xworker", "amount": 0, "settlement_type": "WORKER_PAYOUT"},
                    {"recipient": "0xclient", "amount": 0, "settlement_type": "CLIENT_REFUND"},
                ],
            },
        },
        {
            "worker": "0xworker",
            "client": "0xclient",
            "platform": "0xplatform",
            "settlement": {"outcome": "", "transfers": []},
        },
    )
    assert settlement["transfer_status"] == "FINALIZED"
    assert settlement["outcome"] == "PARTIAL"
    assert settlement["confirmation_basis"] == "FINALIZED_EXTERNAL_MESSAGE"
    assert settlement["transfers"][0] == {
        "recipient": "0xworker",
        "amount": 700,
        "settlement_type": "WORKER_PAYOUT",
    }
