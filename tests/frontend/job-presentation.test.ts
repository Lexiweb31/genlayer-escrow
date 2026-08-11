import { describe, expect, it } from "vitest";
import { hasSubmittedWork, reconciliationPresentation } from "@/lib/job-presentation";
import type { JobRecord } from "@/lib/types";

const job = (overrides: Partial<JobRecord>): JobRecord => ({
  address: "0x0000000000000000000000000000000000000001",
  status: "OPEN",
  ...overrides,
});

describe("job lifecycle presentation", () => {
  it("does not describe a newly funded or accepted job as submitted", () => {
    expect(hasSubmittedWork(job({ status: "OPEN" }))).toBe(false);
    expect(hasSubmittedWork(job({ status: "AGREED" }))).toBe(false);
  });

  it("recognizes submitted work from the lifecycle when an older registry row omits its URL", () => {
    expect(hasSubmittedWork(job({ status: "SUBMITTED" }))).toBe(true);
    expect(hasSubmittedWork(job({ status: "EVALUATED", score: 58, evaluation_complete: true }))).toBe(true);
    expect(hasSubmittedWork(job({ status: "REFUNDED", score: 5 }))).toBe(true);
  });

  it("recognizes direct and Bounty submission evidence", () => {
    expect(hasSubmittedWork(job({ submission_url: "https://example.com/work" }))).toBe(true);
    expect(hasSubmittedWork(job({
      job_type: "BOUNTY",
      submissions: [{ position: 1, submitter: "0xworker", url: "https://example.com/entry" }],
    }))).toBe(true);
  });

  it("requires recovery when settlement is pending without a verified transaction hash", () => {
    const view = reconciliationPresentation(job({
      status: "SETTLEMENT_PENDING",
      settlement: { transfer_status: "PENDING_FINALIZATION" },
      reconcile_age_seconds: 45,
    }));
    expect(view.state).toBe("RECOVERY_REQUIRED");
    expect(view.action).toBe("recover_by_hash");
    expect(view.elapsed).toBe("45s ago");
  });

  it("does not present a cancelled settlement as indefinitely pending", () => {
    const view = reconciliationPresentation(job({
      status: "SETTLEMENT_PENDING",
      settlement: { parent_transaction: "0xcancelled", parent_status: "CANCELED", transfer_status: "FAILED_FINALIZATION" },
      reconcile_age_seconds: 90,
    }));
    expect(view.state).toBe("CANCELLED");
    expect(view.transaction).toBe("0xcancelled");
    expect(view.action).toBe("reconnect_correct_wallet");
  });

  it("keeps Bradbury acceptance distinct from transfer finality", () => {
    const view = reconciliationPresentation(job({
      status: "SETTLEMENT_PENDING",
      settlement: { parent_transaction: "0xaccepted", parent_status: "ACCEPTED", transfer_status: "PENDING_FINALIZATION" },
      reconcile_age_seconds: 12,
    }));
    expect(view.state).toBe("ACCEPTED_NOT_FINALIZED");
    expect(view.transaction).toBe("0xaccepted");
    expect(view.action).toBe("wait_for_finality");
  });
});
