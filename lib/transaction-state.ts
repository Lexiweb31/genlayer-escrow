export interface TransactionEvidence {
  status?: unknown;
  executionResult?: unknown;
  result?: unknown;
}

export interface ClassifiedTransactionState {
  status: string;
  executionResult: string;
  result: string;
  failed: boolean;
  confirmed: boolean;
}

export function classifyTransactionState(evidence: TransactionEvidence): ClassifiedTransactionState {
  const status = String(evidence.status || "UNKNOWN").toUpperCase();
  const executionResult = String(evidence.executionResult || "UNKNOWN").toUpperCase();
  const result = String(evidence.result || "UNKNOWN").toUpperCase();
  const failedStatuses = new Set(["CANCELED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"]);
  return {
    status,
    executionResult,
    result,
    failed: failedStatuses.has(status) || executionResult === "FINISHED_WITH_ERROR" || result === "FAILURE",
    confirmed: ["ACCEPTED", "FINALIZED"].includes(status) && executionResult === "FINISHED_WITH_RETURN" && result !== "FAILURE",
  };
}
