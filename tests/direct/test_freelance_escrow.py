"""
Direct-mode tests for freelance_escrow.py.
Run with:
    pytest tests/direct/test_freelance_escrow.py -v
"""
import json
import pytest
from pathlib import Path
from gltest.direct.loader import create_address

_CONTRACT = Path(__file__).parents[2] / "contracts" / "freelance_escrow.py"


def _addr(name: str):
    """Return an Address for the given seed, priming the SDK if needed."""
    from gltest.direct.sdk_loader import setup_sdk_paths
    setup_sdk_paths(contract_path=_CONTRACT.resolve(), version="v0.2.16")
    return create_address(name)

# ── Constants ─────────────────────────────────────────────────────────────────

SPEC = (
    "Build a landing page for a fintech startup. Must include: "
    "a hero section with headline and CTA button, "
    "a features section with at least 3 items, "
    "and a footer with contact email."
)

MOCK_PAGE_COMPLETE = """
<html><body>
  <section class="hero"><h1>Send Money Fast</h1><button>Get Started</button></section>
  <section class="features">
    <div>Fast Transfers</div><div>Zero Fees</div><div>Bank Security</div>
  </section>
  <footer>Contact: hello@fintech.io</footer>
</body></html>
"""

MOCK_PAGE_EMPTY = "<html><body><h1>Coming Soon</h1></body></html>"

_WEB_OK = {"method": "GET", "status": 200}

FEE_BPS  = 200   # 2%
AMOUNT   = 1000  # native tokens


def _llm_accepted(score=90):
    return json.dumps({
        "verdict": "ACCEPTED",
        "score": score,
        "reasoning": "The deliverable meets all spec requirements.",
    })


def _llm_rejected(score=15):
    return json.dumps({
        "verdict": "REJECTED",
        "score": score,
        "reasoning": "The deliverable is missing required sections.",
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deploy(direct_deploy, direct_vm, worker, platform):
    return direct_deploy(
        "contracts/freelance_escrow.py",
        SPEC,
        worker,
        platform,
        FEE_BPS,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestFreelanceEscrow:

    def test_initial_state_is_unfunded(self, direct_deploy, direct_vm):
        """Freshly deployed contract should be UNFUNDED."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        job = json.loads(contract.get_job())
        assert job["status"] == "UNFUNDED"
        assert job["amount"] == 0
        assert job["fee_bps"] == FEE_BPS

    def test_fund_opens_job(self, direct_deploy, direct_vm):
        """Client calling fund() with value should move status to OPEN."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        direct_vm.value = AMOUNT
        contract.fund()
        direct_vm.value = 0

        job = json.loads(contract.get_job())
        assert job["status"] == "OPEN"
        assert job["amount"] == AMOUNT

    def test_non_client_cannot_fund(self, direct_deploy, direct_vm):
        """A stranger calling fund() should be rejected."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        original_sender = direct_vm.sender
        direct_vm.sender = _addr("stranger")
        direct_vm.value  = AMOUNT
        with pytest.raises(Exception):
            contract.fund()
        direct_vm.sender = original_sender
        direct_vm.value  = 0

    def test_worker_submits_url(self, direct_deploy, direct_vm):
        """Worker submitting a URL should move status to SUBMITTED."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        direct_vm.value = AMOUNT
        contract.fund()
        direct_vm.value = 0

        direct_vm.sender = worker
        contract.submit_work("http://mydeliverable.example.com")
        direct_vm.sender = _addr("default_sender")

        job = json.loads(contract.get_job())
        assert job["status"] == "SUBMITTED"

    def test_stranger_cannot_submit(self, direct_deploy, direct_vm):
        """A non-worker address calling submit_work() should be rejected."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        direct_vm.value = AMOUNT
        contract.fund()
        direct_vm.value = 0

        direct_vm.sender = _addr("stranger")
        with pytest.raises(Exception):
            contract.submit_work("http://example.com")
        direct_vm.sender = _addr("default_sender")

    def test_evaluate_accepted_pays_worker(self, direct_deploy, direct_vm):
        """
        ACCEPTED verdict should move status to ACCEPTED.
        The escrow amount should be zeroed out (payout emitted).
        """
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        direct_vm.value = AMOUNT
        contract.fund()
        direct_vm.value = 0

        direct_vm.sender = worker
        contract.submit_work("http://mydeliverable.example.com")
        direct_vm.sender = _addr("default_sender")

        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm_accepted(score=88))
        contract.evaluate()

        result = json.loads(contract.get_result())
        assert result["status"]  == "ACCEPTED"
        assert result["verdict"] == "ACCEPTED"
        assert result["score"]   >= 70

        # Escrow balance zeroed — payout emitted to worker
        job = json.loads(contract.get_job())
        assert job["amount"] == 0

    def test_evaluate_rejected_refunds_client(self, direct_deploy, direct_vm):
        """REJECTED verdict should move status to REFUNDED and zero the escrow."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        direct_vm.value = AMOUNT
        contract.fund()
        direct_vm.value = 0

        direct_vm.sender = worker
        contract.submit_work("http://mydeliverable.example.com")
        direct_vm.sender = _addr("default_sender")

        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_EMPTY})
        direct_vm.mock_llm(".*", _llm_rejected(score=10))
        contract.evaluate()

        result = json.loads(contract.get_result())
        assert result["status"]  == "REFUNDED"
        assert result["verdict"] == "REJECTED"

        job = json.loads(contract.get_job())
        assert job["amount"] == 0

    def test_cannot_evaluate_before_submission(self, direct_deploy, direct_vm):
        """Calling evaluate() before submit_work() should raise."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        direct_vm.value = AMOUNT
        contract.fund()
        direct_vm.value = 0

        with pytest.raises(Exception):
            contract.evaluate()

    def test_cannot_submit_before_funding(self, direct_deploy, direct_vm):
        """Calling submit_work() before fund() should raise."""
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = _deploy(direct_deploy, direct_vm, worker, platform)

        direct_vm.sender = worker
        with pytest.raises(Exception):
            contract.submit_work("http://example.com")
        direct_vm.sender = _addr("default_sender")
