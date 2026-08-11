import { describe, expect, it } from "vitest";
import { fundingActivationState } from "@/lib/funding-activation";

const job = { address: "0x1111111111111111111111111111111111111111", status: "UNFUNDED" as const };

describe("funding activation state", () => {
  it("requires funding when no transaction exists", () => {
    expect(fundingActivationState({ job }).kind).toBe("REQUIRED");
  });

  it("shows wallet approval before a hash exists", () => {
    expect(fundingActivationState({ job, pendingAction: { stage: "awaiting_wallet" } }).kind).toBe("AWAITING_WALLET");
  });

  it("treats a non-terminal hash as confirming", () => {
    expect(fundingActivationState({ job, fundingTransaction: { tx_hash: "0xabc", status: "ACCEPTED" } }).kind).toBe("CONFIRMING");
  });

  it("uses verified OPEN state as activation", () => {
    expect(fundingActivationState({ job: { ...job, status: "OPEN" } }).kind).toBe("ACTIVE");
  });

  it("makes a cancelled transaction safely retryable", () => {
    expect(fundingActivationState({ job, fundingTransaction: { tx_hash: "0xabc", status: "CANCELED" } })).toMatchObject({ kind: "FAILED", canFund: true });
  });
});
