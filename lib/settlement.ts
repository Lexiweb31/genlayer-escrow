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
      label: "Payment processing",
      decision,
      isPending: true,
      isFinalized: false,
      canClaimCompletion: false,
    };
  }
  if (isFinalized && decision && FINAL_DECISIONS.has(decision)) {
    return {
      status: decision as JobStatus,
      label: decision === "ACCEPTED" ? "Payment sent to worker" : decision === "REFUNDED" ? "Refund sent to client" : "Payment split confirmed",
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
    UNFUNDED: "Waiting for payment",
    OPEN: "Ready for a worker",
    AGREED: "Requirements accepted",
    SUBMITTED: "Work submitted",
    EVALUATED: "Evaluation completed",
    SETTLEMENT_PENDING: "Payment processing",
    ACCEPTED: "Payment sent to worker",
    PARTIAL: "Payment split confirmed",
    REFUNDED: "Refund sent to client",
    LEGACY_UNSAFE: "Legacy · do not fund",
    UNKNOWN: "Testnet unavailable",
  };
  return labels[status] || status;
}

export function recipientRole(transfer: SettlementTransfer): string {
  return {
    WORKER_PAYOUT: "Worker",
    CLIENT_REFUND: "Client",
    PLATFORM_FEE: "Merit fee",
  }[transfer.settlement_type] || "Settlement recipient";
}

export function hasConfirmedEvaluation(job: JobRecord, result?: EvaluationResult): boolean {
  return typeof (result?.score ?? job.score) === "number";
}
