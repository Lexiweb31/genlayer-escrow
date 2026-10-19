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


# ── Tests: drift gate ─────────────────────────────────────────────────────────

HOLD = 3600  # 1h, the minimum, keeps warps small


class _StubDetector:
    """Answers cross-contract view calls the escrow makes to a ValueDriftDetector."""

    def __init__(self, agent, status="ALIGNED"):
        self.agent = str(agent)
        self.status = status
        self.broken = False

    def hook(self, vm, request):
        if "CallContract" not in request:
            return None
        from genlayer.py import calldata
        if self.broken:
            return bytes([2]) + b"detector unavailable"   # VM_ERROR
        method = request["CallContract"]["calldata"]["method"]
        if method == "get_mandate":
            value = json.dumps({"agent": self.agent})
        elif method == "get_status":
            value = json.dumps({"status": self.status})
        else:
            return None
        return bytes([0]) + calldata.encode(value)          # RETURN


def _setup_gated(direct_deploy, direct_vm, status="ALIGNED"):
    """Deploy, fund, link a stub detector for the worker, accept terms and submit."""
    contract, worker, client = _setup(direct_deploy, direct_vm, with_terms=False)
    detector = _StubDetector(worker, status)
    direct_vm._gl_call_hook = detector.hook
    contract.link_drift_detector(_addr("detector"), HOLD)
    direct_vm.sender = worker
    contract.accept_terms()
    contract.submit_work("http://example.com")
    direct_vm.sender = client
    return contract, detector


def _warp(direct_vm, timestamp: str) -> None:
    """direct_vm.warp() skips gl.message_raw["datetime"], which the contract reads."""
    import sys
    direct_vm.warp(timestamp)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = timestamp


def _evaluate(contract, direct_vm, score):
    direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_COMPLETE})
    direct_vm.mock_llm(".*", _llm(score))
    contract.evaluate()


class TestDriftGateLinking:

    def test_link_records_detector_and_hold(self, direct_deploy, direct_vm):
        contract, _ = _setup_gated(direct_deploy, direct_vm)
        gate = json.loads(contract.get_job())["drift_gate"]
        assert gate["linked"] is True
        assert gate["hold_seconds"] == HOLD
        assert gate["hold_since"] == ""

    def test_unlinked_job_reports_no_gate(self, direct_deploy, direct_vm):
        contract, _, _ = _setup(direct_deploy, direct_vm)
        assert json.loads(contract.get_job())["drift_gate"]["linked"] is False

    def test_zero_hold_uses_seven_day_default(self, direct_deploy, direct_vm):
        contract, worker, _ = _setup(direct_deploy, direct_vm, with_terms=False)
        direct_vm._gl_call_hook = _StubDetector(worker).hook
        contract.link_drift_detector(_addr("detector"), 0)
        assert json.loads(contract.get_job())["drift_gate"]["hold_seconds"] == 7 * 24 * 3600

    def test_only_client_can_link(self, direct_deploy, direct_vm):
        contract, worker, _ = _setup(direct_deploy, direct_vm, with_terms=False)
        direct_vm._gl_call_hook = _StubDetector(worker).hook
        direct_vm.sender = worker
        with pytest.raises(Exception):
            contract.link_drift_detector(_addr("detector"), HOLD)

    def test_cannot_link_after_terms_accepted(self, direct_deploy, direct_vm):
        contract, worker, _ = _setup(direct_deploy, direct_vm, with_submission=False)
        direct_vm._gl_call_hook = _StubDetector(worker).hook
        with pytest.raises(Exception):
            contract.link_drift_detector(_addr("detector"), HOLD)

    def test_detector_must_track_the_worker(self, direct_deploy, direct_vm):
        contract, _, _ = _setup(direct_deploy, direct_vm, with_terms=False)
        direct_vm._gl_call_hook = _StubDetector(_addr("someone_else")).hook
        with pytest.raises(Exception):
            contract.link_drift_detector(_addr("detector"), HOLD)

    def test_unreadable_detector_rejected(self, direct_deploy, direct_vm):
        contract, worker, _ = _setup(direct_deploy, direct_vm, with_terms=False)
        stub = _StubDetector(worker)
        stub.broken = True
        direct_vm._gl_call_hook = stub.hook
        with pytest.raises(Exception):
            contract.link_drift_detector(_addr("detector"), HOLD)

    @pytest.mark.parametrize("hold", [HOLD - 1, 30 * 24 * 3600 + 1])
    def test_hold_bounds_enforced(self, direct_deploy, direct_vm, hold):
        contract, worker, _ = _setup(direct_deploy, direct_vm, with_terms=False)
        direct_vm._gl_call_hook = _StubDetector(worker).hook
        with pytest.raises(Exception):
            contract.link_drift_detector(_addr("detector"), hold)


