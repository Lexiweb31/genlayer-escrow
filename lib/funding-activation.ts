import type { FundingActivationInput } from "@/lib/types";

export type FundingActivationKind = "REQUIRED" | "AWAITING_WALLET" | "CONFIRMING" | "ACTIVE" | "FAILED";

export interface FundingActivationView {
  kind: FundingActivationKind;
  label: string;
  detail: string;
  canFund: boolean;
  transactionHash?: string;
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
