import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const useJob = vi.hoisted(() => vi.fn());

vi.mock("next/link", () => ({ default: "a" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "0x1111111111111111111111111111111111111111" }),
  usePathname: () => "/jobs/0x1111111111111111111111111111111111111111",
}));
vi.mock("@/components/providers", () => ({
  useWalletMode: () => ({ mode: "demo", address: null, onBradbury: true }),
}));
vi.mock("@/lib/hooks", () => ({ useJob }));

import JobOverviewPage from "@/app/jobs/[id]/page";

describe("funding overview authorization", () => {
  it("does not treat the demo display address as an unrecorded job client", () => {
    useJob.mockReturnValue({
      data: {
        meta: { address: "0x1111111111111111111111111111111111111111", title: "Unrecorded client", status: "UNFUNDED" },
        job: { address: "0x1111111111111111111111111111111111111111", status: "UNFUNDED" },
        result: {},
        addresses: {},
        demo: { client_address: "0xdemo", worker_address: "0xworker", live_actions_enabled: true },
      },
      error: null,
      loading: false,
      refresh: vi.fn(),
    });

    const markup = renderToStaticMarkup(createElement(JobOverviewPage));

    expect(markup).not.toContain("Fund and activate job");
  });
});
