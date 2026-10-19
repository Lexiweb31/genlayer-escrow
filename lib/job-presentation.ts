import type { JobRecord } from "@/lib/types";

export type ReconciliationUiState =
  | "SUBMITTED"
  | "ACCEPTED_NOT_FINALIZED"
  | "FINALIZED"
  | "FAILED"
  | "CANCELLED"
  | "RECOVERY_REQUIRED";

export interface ReconciliationPresentation {
  state: ReconciliationUiState;
  transaction?: string;
  transactionLink?: string;
  elapsed: string;
  action: "refresh" | "reconnect_correct_wallet" | "recover_by_hash" | "wait_for_finality";
  message: string;
}

const submittedOrLater = new Set<JobRecord["status"]>([
  "SUBMITTED",
  "EVALUATED",
  "SETTLEMENT_PENDING",
  "ACCEPTED",
  "PARTIAL",
  "REFUNDED",
]);

export function hasSubmittedWork(job: JobRecord | null | undefined): boolean {
  if (!job) return false;
  return Boolean(
    job.submission_url
    || job.winning_url
    || job.submissions?.length
    || job.evaluation_complete
    || job.score !== null && job.score !== undefined
    || submittedOrLater.has(job.status),
  );
}

function elapsedContext(seconds: number | null | undefined): string {
  const age = Math.max(0, Math.floor(Number(seconds) || 0));
  if (age < 60) return `${age}s ago`;
  if (age < 3600) return `${Math.floor(age / 60)}m ago`;
  return `${Math.floor(age / 3600)}h ago`;
}

export function reconciliationPresentation(job: JobRecord): ReconciliationPresentation {
  const settlement = job.settlement || {};
  const transaction = settlement.parent_transaction;
  const parentStatus = String(settlement.parent_status || "").toUpperCase();
  const transferStatus = String(settlement.transfer_status || "").toUpperCase();
  const base = {
    transaction,
    transactionLink: settlement.parent_explorer || settlement.explorer,
    elapsed: elapsedContext(job.reconcile_age_seconds),
  };
  if (transferStatus === "FINALIZED") {
    return { ...base, state: "FINALIZED", action: "refresh", message: "Transfer finality is verified." };
  }
  if (!transaction && (job.status === "SETTLEMENT_PENDING" || transferStatus.startsWith("PENDING"))) {
    return { ...base, state: "RECOVERY_REQUIRED", action: "recover_by_hash", message: "Recover the settlement by its transaction hash." };
  }
  if (["CANCELED", "CANCELLED"].includes(parentStatus)) {
    return { ...base, state: "CANCELLED", action: "reconnect_correct_wallet", message: "The settlement transaction was cancelled; reconnect the assigned client wallet." };
  }
  if (["FAILED", "REJECTED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"].includes(parentStatus) || transferStatus === "FAILED_FINALIZATION") {
    return { ...base, state: "FAILED", action: "reconnect_correct_wallet", message: "The settlement transaction failed; reconnect the assigned client wallet." };
  }
  if (parentStatus === "ACCEPTED") {
    return { ...base, state: "ACCEPTED_NOT_FINALIZED", action: "wait_for_finality", message: "Bradbury accepted the transaction; wait for transfer finality." };
  }
  return { ...base, state: "SUBMITTED", action: "refresh", message: "The transaction was submitted; refresh its Bradbury status." };
}
