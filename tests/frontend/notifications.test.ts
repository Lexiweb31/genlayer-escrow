import { describe, expect, it } from "vitest";
import { addressMatches, jobRelevantToWallet, notificationForStatus } from "@/lib/notifications";
import type { JobRecord } from "@/lib/types";

const job: JobRecord = { address: "0x1111111111111111111111111111111111111111", status: "AGREED", client_address: "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", worker_address: "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB" };

describe("lifecycle notifications", () => {
  it("matches wallet roles without case sensitivity", () => {
    expect(addressMatches("0xaaaa", "0xAAAA")).toBe(true);
    expect(jobRelevantToWallet(job, "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")).toBe(true);
    expect(jobRelevantToWallet(job, "0xcccccccccccccccccccccccccccccccccccccccc")).toBe(false);
  });

  it("creates an acceptance notification linked to the job", () => {
    const item = notificationForStatus(job, "AGREED", "2026-07-16T20:00:00.000Z");
    expect(item?.title).toBe("Worker accepted the job");
    expect(item?.jobAddress).toBe(job.address);
    expect(item?.read).toBe(false);
  });

  it("gives the client the next required action after work is submitted", () => {
    const item = notificationForStatus(
      { ...job, status: "SUBMITTED" },
      "SUBMITTED",
      "2026-07-16T20:00:00.000Z",
      job.client_address,
    );
    expect(item?.title).toBe("Work ready for evaluation");
    expect(item?.message).toContain("request GenLayer evaluation");
  });

  it("gives the worker a role-specific funded-job action", () => {
    const item = notificationForStatus(
      { ...job, status: "OPEN" },
      "OPEN",
      "2026-07-16T20:00:00.000Z",
      job.worker_address,
    );
    expect(item?.title).toBe("Assigned job funded");
    expect(item?.message).toContain("accept the job requirements");
  });

  it("does not claim a notification for unchanged waiting state", () => {
    expect(notificationForStatus({ ...job, status: "UNFUNDED" }, "UNFUNDED")).toBeNull();
  });
});
