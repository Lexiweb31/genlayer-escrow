"""
Integration tests for evaluate_submission.py.
These run against a real GenLayer environment (GLSim or localnet) with live LLM calls.

Run against GLSim (fastest):
    glsim --port 4000 --validators 5   # in a separate terminal
    gltest tests/integration/ -v -s

Run against localnet (full GenVM):
    genlayer up
    gltest tests/integration/ -v -s --network localnet
"""
import json
import pytest


SPEC_LANDING_PAGE = (
    "Build a landing page for a fintech startup. Must include: "
    "a hero section with headline and CTA button, a features section "
    "with at least 3 items, a footer with contact email. "
    "Must be mobile-responsive."
)

# A real, publicly accessible page that clearly meets a spec
# Using example.com as a stand-in — replace with a real test URL
URL_CLEARLY_DONE = "https://example.com"
URL_CLEARLY_NOT_DONE = "https://example.com/404-this-does-not-exist"


class TestEvaluateSubmissionIntegration:

    @pytest.fixture
    def contract(self, gl_deploy):
        return gl_deploy("contracts/evaluate_submission.py", constructor_args=[])

    def test_initial_state_is_pending(self, contract, gl_call):
        result = json.loads(gl_call(contract, "get_result"))
        assert result["status"] == "pending"

    def test_evaluation_reaches_consensus(self, contract, gl_transaction):
        """
        Core Phase 0 gate: validators must reach consensus and finalise the transaction.
        If this test fails with UNDETERMINED, the validator agreement thresholds need tuning.
        """
        receipt = gl_transaction(
            contract,
            "evaluate_submission",
            args=[SPEC_LANDING_PAGE, URL_CLEARLY_DONE],
        )
        assert receipt["status"] == "FINALIZED", (
            f"Transaction did not finalise — validators could not agree. "
            f"Status: {receipt['status']}"
        )

    def test_result_stored_after_evaluation(self, contract, gl_transaction, gl_call):
        """After a finalised transaction, result must be readable."""
        gl_transaction(
            contract,
            "evaluate_submission",
            args=[SPEC_LANDING_PAGE, URL_CLEARLY_DONE],
        )

        result = json.loads(gl_call(contract, "get_result"))
        assert "verdict" in result
        assert result["verdict"] in ("ACCEPTED", "REJECTED")
        assert 0 <= result["score"] <= 100
        assert len(result["reasoning"]) > 10

    def test_verdict_is_boolean_not_numeric(self, contract, gl_transaction, gl_call):
        """Verdict must be a string ACCEPTED or REJECTED, never a number or boolean."""
        gl_transaction(
            contract,
            "evaluate_submission",
            args=[SPEC_LANDING_PAGE, URL_CLEARLY_DONE],
        )

        result = json.loads(gl_call(contract, "get_result"))
        assert isinstance(result["verdict"], str)
        assert result["verdict"] in ("ACCEPTED", "REJECTED")
