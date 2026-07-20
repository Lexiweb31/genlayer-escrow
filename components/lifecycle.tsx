import { CheckIcon, ClockIcon } from "@/components/icons";
import { settlementPresentation } from "@/lib/settlement";
import type { EvaluationResult, JobRecord, JobStatus } from "@/lib/types";

const stageIndex: Partial<Record<JobStatus, number>> = {
  UNFUNDED: 1,
  OPEN: 2,
  AGREED: 3,
  SUBMITTED: 4,
  EVALUATED: 5,
  SETTLEMENT_PENDING: 5,
  ACCEPTED: 7,
  PARTIAL: 7,
  REFUNDED: 7,
};

export function Lifecycle({ job, result, transactionPending = false }: { job: JobRecord; result?: EvaluationResult; transactionPending?: boolean }) {
  const presentation = settlementPresentation(job, result);
  const current = presentation.isFinalized ? 7 : stageIndex[job.status] ?? 1;
  const settlementStage = presentation.isPending && !presentation.hasTransactionReference
    ? presentation.decision === "REFUNDED" ? "Refund transaction not verified" : "Payment transaction not verified"
    : presentation.hasTransactionReference
    ? "Payment transaction submitted"
    : "Settlement submitted";
  const confirmedLabel = presentation.decision === "REFUNDED" ? "Refund confirmed" : presentation.decision === "PARTIAL" ? "Split payment confirmed" : "Payment confirmed";
  const stages = ["Job created", "Payment locked", "Requirements accepted", "Work submitted", "Evaluation completed", settlementStage, confirmedLabel];
  return <ol className="lifecycle">{stages.map((label, index) => <li key={`${index}:${label}`} className={index < current ? "done" : index === current ? "current" : ""}><span>{index < current ? <CheckIcon size={14}/> : index === current ? <ClockIcon size={14}/> : index + 1}</span><div><b>{label}</b><small>{index < current ? "Confirmed" : index === current ? transactionPending ? "Transaction processing" : "Current step" : "Pending"}</small></div></li>)}</ol>;
}
