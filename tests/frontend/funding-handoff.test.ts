import { describe, expect, it } from "vitest";
import { fundingManageHref, shouldShowFundingBanner } from "@/components/funding-activation-banner";

const unfundedJob = {
  address: "0x1111111111111111111111111111111111111111",
  status: "UNFUNDED" as const,
  client_address: "0xclient",
  worker_address: "0xworker",
};

describe("funding handoff", () => {
  it("routes a deployed job to its funding panel", () => {
    expect(fundingManageHref("0xabc")).toBe("/jobs/0xabc/manage#funding");
  });

  it("does not expose the client funding banner to the worker", () => {
    expect(shouldShowFundingBanner(unfundedJob, unfundedJob.worker_address)).toBe(false);
    expect(shouldShowFundingBanner(unfundedJob, unfundedJob.client_address)).toBe(true);
  });

  it("does not expose the client funding banner to an unrelated wallet", () => {
    expect(shouldShowFundingBanner(unfundedJob, "0xvisitor")).toBe(false);
  });
});
