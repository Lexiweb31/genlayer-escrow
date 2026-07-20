import { describe, expect, it } from "vitest";
import { displayEscrowAmountWei, hasConfirmedEvaluation, settlementPresentation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";

const baseJob: JobRecord = {
  address: "0x1234567890123456789012345678901234567890",
  status: "EVALUATED",
};

describe("settlement lifecycle mapping", () => {
  it("keeps a recorded decision pending until transfer finality", () => {
    const view = settlementPresentation({
      ...baseJob,
      status: "ACCEPTED",
      settlement: {
        outcome: "ACCEPTED",
        transfer_status: "PENDING_FINALIZATION",
        parent_transaction: "0xparent",
      },
    });
    expect(view.status).toBe("SETTLEMENT_PENDING");
    expect(view.label).toBe("Payment processing");
    expect(view.decision).toBe("ACCEPTED");
    expect(view.canClaimCompletion).toBe(false);
    expect(view.hasTransactionReference).toBe(true);
  });

  it("shows the exact Bradbury acceptance state before finality", () => {
    const view = settlementPresentation({
      ...baseJob,
      status: "SETTLEMENT_PENDING",
      settlement: {
        outcome: "PARTIAL",
        transfer_status: "PENDING_FINALIZATION",
        parent_transaction: "0xparent",
        parent_status: "ACCEPTED",
      },
    });
    expect(view.label).toBe("Waiting for Bradbury finality");
    expect(view.isFinalized).toBe(false);
  });

  it("does not disguise a canceled settlement as processing", () => {
    const view = settlementPresentation({
      ...baseJob,
      status: "SETTLEMENT_PENDING",
      settlement: {
        outcome: "PARTIAL",
        transfer_status: "FAILED_FINALIZATION",
        parent_transaction: "0xparent",
        parent_status: "CANCELED",
      },
    });
    expect(view.label).toBe("Settlement transaction failed");
    expect(view.isFinalized).toBe(false);
  });

  it("never claims confirmation for a pending settlement without a transaction reference", () => {
    const view = settlementPresentation({
      ...baseJob,
      status: "SETTLEMENT_PENDING",
      settlement: {
        outcome: "REFUNDED",
        transfer_status: "PENDING_FINALIZATION",
      },
    });
    expect(view.isPending).toBe(true);
    expect(view.isFinalized).toBe(false);
    expect(view.hasTransactionReference).toBe(false);
    expect(view.label).toBe("Refund transaction not verified");
    expect(view.canClaimCompletion).toBe(false);
  });

  it("uses completion language only after the outbound transfer finalizes", () => {
    const accepted = settlementPresentation({
      ...baseJob,
      status: "ACCEPTED",
      settlement: {
        outcome: "ACCEPTED",
        transfer_status: "FINALIZED",
        parent_transaction: "0xparent",
      },
    });
    const refunded = settlementPresentation({
      ...baseJob,
      status: "REFUNDED",
      settlement: {
        outcome: "REFUNDED",
        transfer_status: "FINALIZED",
        parent_transaction: "0xparent",
      },
    });
    expect(accepted.label).toBe("Payment sent to worker");
    expect(refunded.label).toBe("Refund sent to client");
    expect(accepted.canClaimCompletion).toBe(true);
  });

  it("keeps legacy contracts read-only", () => {
    const view = settlementPresentation({ ...baseJob, status: "LEGACY_UNSAFE", legacy_contract: true });
    expect(view.status).toBe("LEGACY_UNSAFE");
    expect(view.canClaimCompletion).toBe(false);
  });

  it("does not infer evaluation from an absent score", () => {
    expect(hasConfirmedEvaluation({ ...baseJob, status: "SUBMITTED" }, { score: null })).toBe(false);
    expect(hasConfirmedEvaluation({ ...baseJob, score: 0 }, {})).toBe(true);
  });

  it("shows the original settled value after the contract balance reaches zero", () => {
    expect(displayEscrowAmountWei({
      ...baseJob,
      status: "PARTIAL",
      amount: "0",
      settlement: {
        outcome: "PARTIAL",
        transfer_status: "FINALIZED",
        transfers: [
          { recipient: "0xworker", amount: "2227500000000000000", settlement_type: "WORKER_PAYOUT" },
          { recipient: "0xclient", amount: "750000000000000000", settlement_type: "CLIENT_REFUND" },
          { recipient: "0xfee", amount: "22500000000000000", settlement_type: "PLATFORM_FEE" },
        ],
      },
    })).toBe("3000000000000000000");
  });
});
