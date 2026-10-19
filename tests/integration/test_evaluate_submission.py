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

from gltest.contracts import get_contract_factory
from gltest.types import TransactionStatus


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
    def contract(self, default_account):
        factory = get_contract_factory(
            contract_file_path="contracts/evaluate_submission.py"
        )
        return factory.deploy(
            account=default_account,
            wait_transaction_status=TransactionStatus.FINALIZED,
        )

    def test_initial_state_is_pending(self, contract):
        result = json.loads(contract.get_result().call())
        assert result["status"] == "pending"

    def test_evaluation_reaches_consensus(self, contract):
        """
        Core Phase 0 gate: validators must reach consensus and finalise the transaction.
        If this test fails with UNDETERMINED, the validator agreement thresholds need tuning.
        """
        receipt = contract.evaluate_submission(
            args=[SPEC_LANDING_PAGE, URL_CLEARLY_DONE]
        ).transact(
            wait_transaction_status=TransactionStatus.FINALIZED,
        )
        assert receipt["status"].upper() == "FINALIZED", (
            f"Transaction did not finalise — validators could not agree. "
            f"Status: {receipt['status']}"
        )

    def test_result_stored_after_evaluation(self, contract):
        """After a finalised transaction, result must be readable."""
        contract.evaluate_submission(
            args=[SPEC_LANDING_PAGE, URL_CLEARLY_DONE]
        ).transact(wait_transaction_status=TransactionStatus.FINALIZED)

        result = json.loads(contract.get_result().call())
        assert "verdict" in result
        assert result["verdict"] in ("ACCEPTED", "REJECTED")
        assert 0 <= result["score"] <= 100
        assert len(result["reasoning"]) > 10

    def test_verdict_is_boolean_not_numeric(self, contract):
        """Verdict must be a string ACCEPTED or REJECTED, never a number or boolean."""
        contract.evaluate_submission(
            args=[SPEC_LANDING_PAGE, URL_CLEARLY_DONE]
        ).transact(wait_transaction_status=TransactionStatus.FINALIZED)

        result = json.loads(contract.get_result().call())
        assert isinstance(result["verdict"], str)
        assert result["verdict"] in ("ACCEPTED", "REJECTED")