class TestDriftGateFinalize:

    def test_aligned_agent_pays_out(self, direct_deploy, direct_vm):
        contract, _ = _setup_gated(direct_deploy, direct_vm, "ALIGNED")
        _evaluate(contract, direct_vm, 90)
        contract.finalize()
        job = json.loads(contract.get_job())
        assert job["status"] == "SETTLEMENT_PENDING"
        assert job["drift_gate"]["release"] == "CLEAR"
        assert job["drift_gate"]["last_status"] == "ALIGNED"

    def test_unreviewed_agent_is_not_held(self, direct_deploy, direct_vm):
        contract, _ = _setup_gated(direct_deploy, direct_vm, "UNREVIEWED")
        _evaluate(contract, direct_vm, 90)
        contract.finalize()
        assert json.loads(contract.get_job())["status"] == "SETTLEMENT_PENDING"

    @pytest.mark.parametrize("status", ["DRIFTED", "REVOKED"])
    def test_drifted_agent_payout_is_held(self, direct_deploy, direct_vm, status):
        contract, _ = _setup_gated(direct_deploy, direct_vm, status)
        _evaluate(contract, direct_vm, 90)
        contract.finalize()
        job = json.loads(contract.get_job())
        assert job["status"] == "EVALUATED"
        assert job["amount"] == AMOUNT
        assert job["drift_gate"]["hold_since"] != ""
        assert job["drift_gate"]["last_status"] == status
        assert job["settlement"]["transfer_status"] == "NOT_STARTED"

    def test_hold_persists_until_period_ends(self, direct_deploy, direct_vm):
        contract, _ = _setup_gated(direct_deploy, direct_vm, "DRIFTED")
        _warp(direct_vm, "2026-01-01T00:00:00Z")
        _evaluate(contract, direct_vm, 90)
        contract.finalize()
        _warp(direct_vm, "2026-01-01T00:59:59Z")
        contract.finalize()
        assert json.loads(contract.get_job())["status"] == "EVALUATED"

    def test_expired_hold_pays_out_the_verdict(self, direct_deploy, direct_vm):
        contract, _ = _setup_gated(direct_deploy, direct_vm, "DRIFTED")
        _warp(direct_vm, "2026-01-01T00:00:00Z")
        _evaluate(contract, direct_vm, 90)
        contract.finalize()
        _warp(direct_vm, "2026-01-01T01:00:00Z")
        contract.finalize()
        job = json.loads(contract.get_job())
        assert job["status"] == "SETTLEMENT_PENDING"
        assert job["settlement"]["outcome"] == "ACCEPTED"
        assert job["drift_gate"]["release"] == "HOLD_EXPIRED"

    def test_re_review_to_aligned_releases_hold(self, direct_deploy, direct_vm):
        contract, detector = _setup_gated(direct_deploy, direct_vm, "DRIFTED")
        _evaluate(contract, direct_vm, 90)
        contract.finalize()
        detector.status = "ALIGNED"
        contract.finalize()
        job = json.loads(contract.get_job())
        assert job["status"] == "SETTLEMENT_PENDING"
        assert job["drift_gate"]["release"] == "CLEAR"

    def test_partial_payout_is_also_held(self, direct_deploy, direct_vm):
        contract, _ = _setup_gated(direct_deploy, direct_vm, "DRIFTED")
        _evaluate(contract, direct_vm, 55)
        contract.finalize()
        assert json.loads(contract.get_job())["status"] == "EVALUATED"

    def test_refund_is_never_held(self, direct_deploy, direct_vm):
        """A drifted agent with failing work: the client's refund goes straight out."""
        contract, _ = _setup_gated(direct_deploy, direct_vm, "DRIFTED")
        _evaluate(contract, direct_vm, 10)
        contract.finalize()
        job = json.loads(contract.get_job())
        assert job["status"] == "SETTLEMENT_PENDING"
        assert job["settlement"]["outcome"] == "REFUNDED"
        assert job["drift_gate"]["hold_since"] == ""

    def test_unavailable_detector_fails_open(self, direct_deploy, direct_vm):
        contract, detector = _setup_gated(direct_deploy, direct_vm, "DRIFTED")
        _evaluate(contract, direct_vm, 90)
        detector.broken = True
        contract.finalize()
        job = json.loads(contract.get_job())
        assert job["status"] == "SETTLEMENT_PENDING"
        assert job["drift_gate"]["last_status"] == "UNAVAILABLE"

    def test_appeal_still_allowed_during_hold(self, direct_deploy, direct_vm):
        contract, _ = _setup_gated(direct_deploy, direct_vm, "DRIFTED")
        _evaluate(contract, direct_vm, 90)
        contract.finalize()
        direct_vm.clear_mocks()
        direct_vm.mock_web(".*", {**_WEB_OK, "body": MOCK_PAGE_EMPTY})
        direct_vm.mock_llm(".*", _llm(20))
        contract.appeal()
        contract.finalize()
        assert json.loads(contract.get_job())["settlement"]["outcome"] == "REFUNDED"
