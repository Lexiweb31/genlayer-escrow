import { describe, expect, it } from "vitest";
import { hasConfirmedEvaluation, settlementPresentation } from "@/lib/settlement";
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
});
