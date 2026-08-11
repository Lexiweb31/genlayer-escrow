import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const useJob = vi.hoisted(() => vi.fn());

vi.mock("next/link", () => ({ default: "a" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "0x1111111111111111111111111111111111111111" }),
  usePathname: () => "/jobs/0x1111111111111111111111111111111111111111/manage",
}));
vi.mock("@/components/providers", () => ({
  useDemoMode: () => ({ demo: { live_actions_enabled: true } }),
  useWalletMode: () => ({ mode: "wallet", address: "0xclient", onBradbury: true, balance: "1 GEN" }),
}));
vi.mock("@/lib/hooks", () => ({ useJob }));
vi.mock("@/lib/api", () => ({
  meritApi: {
    fund: vi.fn(), acceptTerms: vi.fn(), submit: vi.fn(), closeSubmissions: vi.fn(),
    evaluate: vi.fn(), finalize: vi.fn(), registerWalletSettlement: vi.fn(),
  },
  friendlyApiError: () => "Request failed.",
}));
vi.mock("@/lib/wallet-client", () => ({
  sameAddress: (left?: string | null, right?: string | null) => left?.toLowerCase() === right?.toLowerCase(),
  writeWalletContract: vi.fn(),
}));

import ManageJobPage from "@/app/jobs/[id]/manage/page";

function renderPendingSettlement(settlement: Record<string, string>) {
  useJob.mockReturnValue({
    data: {
      meta: {
        address: "0x1111111111111111111111111111111111111111",
        title: "Settlement proof",
        status: "SETTLEMENT_PENDING",
        client_address: "0xclient",
      },
      job: {
        address: "0x1111111111111111111111111111111111111111",
        status: "SETTLEMENT_PENDING",
        client: "0xclient",
        settlement,
        reconcile_age_seconds: 90,
      },
      result: {},
      addresses: {},
      demo: { live_actions_enabled: true },
    },
    error: null,
    loading: false,
    refresh: vi.fn(),
  });
  return renderToStaticMarkup(createElement(ManageJobPage));
}

describe("manage settlement reconciliation guidance", () => {
  it("renders accepted-but-not-final payment guidance with transaction evidence and elapsed context", () => {
    const transaction = `0x${"a".repeat(64)}`;
    const markup = renderPendingSettlement({
      parent_transaction: transaction,
      parent_status: "ACCEPTED",
      transfer_status: "PENDING_FINALIZATION",
    });

    expect(markup).toContain("Bradbury accepted the transaction; wait for transfer finality.");
    expect(markup).toContain("Last reconciliation · 1m ago");
    expect(markup).toContain("View settlement transaction");
    expect(markup).toContain(`/api/explorer/tx/${transaction}`);
    expect(markup).toContain("Check finality");
  });
});
