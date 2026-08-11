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

  it("keeps an unknown refreshed state confirming when funding evidence exists", () => {
    expect(fundingActivationState({
      job: { ...job, status: "UNKNOWN" },
      fundingTransaction: { tx_hash: "0xabc", status: "FINALIZED" },
    })).toMatchObject({ kind: "CONFIRMING", canFund: false, transactionHash: "0xabc" });
  });

  it("makes a cancelled transaction safely retryable", () => {
    expect(fundingActivationState({ job, fundingTransaction: { tx_hash: "0xabc", status: "CANCELED" } })).toMatchObject({ kind: "FAILED", canFund: true });
  });

  it.each(["UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT", "FAILED"])(
    "makes %s funding evidence safely retryable",
    (status) => {
      expect(fundingActivationState({ job, fundingTransaction: { tx_hash: "0xabc", status } })).toMatchObject({
        kind: "FAILED",
        canFund: true,
        transactionHash: "0xabc",
      });
    },
  );
});
