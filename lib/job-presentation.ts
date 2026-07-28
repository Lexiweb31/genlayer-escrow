import type { JobRecord } from "@/lib/types";

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
