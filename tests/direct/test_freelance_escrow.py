"""
Direct-mode tests for freelance_escrow.py (Phase 2).
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


# ── Constants ──────────────────────────────────────────────────────────────────

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

MOCK_PAGE_PARTIAL = """
<html><body>
  <h1>Welcome to FinApp</h1><button>Sign Up</button>
  <div>Fast Transfers</div>
</body></html>
"""

MOCK_PAGE_EMPTY = "<html><body><h1>Coming Soon</h1></body></html>"

_WEB_OK   = {"method": "GET", "status": 200}
FEE_BPS   = 200   # 2%
MIN_SCORE = 70
FLOOR     = 40
AMOUNT    = 10000


def _llm(score: int):
    verdict = "ACCEPTED" if score >= MIN_SCORE else "REJECTED"
    return json.dumps({
        "verdict": verdict,
        "score": score,
        "reasoning": f"Score {score} — deliverable quality assessment.",
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _setup(direct_deploy, direct_vm, *, with_terms=True, with_submission=True, url="http://example.com"):
    """Deploy → fund → (accept_terms) → (submit_work). Returns (contract, worker, client)."""
    worker   = _addr("worker")
    platform = _addr("platform")
    client   = _addr("default_sender")

    contract = direct_deploy(
        str(_CONTRACT),
        SPEC, worker, platform, FEE_BPS,
        MIN_SCORE, FLOOR,
    )

    # Fund
    direct_vm.value = AMOUNT
    contract.fund()
    direct_vm.value = 0

    if with_terms:
        direct_vm.sender = worker
        contract.accept_terms()
        direct_vm.sender = client

    if with_terms and with_submission:
        direct_vm.sender = worker
        contract.submit_work(url)
        direct_vm.sender = client

    return contract, worker, client


# ── Tests: state machine ──────────────────────────────────────────────────────

class TestStateMachine:

    def test_initial_state_unfunded(self, direct_deploy, direct_vm):
        worker   = _addr("worker")
        platform = _addr("platform")
        contract = direct_deploy(str(_CONTRACT), SPEC, worker, platform, FEE_BPS, MIN_SCORE, FLOOR)
        job = json.loads(contract.get_job())
        assert job["status"]        == "UNFUNDED"
        assert job["min_score"]     == MIN_SCORE
        assert job["partial_floor"] == FLOOR
        assert job["terms_agreed"]  is False
        assert job["settlement"]["transfer_status"] == "NOT_STARTED"

    def test_client_and_worker_must_be_different(self, direct_deploy, direct_vm):
        client = _addr("default_sender")
        with pytest.raises(Exception):
            direct_deploy(
                str(_CONTRACT), SPEC, client, _addr("platform"), FEE_BPS,
                MIN_SCORE, FLOOR,
            )

    def test_fund_moves_to_open(self, direct_deploy, direct_vm):
        contract, _, _ = _setup(direct_deploy, direct_vm, with_terms=False, with_submission=False)
        assert json.loads(contract.get_job())["status"] == "OPEN"

    def test_accept_terms_moves_to_agreed(self, direct_deploy, direct_vm):
        contract, _, _ = _setup(direct_deploy, direct_vm, with_terms=True, with_submission=False)
        job = json.loads(contract.get_job())
        assert job["status"]       == "AGREED"
        assert job["terms_agreed"] is True

    def test_submit_moves_to_submitted(self, direct_deploy, direct_vm):
        contract, _, _ = _setup(direct_deploy, direct_vm)
        assert json.loads(contract.get_job())["status"] == "SUBMITTED"

    def test_evaluate_moves_to_evaluated(self, direct_deploy, direct_vm):
        contract, _, _ = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(85))
        contract.evaluate()
        result = json.loads(contract.get_result())
        assert result["status"] == "EVALUATED"
        assert result["score"]  == 85


# ── Tests: accept_terms guards ────────────────────────────────────────────────

class TestAcceptTerms:

    def test_stranger_cannot_accept(self, direct_deploy, direct_vm):
        contract, _, client = _setup(direct_deploy, direct_vm, with_terms=False, with_submission=False)
        direct_vm.sender = _addr("stranger")
        with pytest.raises(Exception):
            contract.accept_terms()
        direct_vm.sender = client

    def test_cannot_submit_without_accepting(self, direct_deploy, direct_vm):
        contract, worker, client = _setup(direct_deploy, direct_vm, with_terms=False, with_submission=False)
        direct_vm.sender = worker
        with pytest.raises(Exception):
            contract.submit_work("http://example.com")
        direct_vm.sender = client


# ── Tests: finalize — full payment ────────────────────────────────────────────

class TestFullPayment:

    def test_score_above_min_gives_accepted(self, direct_deploy, direct_vm):
        """Full payout is recorded and remains pending until the parent finalizes."""
        contract, worker, _ = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(88))
        contract.evaluate()
        contract.finalize()
        result = json.loads(contract.get_result())
        assert result["status"] == "SETTLEMENT_PENDING"
        assert result["settlement_outcome"] == "ACCEPTED"
        job = json.loads(contract.get_job())
        settlement = job["settlement"]
        assert job["amount"] == 0
        assert settlement["settlement_type"] == "FULL_WORKER_PAYOUT"
        assert settlement["transfer_status"] == "PENDING_FINALIZATION"
        assert settlement["transfers"][0] == {
            "recipient": str(worker),
            "amount": 9800,
            "settlement_type": "WORKER_PAYOUT",
        }
        assert settlement["transfers"][1]["amount"] == 0
        assert settlement["transfers"][2]["amount"] == 200

    def test_exact_min_score_accepted(self, direct_deploy, direct_vm):
        """score exactly equal to min_score → ACCEPTED."""
        contract, _, _ = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(MIN_SCORE))
        contract.evaluate()
        contract.finalize()
        result = json.loads(contract.get_result())
        assert result["status"] == "SETTLEMENT_PENDING"
        assert result["settlement_outcome"] == "ACCEPTED"


# ── Tests: finalize — partial payment ─────────────────────────────────────────

class TestPartialPayment:

    def test_score_between_floor_and_min_gives_partial(self, direct_deploy, direct_vm):
        """FLOOR <= score < min_score records every leg of the split."""
        contract, worker, client = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_PARTIAL})
        direct_vm.mock_llm(".*", _llm(55))   # 55 is between 40 and 70
        contract.evaluate()
        contract.finalize()
        result = json.loads(contract.get_result())
        assert result["status"] == "SETTLEMENT_PENDING"
        assert result["settlement_outcome"] == "PARTIAL"
        job = json.loads(contract.get_job())
        settlement = job["settlement"]
        worker_share = (AMOUNT * 55) // MIN_SCORE
        fee = (worker_share * FEE_BPS) // 10000
        assert job["amount"] == 0
        assert settlement["settlement_type"] == "PROPORTIONAL_SPLIT"
        assert settlement["transfer_status"] == "PENDING_FINALIZATION"
        assert settlement["transfers"][0]["recipient"] == str(worker)
        assert settlement["transfers"][0]["amount"] == worker_share - fee
        assert settlement["transfers"][2]["amount"] == fee
        assert settlement["transfers"][1] == {
            "recipient": str(client),
            "amount": AMOUNT - worker_share,
            "settlement_type": "CLIENT_REFUND",
        }

    def test_exact_partial_floor_gives_partial(self, direct_deploy, direct_vm):
        """score exactly at partial_floor → PARTIAL (not REFUNDED)."""
        contract, _, _ = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_PARTIAL})
        direct_vm.mock_llm(".*", _llm(FLOOR))
        contract.evaluate()
        contract.finalize()
        result = json.loads(contract.get_result())
        assert result["status"] == "SETTLEMENT_PENDING"
        assert result["settlement_outcome"] == "PARTIAL"


# ── Tests: finalize — full refund ─────────────────────────────────────────────

class TestRefund:

    def test_score_below_floor_gives_refund(self, direct_deploy, direct_vm):
        """score < partial_floor queues a full EOA refund and stays pending."""
        contract, _, client = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_EMPTY})
        direct_vm.mock_llm(".*", _llm(10))
        contract.evaluate()
        contract.finalize()
        result = json.loads(contract.get_result())
        assert result["status"] == "SETTLEMENT_PENDING"
        assert result["settlement_outcome"] == "REFUNDED"
        job = json.loads(contract.get_job())
        settlement = job["settlement"]
        assert job["amount"] == 0
        assert settlement["settlement_type"] == "FULL_CLIENT_REFUND"
        assert settlement["transfer_status"] == "PENDING_FINALIZATION"
        assert settlement["transfers"][0]["amount"] == 0
        assert settlement["transfers"][2]["amount"] == 0
        assert settlement["transfers"][1] == {
            "recipient": str(client),
            "amount": AMOUNT,
            "settlement_type": "CLIENT_REFUND",
        }


# ── Tests: appeal ─────────────────────────────────────────────────────────────

class TestAppeal:

    def test_client_can_appeal_after_evaluation(self, direct_deploy, direct_vm):
        """Client appeals an unfair REJECTED verdict — new score stored."""
        contract, _, client = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(30))     # initial: low score
        contract.evaluate()
        assert json.loads(contract.get_result())["score"] == 30

        # Appeal: clear old mocks and set new ones before re-evaluation
        direct_vm.clear_mocks()
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(82))     # second eval: high score
        direct_vm.sender = client
        contract.appeal()
        direct_vm.sender = client

        result = json.loads(contract.get_result())
        assert result["score"]  == 82
        assert result["status"] == "EVALUATED"   # still pending finalize
        assert json.loads(contract.get_job())["appeal_used"] is True

    def test_worker_can_appeal(self, direct_deploy, direct_vm):
        """Worker appeals a REJECTED verdict."""
        contract, worker, client = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(20))
        contract.evaluate()

        direct_vm.clear_mocks()
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(75))
        direct_vm.sender = worker
        contract.appeal()
        direct_vm.sender = client

        assert json.loads(contract.get_result())["score"] == 75

    def test_only_one_appeal_allowed(self, direct_deploy, direct_vm):
        """Second appeal call should raise."""
        contract, _, client = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(20))
        contract.evaluate()

        direct_vm.clear_mocks()
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(75))
        direct_vm.sender = client
        contract.appeal()

        # Second appeal should fail (appeal_used is now True)
        with pytest.raises(Exception):
            contract.appeal()
        direct_vm.sender = client

    def test_stranger_cannot_appeal(self, direct_deploy, direct_vm):
        """Random address should not be able to appeal."""
        contract, _, client = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(20))
        contract.evaluate()

        direct_vm.sender = _addr("stranger")
        with pytest.raises(Exception):
            contract.appeal()
        direct_vm.sender = client

    def test_appeal_then_finalize_accepted(self, direct_deploy, direct_vm):
        """Appeal overturns verdict: appeal score >= min_score → ACCEPTED after finalize."""
        contract, _, client = _setup(direct_deploy, direct_vm)
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(20))
        contract.evaluate()

        direct_vm.clear_mocks()
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
        direct_vm.mock_llm(".*", _llm(80))
        direct_vm.sender = client
        contract.appeal()
        direct_vm.sender = client

        contract.finalize()
        result = json.loads(contract.get_result())
        assert result["status"] == "SETTLEMENT_PENDING"
        assert result["settlement_outcome"] == "ACCEPTED"

    def test_cannot_appeal_before_evaluation(self, direct_deploy, direct_vm):
        """appeal() before evaluate() should raise."""
        contract, _, client = _setup(direct_deploy, direct_vm)
        direct_vm.sender = client
        with pytest.raises(Exception):
            contract.appeal()
        direct_vm.sender = client

    def test_cannot_finalize_before_evaluation(self, direct_deploy, direct_vm):
        """finalize() before evaluate() should raise."""
        contract, _, _ = _setup(direct_deploy, direct_vm)
        with pytest.raises(Exception):
            contract.finalize()
