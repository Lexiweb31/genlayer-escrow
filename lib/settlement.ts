import type { EvaluationResult, JobRecord, JobStatus, SettlementTransfer } from "@/lib/types";

const FINAL_DECISIONS = new Set(["ACCEPTED", "PARTIAL", "REFUNDED"]);

export interface SettlementPresentation {
  status: JobStatus;
  label: string;
  decision?: string;
  isPending: boolean;
  isFinalized: boolean;
  canClaimCompletion: boolean;
}

export function settlementPresentation(
  job: JobRecord,
  result?: EvaluationResult,
): SettlementPresentation {
  if (job.legacy_contract || job.status === "LEGACY_UNSAFE") {
    return {
      status: "LEGACY_UNSAFE",
      label: "Legacy · do not fund",
      isPending: false,
      isFinalized: false,
      canClaimCompletion: false,
    };
  }
  const settlement = job.settlement || {};
  const decision = settlement.outcome || result?.settlement_outcome;
  const hasQueuedTransfer = Boolean(settlement.parent_transaction);
  const isFinalized = settlement.transfer_status === "FINALIZED" && Boolean(decision);
  if (hasQueuedTransfer && !isFinalized) {
    return {
      status: "SETTLEMENT_PENDING",
      label: "Settlement pending",
      decision,
      isPending: true,
      isFinalized: false,
      canClaimCompletion: false,
    };
  }
  if (isFinalized && decision && FINAL_DECISIONS.has(decision)) {
    return {
      status: decision as JobStatus,
      label: decision === "ACCEPTED" ? "Payment released" : decision === "REFUNDED" ? "Funds refunded" : "Split finalized",
      decision,
      isPending: false,
      isFinalized: true,
      canClaimCompletion: true,
    };
  }
  return {
    status: job.status,
    label: statusLabel(job.status),
    decision,
    isPending: false,
    isFinalized: false,
    canClaimCompletion: false,
  };
}

export function statusLabel(status: JobStatus): string {
  const labels: Partial<Record<JobStatus, string>> = {
    UNFUNDED: "Awaiting funding",
    OPEN: "Open escrow",
    AGREED: "Terms accepted",
    SUBMITTED: "Submitted",
    EVALUATED: "Evaluated",
    SETTLEMENT_PENDING: "Settlement pending",
    ACCEPTED: "Payment released",
    PARTIAL: "Split finalized",
    REFUNDED: "Funds refunded",
    LEGACY_UNSAFE: "Legacy · do not fund",
    UNKNOWN: "Testnet unavailable",
  };
  return labels[status] || status;
}

export function recipientRole(transfer: SettlementTransfer): string {
  return {
    WORKER_PAYOUT: "Worker recipient",
    CLIENT_REFUND: "Client recipient",
    PLATFORM_FEE: "Platform recipient",
  }[transfer.settlement_type] || "Settlement recipient";
}

export function hasConfirmedEvaluation(job: JobRecord, result?: EvaluationResult): boolean {
  return typeof (result?.score ?? job.score) === "number";
}
