from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from dashboard.store import JobStore
import dashboard.api as api
from genlayer_py.types.transactions import TransactionStatus


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


def test_sqlite_jobs_survive_store_reopen(tmp_path):
    first = JobStore(tmp_path)
    first.add_job(_record())
    first.update_job(
        "0xabc",
        lifecycle_status="SETTLEMENT_PENDING",
        settlement={"transfer_status": "PENDING_FINALIZATION", "parent_transaction": "0xfinalize"},
    )

    restarted = JobStore(tmp_path)
    job = restarted.get_job("0xABC")
    assert job is not None
    assert job["client_address"] == "0xclient"
    assert job["worker_address"] == "0xworker"
    assert job["deployment_tx"] == "0xdeploy"
    assert job["lifecycle_status"] == "SETTLEMENT_PENDING"
    assert job["settlement"]["parent_transaction"] == "0xfinalize"


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
    monkeypatch.setattr(api.store, "list_jobs", lambda: [record])
    monkeypatch.setattr(api.store, "update_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api,
        "_job_state",
        lambda _address: {
            "job": {
                "status": "SUBMITTED",
                "amount": 1,
                "settlement": {"transfer_status": "NOT_STARTED", "transfers": []},
            },
            # Some contract readers expose the default numeric score before an
            # evaluation. The marketplace must not treat it as a real result.
            "result": {"score": 0, "status": "SUBMITTED"},
        },
    )
    response = api.list_jobs()
    assert response["jobs"][0]["amount"] == "1"
    assert response["jobs"][0]["evaluation_complete"] is False
    assert response["jobs"][0]["score"] is None
    assert response["stats"]["locked_wei"] == "1"


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
