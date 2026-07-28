import { describe, expect, it } from "vitest";
import { hasSubmittedWork } from "@/lib/job-presentation";
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
});
