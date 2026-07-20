import type { JobRecord, JobStatus } from "@/lib/types";

export type NotificationTone = "info" | "success" | "warning" | "danger";
export interface MeritNotification { id: string; jobAddress?: string; title: string; message: string; tone: NotificationTone; createdAt: string; read: boolean; }

const COPY: Partial<Record<JobStatus, Omit<MeritNotification, "id" | "jobAddress" | "createdAt" | "read">>> = {
  OPEN: { title: "Job funded", message: "Payment is protected and the assigned worker can now accept the job.", tone: "info" },
  AGREED: { title: "Worker accepted the job", message: "The requirements are accepted and work can begin.", tone: "success" },
  SUBMITTED: { title: "Work submitted", message: "The worker added a public deliverable that is ready for evaluation.", tone: "info" },
  EVALUATED: { title: "Evaluation completed", message: "Validator consensus is ready. Review the score and payment result.", tone: "success" },
  SETTLEMENT_PENDING: { title: "Payment is processing", message: "The settlement transaction was submitted and is awaiting confirmation.", tone: "warning" },
  ACCEPTED: { title: "Worker payment confirmed", message: "The worker payout has been confirmed on-chain.", tone: "success" },
  PARTIAL: { title: "Split payment confirmed", message: "The proportional worker payment and client return are confirmed.", tone: "success" },
  REFUNDED: { title: "Client refund confirmed", message: "The escrow refund has been confirmed on-chain.", tone: "danger" },
  LEGACY_UNSAFE: { title: "Unsafe legacy contract", message: "This contract is read-only and must not be funded.", tone: "danger" },
};

const CLIENT_COPY: Partial<Record<JobStatus, Omit<MeritNotification, "id" | "jobAddress" | "createdAt" | "read">>> = {
  OPEN: { title: "Payment locked", message: "The assigned worker can now review and accept the job requirements.", tone: "info" },
  AGREED: { title: "Worker accepted the job", message: "Work has started under the agreed requirements.", tone: "success" },
  SUBMITTED: { title: "Work ready for evaluation", message: "The worker submitted a public deliverable. Review it and request GenLayer evaluation.", tone: "info" },
  EVALUATED: { title: "Evaluation ready", message: "Validator consensus is confirmed. Review the reasoning and submit the payment transaction.", tone: "success" },
};

const WORKER_COPY: Partial<Record<JobStatus, Omit<MeritNotification, "id" | "jobAddress" | "createdAt" | "read">>> = {
  OPEN: { title: "Assigned job funded", message: "Payment is protected. Review and accept the job requirements to begin work.", tone: "info" },
  AGREED: { title: "Requirements accepted", message: "The agreement is active. Submit the public deliverable when the work is complete.", tone: "success" },
  SUBMITTED: { title: "Submission recorded", message: "Your public deliverable is waiting for the client to request evaluation.", tone: "info" },
  EVALUATED: { title: "Evaluation completed", message: "Validator consensus is ready. Review the score and expected payment result.", tone: "success" },
};

export function addressMatches(left?: string | null, right?: string | null): boolean { return Boolean(left && right && left.toLowerCase() === right.toLowerCase()); }
export function jobRelevantToWallet(job: JobRecord, address?: string | null): boolean { return Boolean(address && (addressMatches(address, job.client || job.client_address) || addressMatches(address, job.worker || job.worker_address))); }
export function notificationForStatus(job: JobRecord, status: JobStatus, createdAt = new Date().toISOString(), viewerAddress?: string | null): MeritNotification | null {
  const isClient = addressMatches(viewerAddress, job.client || job.client_address);
  const isWorker = addressMatches(viewerAddress, job.worker || job.worker_address);
  const copy = (isClient ? CLIENT_COPY[status] : isWorker ? WORKER_COPY[status] : undefined) || COPY[status];
  return copy ? { id: `${job.address}:${status}`, jobAddress: job.address, ...copy, createdAt, read: false } : null;
}
