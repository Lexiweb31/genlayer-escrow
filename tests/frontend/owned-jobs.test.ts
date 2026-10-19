import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { JobRecord } from "@/lib/types";

const useJobs = vi.hoisted(() => vi.fn());
const useOwnedUnfundedJobs = vi.hoisted(() => vi.fn());
const walletMode = vi.hoisted(() => ({ current: { mode: "wallet", address: "0xclient" } }));

vi.mock("next/link", () => ({ default: "a" }));
vi.mock("@/components/providers", () => ({ useWalletMode: () => walletMode.current }));
vi.mock("@/lib/hooks", () => ({ useJobs, useOwnedUnfundedJobs }));

import BrowseJobsPage, { partitionJobs } from "@/app/jobs/page";

const publicJob: JobRecord = {
  address: "0x1111111111111111111111111111111111111111",
  title: "Public job",
  status: "OPEN",
};

const unfundedJob: JobRecord = {
  address: "0x2222222222222222222222222222222222222222",
  title: "Private draft",
  status: "UNFUNDED",
};

function renderPage(owned: JobRecord[] | null) {
  useJobs.mockReturnValue({
    data: {
      jobs: [publicJob],
      stats: {
        locked_wei: "0", pending_settlement_wei: "0", settlement_pending: 0,
        finalized_settlement_wei: "0", finalized_settlements: 0, total_jobs: 1,
        legacy_jobs: 0, degraded_jobs: 0,
      },
    },
    error: null,
    loading: false,
    refresh: vi.fn(),
  });
  useOwnedUnfundedJobs.mockReturnValue({
    data: owned === null ? null : { jobs: owned },
    error: null,
    loading: false,
    load: vi.fn(),
  });
  return renderToStaticMarkup(createElement(BrowseJobsPage));
}

describe("owned unpublished jobs", () => {
  it("keeps recovered unfunded drafts out of live marketplace results", () => {
    const { liveJobs, needsFunding } = partitionJobs([publicJob, unfundedJob], [unfundedJob]);

    expect(liveJobs.map((job) => job.address)).toEqual([publicJob.address]);
    expect(needsFunding.map((job) => job.address)).toEqual([unfundedJob.address]);
  });

  it("does not render client queue details before signed recovery returns drafts", () => {
    const markup = renderPage(null);

    expect(markup).toContain("Recover unpublished jobs");
    expect(markup).not.toContain("Needs funding");
    expect(markup).not.toContain(unfundedJob.title!);
  });

  it("renders only recovered client drafts in the needs-funding queue", () => {
    const markup = renderPage([unfundedJob]);

    expect(markup).toContain("Needs funding");
    expect(markup).toContain(unfundedJob.title!);
    expect(markup).toContain("Not visible to workers");
    expect(markup).toContain("Fund and activate");
  });
});
