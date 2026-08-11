from types import SimpleNamespace
import time
from threading import Barrier, Lock, Thread

import pytest
from fastapi import HTTPException

from dashboard.store import JobStore
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
