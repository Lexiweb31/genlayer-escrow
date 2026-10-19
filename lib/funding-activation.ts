import type { FundingActivationInput } from "@/lib/types";

export type FundingActivationKind = "REQUIRED" | "AWAITING_WALLET" | "CONFIRMING" | "ACTIVE" | "FAILED";

export interface FundingActivationView {
  kind: FundingActivationKind;
  label: string;
  detail: string;
  canFund: boolean;
  transactionHash?: string;
}

export type FundingFailureCase = "wallet rejection" | "malformed hash" | "network timeout" | "stale snapshot" | "contract rejection" | "API unavailable";

export function fundingFailurePresentation(failure: FundingFailureCase): Pick<FundingActivationView, "kind"> & { copy: string } {
  const presentations: Record<FundingFailureCase, Pick<FundingActivationView, "kind"> & { copy: string }> = {
    "wallet rejection": { kind: "REQUIRED", copy: "The wallet request was canceled. No GEN moved." },
    "malformed hash": { kind: "FAILED", copy: "The saved funding transaction hash is malformed. Clear it and retry funding safely." },
    "network timeout": { kind: "CONFIRMING", copy: "Confirmation timed out. Check funding status before taking another action." },
    "stale snapshot": { kind: "CONFIRMING", copy: "Transaction submitted — confirming on Bradbury. The shared job snapshot is still refreshing." },
    "contract rejection": { kind: "FAILED", copy: "Funding failed. Bradbury confirmed that the contract rejected the deposit." },
    "API unavailable": { kind: "CONFIRMING", copy: "Live updates unavailable. Check funding status before submitting another deposit." },
  };
  return presentations[failure];
}

const FUNDING_ACTIVE_JOB_STATUSES = new Set([
  "OPEN", "CLOSED", "AGREED", "SUBMITTED", "EVALUATED", "SETTLEMENT_PENDING", "ACCEPTED", "PARTIAL", "REFUNDED",
]);

export function isFundingActivatedStatus(status?: string): boolean {
  return Boolean(status && FUNDING_ACTIVE_JOB_STATUSES.has(status));
}

export function fundingActivationState({ job, fundingTransaction, pendingAction }: FundingActivationInput): FundingActivationView {
  if (isFundingActivatedStatus(job.status)) return { kind: "ACTIVE", label: "Job funded and publicly visible", detail: "Protected payment is verified by the shared contract snapshot.", canFund: false };
  if (fundingTransaction && ["CANCELED", "CANCELLED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT", "FAILED", "REJECTED"].includes(fundingTransaction.status.toUpperCase())) {
    return { kind: "FAILED", label: "Funding failed", detail: "No protected payment was activated. Review the transaction and retry safely.", canFund: true, transactionHash: fundingTransaction.tx_hash };
  }
  if (fundingTransaction?.tx_hash || pendingAction?.hash) return { kind: "CONFIRMING", label: "Transaction submitted — confirming on Bradbury", detail: "Do not submit another funding transaction.", canFund: false, transactionHash: fundingTransaction?.tx_hash || pendingAction?.hash };
  if (pendingAction?.stage === "awaiting_wallet") return { kind: "AWAITING_WALLET", label: "Awaiting wallet approval", detail: "Confirm or reject the funding request in your wallet.", canFund: false };
  if (job.status !== "UNFUNDED") return { kind: "CONFIRMING", label: "Funding state awaiting verification", detail: "Refresh Bradbury before submitting another funding transaction.", canFund: false };
  return { kind: "REQUIRED", label: "Funding required", detail: "Your job is created but not active yet.", canFund: true };
}
