import type { EvaluationResult, JobRecord, JobStatus, SettlementTransfer } from "@/lib/types";

const FINAL_DECISIONS = new Set(["ACCEPTED", "PARTIAL", "REFUNDED"]);

export interface SettlementPresentation {
  status: JobStatus;
  label: string;
  decision?: string;
  hasTransactionReference: boolean;
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
      hasTransactionReference: false,
      isPending: false,
      isFinalized: false,
      canClaimCompletion: false,
    };
  }
  const settlement = job.settlement || {};
  const decision = settlement.outcome || result?.settlement_outcome;
  const hasQueuedTransfer = Boolean(settlement.parent_transaction);
  const parentStatus = String(settlement.parent_status || "").toUpperCase();
  const isFinalized = settlement.transfer_status === "FINALIZED" && Boolean(decision);
  const isSettlementPending = !isFinalized && (
    hasQueuedTransfer
    || job.status === "SETTLEMENT_PENDING"
    || settlement.transfer_status === "PENDING_FINALIZATION"
    || settlement.transfer_status === "PENDING_TRANSFER_RECORD"
  );
  if (isSettlementPending) {
    return {
      status: "SETTLEMENT_PENDING",
      label: hasQueuedTransfer
        ? parentStatus === "ACCEPTED"
          ? "Waiting for Bradbury finality"
          : ["CANCELED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"].includes(parentStatus)
            ? "Settlement transaction failed"
            : "Payment processing"
        : decision === "REFUNDED"
          ? "Refund transaction not verified"
          : "Payment transaction not verified",
      decision,
      hasTransactionReference: hasQueuedTransfer,
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
      hasTransactionReference: hasQueuedTransfer,
      isPending: false,
      isFinalized: true,
      canClaimCompletion: true,
    };
  }
  return {
    status: job.status,
    label: statusLabel(job.status),
    decision,
    hasTransactionReference: hasQueuedTransfer,
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

export function displayEscrowAmountWei(job: JobRecord): string {
  const transfers = job.settlement?.transfers || [];
  const settledTotal = transfers.reduce((total, transfer) => {
    try {
      const amount = BigInt(transfer.amount || "0");
      return amount > 0n ? total + amount : total;
    } catch {
      return total;
    }
  }, 0n);
  return settledTotal > 0n ? settledTotal.toString() : String(job.amount || "0");
}
