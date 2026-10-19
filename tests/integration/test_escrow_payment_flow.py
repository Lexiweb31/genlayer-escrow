"""
End-to-end payment flow for freelance_escrow.py on a network that can move GEN.

The v0.79.1 localnet rejects any transaction carrying value, so this runs only
against testnet:

    # .env
    DEPLOYER_PRIVATE_KEY=0x...   # client: deploys, funds, links the detector
    WORKER_PRIVATE_KEY=0x...     # worker: accepts terms and submits work

    gltest tests/integration/test_escrow_payment_flow.py -v -s --network testnet_bradbury

Use throwaway wallets. Both need testnet GEN for gas; the client also needs
ESCROW_AMOUNT (wei, default 0.01 GEN) per test.
"""
import json
import os

import pytest
from eth_utils import to_bytes
from genlayer_py.types.calldata import CalldataAddress

from gltest import create_account, get_contract_factory, get_default_account, get_gl_client
from gltest.assertions import tx_execution_succeeded
from gltest.types import TransactionStatus
from gltest_cli.config.general import get_general_config


NETWORK = get_general_config().get_network_name()
WORKER_KEY = os.environ.get("WORKER_PRIVATE_KEY", "")
AMOUNT = int(os.environ.get("ESCROW_AMOUNT", str(10**16)))
FEE_BPS = 200
MIN_SCORE = 70
FLOOR = 40

# example.com is stable and says exactly this, so a fair judge scores it high.
SPEC = (
    "A single web page stating that the domain is reserved for use in "
    "documentation examples and may be used without asking for permission."
)
URL = "https://example.com"

MANDATE = "Deliver documentation pages only. Never touch client funds or trade assets."
EVIDENCE_DRIFT = (
    "Activity log: agent moved the client's entire treasury into a 10x leveraged "
    "perpetual position on a new token and stopped producing documentation."
)

pytestmark = pytest.mark.skipif(
    not NETWORK.startswith("testnet") or not WORKER_KEY,
    reason="needs --network testnet_* and WORKER_PRIVATE_KEY (localnet can't move GEN)",
)

# Settlement transfers are child transactions that run after finalize() is
# itself finalized, which on testnet includes the appeal window.
WAIT = dict(wait_interval=10000, wait_retries=120)


def _addr(account) -> CalldataAddress:
    return CalldataAddress(to_bytes(hexstr=str(account.address)))


def _balance(account) -> int:
    return int(get_gl_client().get_balance(account.address))


def _committed(receipt) -> None:
    assert tx_execution_succeeded(receipt), receipt


def _open_job(worker, platform):
    """Client deploys the escrow (unfunded)."""
    return get_contract_factory(contract_file_path="freelance_escrow.py").deploy(
        args=[SPEC, _addr(worker), _addr(platform), FEE_BPS, MIN_SCORE, FLOOR], **WAIT
    )


def _fund_and_submit(escrow, worker):
    """Client funds; worker accepts terms and submits; the work is evaluated."""
    _committed(escrow.fund(args=[]).transact(value=AMOUNT, **WAIT))
    as_worker = escrow.connect(worker)
    _committed(as_worker.accept_terms(args=[]).transact(**WAIT))
    _committed(as_worker.submit_work(args=[URL]).transact(**WAIT))
    _committed(escrow.evaluate(args=[]).transact(**WAIT))
    result = json.loads(escrow.get_result(args=[]).call())
    print(f"\n  evaluated: score={result.get('score')} status={result.get('status')}")
    assert result["status"] == "EVALUATED", result
    assert result["score"] >= MIN_SCORE, f"Expected a passing score for {URL}: {result}"


@pytest.fixture
def parties():
    worker = create_account(WORKER_KEY)
    assert worker.address.lower() != get_default_account().address.lower(), (
        "WORKER_PRIVATE_KEY must differ from DEPLOYER_PRIVATE_KEY"
    )
    return worker, create_account()


class TestEscrowPaymentFlow:

    def test_accepted_work_pays_worker_and_platform(self, parties):
        worker, platform = parties
        escrow = _open_job(worker, platform)
        _fund_and_submit(escrow, worker)

        worker_before = _balance(worker)
        receipt = escrow.finalize(args=[]).transact(
            wait_transaction_status=TransactionStatus.FINALIZED,
            wait_triggered_transactions=True,
            wait_triggered_transactions_status=TransactionStatus.FINALIZED,
            **WAIT,
        )
        _committed(receipt)

        job = json.loads(escrow.get_job(args=[]).call())
        fee = AMOUNT * FEE_BPS // 10000
        print(f"  settlement: {job['settlement']['outcome']} worker+{_balance(worker) - worker_before}")
        assert job["settlement"]["outcome"] == "ACCEPTED"
        assert job["amount"] == 0
        assert _balance(worker) - worker_before == AMOUNT - fee
        assert _balance(platform) == fee

    def test_drifted_worker_payout_is_held(self, parties):
        worker, platform = parties
        detector = get_contract_factory(contract_file_path="value_drift_detector.py").deploy(
            args=[_addr(worker), MANDATE, [], False, 0, 80], **WAIT
        )
        escrow = _open_job(worker, platform)
        _committed(escrow.link_drift_detector(args=[_addr(detector), 3600]).transact(**WAIT))
        _fund_and_submit(escrow, worker)

        _committed(detector.submit_evidence(args=["text", EVIDENCE_DRIFT, "testnet flow"]).transact(**WAIT))
        _committed(detector.trigger_review(args=[]).transact(**WAIT))
        drift_status = json.loads(detector.get_status(args=[]).call())["status"]
        print(f"  detector: {drift_status}")
        assert drift_status in ("DRIFTED", "REVOKED")

        worker_before = _balance(worker)
        _committed(escrow.finalize(args=[]).transact(**WAIT))

        job = json.loads(escrow.get_job(args=[]).call())
        print(f"  after finalize: {job['status']} gate={job['drift_gate']}")
        assert job["status"] == "EVALUATED"
        assert job["amount"] == AMOUNT
        assert job["drift_gate"]["hold_since"] != ""
        assert job["drift_gate"]["last_status"] == drift_status
        assert _balance(worker) == worker_before
