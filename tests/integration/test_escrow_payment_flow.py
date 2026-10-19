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
import os

import pytest
from gltest import create_account

from bradbury_helpers import (
    balance, committed, deploy, open_job, requires_testnet, send, view, wait_for_balance_change,
    worker_account,
)


AMOUNT = int(os.environ.get("ESCROW_AMOUNT", str(10**16)))
FEE_BPS = 200
MIN_SCORE = 70

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

pytestmark = requires_testnet


@pytest.fixture
def parties():
    return worker_account(), create_account()


def _evaluated_job(worker, platform, detector=None):
    escrow, receipt, result = open_job(SPEC, worker, platform, URL, AMOUNT, FEE_BPS, MIN_SCORE, detector=detector)
    committed(receipt)
    print(f"\n  escrow {escrow.address} evaluated: score={result.get('score')} status={result.get('status')}")
    assert result["status"] == "EVALUATED", result
    assert result["score"] >= MIN_SCORE, f"Expected a passing score for {URL}: {result}"
    return escrow


class TestEscrowPaymentFlow:

    def test_accepted_work_pays_worker_and_platform(self, parties):
        worker, platform = parties
        escrow = _evaluated_job(worker, platform)

        worker_before = balance(worker)
        committed(send(escrow.finalize))

        job = view(escrow, "get_job")
        fee = AMOUNT * FEE_BPS // 10000
        worker_after = wait_for_balance_change(worker, worker_before)
        print(f"  settlement: {job['settlement']['outcome']} worker+{worker_after - worker_before} platform+{balance(platform)}")
        assert job["settlement"]["outcome"] == "ACCEPTED"
        assert job["amount"] == 0
        assert worker_after - worker_before == AMOUNT - fee
        assert balance(platform) == fee

    def test_drifted_worker_payout_is_held(self, parties):
        worker, platform = parties
        detector = deploy("value_drift_detector.py", [str(worker.address), MANDATE, [], False, 0, 80])
        escrow = _evaluated_job(worker, platform, detector=detector)

        committed(send(detector.submit_evidence, ["text", EVIDENCE_DRIFT, "testnet flow"]))
        committed(send(detector.trigger_review))
        drift_status = view(detector, "get_status")["status"]
        print(f"  detector: {drift_status}")
        assert drift_status in ("DRIFTED", "REVOKED")

        worker_before = balance(worker)
        committed(send(escrow.finalize))

        job = view(escrow, "get_job")
        print(f"  after finalize: {job['status']} gate={job['drift_gate']}")
        assert job["status"] == "EVALUATED"
        assert job["amount"] == AMOUNT
        assert job["drift_gate"]["hold_since"] != ""
        assert job["drift_gate"]["last_status"] == drift_status
        assert balance(worker) == worker_before
