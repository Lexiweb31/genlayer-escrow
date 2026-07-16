import { CheckIcon, ClockIcon } from "@/components/icons";
import { settlementPresentation } from "@/lib/settlement";
import type { EvaluationResult, JobRecord, JobStatus } from "@/lib/types";

const stageIndex: Partial<Record<JobStatus, number>> = {
  UNFUNDED: 0,
  OPEN: 1,
  AGREED: 2,
  SUBMITTED: 3,
  EVALUATED: 4,
  SETTLEMENT_PENDING: 5,
  ACCEPTED: 6,
  PARTIAL: 6,
  REFUNDED: 6,
};

export function Lifecycle({ job, result }: { job: JobRecord; result?: EvaluationResult }) {
  const presentation = settlementPresentation(job, result);
  const current = presentation.isPending ? 5 : presentation.isFinalized ? 6 : stageIndex[job.status] ?? 0;
  const settlementStage = presentation.hasTransactionReference
    ? "Payment transaction submitted"
    : presentation.decision === "REFUNDED"
      ? "Refund transaction not verified"
      : "Payment transaction not verified";
  const stages = ["Job created", "Payment locked", "Requirements accepted", "Work submitted", "Evaluation completed", settlementStage, "Payment confirmed"];
  return <ol className="lifecycle">{stages.map((label, index) => <li key={label} className={index < current ? "done" : index === current ? "current" : ""}><span>{index < current ? <CheckIcon size={14}/> : index === current ? <ClockIcon size={14}/> : index + 1}</span><div><b>{label}</b><small>{index < current ? "Confirmed" : index === current ? "Current state" : "Pending"}</small></div></li>)}</ol>;
}
