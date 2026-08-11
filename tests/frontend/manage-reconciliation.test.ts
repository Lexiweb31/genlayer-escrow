// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://localhost/"}

import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const useJob = vi.hoisted(() => vi.fn());
const registerWalletFunding = vi.hoisted(() => vi.fn());
const readBradburyTransaction = vi.hoisted(() => vi.fn());
const storage = new Map<string, string>();
const localStore = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
  removeItem: (key: string) => { storage.delete(key); },
  clear: () => { storage.clear(); },
};
const walletMode = vi.hoisted(() => ({
  current: { mode: "wallet" as "wallet" | "demo", address: "0xclient" as string | null, onBradbury: true, balance: "1 GEN" },
}));

vi.mock("next/link", () => ({ default: "a" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "0x1111111111111111111111111111111111111111" }),
  usePathname: () => "/jobs/0x1111111111111111111111111111111111111111/manage",
}));
vi.mock("@/components/providers", () => ({
  useDemoMode: () => ({ demo: { live_actions_enabled: true } }),
  useWalletMode: () => walletMode.current,
}));
vi.mock("@/lib/hooks", () => ({ useJob }));
vi.mock("@/lib/api", () => ({
  meritApi: {
    fund: vi.fn(), acceptTerms: vi.fn(), submit: vi.fn(), closeSubmissions: vi.fn(),
    evaluate: vi.fn(), finalize: vi.fn(), registerWalletSettlement: vi.fn(), registerWalletFunding,
  },
  friendlyApiError: () => "Request failed.",
}));
vi.mock("@/lib/wallet-client", () => ({
  sameAddress: (left?: string | null, right?: string | null) => Boolean(left && right && left.toLowerCase() === right.toLowerCase()),
  readBradburyTransaction,
  writeWalletContract: vi.fn(),
}));

import ManageJobPage from "@/app/jobs/[id]/manage/page";

beforeEach(() => {
  storage.clear();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("localStorage", localStore);
});

function renderPendingSettlement(settlement: Record<string, string>, visitor = false) {
  walletMode.current = {
    mode: "wallet",
    address: visitor ? "0xvisitor" : "0xclient",
    onBradbury: true,
    balance: "1 GEN",
  };
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

function renderUnfundedWorkspace({ address, jobType = "DIRECT_HIRE", mode = "wallet", demoClientAddress = "0xclient" }: { address: string | null; jobType?: "DIRECT_HIRE" | "BOUNTY"; mode?: "wallet" | "demo"; demoClientAddress?: string }) {
  walletMode.current = { mode, address, onBradbury: true, balance: "1 GEN" };
  useJob.mockReturnValue({
    data: {
      meta: {
        address: "0x1111111111111111111111111111111111111111",
        title: "Funding gate",
        status: "UNFUNDED",
        client_address: "0xclient",
        worker_address: jobType === "DIRECT_HIRE" ? "0xworker" : undefined,
        job_type: jobType,
      },
      job: {
        address: "0x1111111111111111111111111111111111111111",
        status: "UNFUNDED",
        client: "0xclient",
        worker: jobType === "DIRECT_HIRE" ? "0xworker" : undefined,
        job_type: jobType,
      },
      result: {},
      addresses: {},
      demo: { live_actions_enabled: true, client_address: demoClientAddress },
    },
    error: null,
    loading: false,
    refresh: vi.fn(),
  });
  return renderToStaticMarkup(createElement(ManageJobPage));
}

async function mountUnfundedRecovery(hash: string, receipt: Record<string, unknown>) {
  registerWalletFunding.mockClear();
  readBradburyTransaction.mockClear();
  walletMode.current = { mode: "wallet", address: "0xclient", onBradbury: true, balance: "1 GEN" };
  const refresh = vi.fn();
  useJob.mockReturnValue({
    data: {
      meta: { address: "0x1111111111111111111111111111111111111111", title: "Funding recovery", status: "UNFUNDED", client_address: "0xclient", worker_address: "0xworker" },
      job: { address: "0x1111111111111111111111111111111111111111", status: "UNFUNDED", client: "0xclient", worker: "0xworker" },
      result: {}, addresses: {}, demo: { live_actions_enabled: true, client_address: "0xclient" },
    },
    error: null,
    loading: false,
    refresh,
  });
  localStorage.setItem("merit-pending-action:0x1111111111111111111111111111111111111111", JSON.stringify({
    label: "Funding escrow",
    hash,
    startingStatus: "UNFUNDED",
  }));
  readBradburyTransaction.mockResolvedValue(receipt);
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => { root.render(createElement(ManageJobPage)); });
  await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
  return { host, refresh, unmount: async () => { await act(async () => root.unmount()); host.remove(); } };
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

  it("renders reconciliation evidence instead of generic visitor copy for a pending payment", () => {
    const transaction = `0x${"b".repeat(64)}`;
    const markup = renderPendingSettlement({
      parent_transaction: transaction,
      parent_status: "ACCEPTED",
      transfer_status: "PENDING_FINALIZATION",
    }, true);

    expect(markup).toContain("Bradbury accepted the transaction; wait for transfer finality.");
    expect(markup).toContain("Last reconciliation · 1m ago");
    expect(markup).toContain(`/api/explorer/tx/${transaction}`);
    expect(markup).toContain("Check finality");
    expect(markup).not.toContain("Public job status");
    expect(markup).not.toContain("Verify and recover payment");
  });

  it("blocks a visitor from client funding controls while the job is unfunded", () => {
    const markup = renderUnfundedWorkspace({ address: "0xvisitor" });

    expect(markup).toContain("This job is awaiting client funding");
    expect(markup).not.toContain("Client wallet required");
    expect(markup).not.toContain("Lock 0.001 GEN");
  });

  it("keeps an unfunded Bounty entrant out of the submission form", () => {
    const markup = renderUnfundedWorkspace({ address: "0xentrant", jobType: "BOUNTY" });

    expect(markup).toContain("This Bounty opens after the reward is funded");
    expect(markup).not.toContain("Public link to finished work");
    expect(markup).not.toContain("Open 0.001 GEN Bounty");
  });

  it("keeps the server demo client on the post-publish funding path", () => {
    const markup = renderUnfundedWorkspace({ address: null, mode: "demo" });

    expect(markup).toContain("Fund and activate job");
    expect(markup).toContain("Fund with demo client");
    expect(markup).not.toContain("Only the recorded client wallet can activate this agreement.");
  });

  it("does not let a retained wallet address authorize the server demo client", () => {
    const markup = renderUnfundedWorkspace({ address: "0xclient", mode: "demo", demoClientAddress: "0xdemo" });

    expect(markup).toContain("This job is awaiting client funding");
    expect(markup).not.toContain("Fund and activate job");
    expect(markup).not.toContain("Fund with demo client");
  });

  it("registers a successful saved funding hash after refresh without enabling a duplicate", async () => {
    const hash = `0x${"c".repeat(64)}`;
    registerWalletFunding.mockResolvedValue({ job_status: "UNFUNDED" });

    const mounted = await mountUnfundedRecovery(hash, {
      status: "FINALIZED",
      executionResult: "FINISHED_WITH_RETURN",
      result: "SUCCESS",
      failed: false,
      confirmed: true,
    });

    expect(readBradburyTransaction).toHaveBeenCalledWith(hash);
    expect(registerWalletFunding).toHaveBeenCalledWith("0x1111111111111111111111111111111111111111", hash);
    expect(mounted.refresh).toHaveBeenCalledOnce();
    expect(localStorage.getItem("merit-pending-action:0x1111111111111111111111111111111111111111")).toContain(hash);
    expect(mounted.host.textContent).toContain("Transaction submitted — confirming on Bradbury");
    expect(mounted.host.querySelector("button.primary.large")).toBeNull();
    await mounted.unmount();
    localStorage.clear();
  });

  it("does not treat an unknown refreshed snapshot as funding activation", async () => {
    const hash = `0x${"e".repeat(64)}`;
    registerWalletFunding.mockResolvedValue({ job_status: "UNKNOWN" });

    const mounted = await mountUnfundedRecovery(hash, {
      status: "FINALIZED",
      executionResult: "FINISHED_WITH_RETURN",
      result: "SUCCESS",
      failed: false,
      confirmed: true,
    });

    expect(localStorage.getItem("merit-pending-action:0x1111111111111111111111111111111111111111")).toContain(hash);
    expect(mounted.host.textContent).toContain("Transaction submitted — confirming on Bradbury");
    expect(mounted.host.querySelector("button.primary.large")).toBeNull();
    await mounted.unmount();
    localStorage.clear();
  });

  it("renders a failed saved funding reference before clearing it and enabling retry", async () => {
    const hash = `0x${"d".repeat(64)}`;

    const mounted = await mountUnfundedRecovery(hash, {
      status: "CANCELED",
      executionResult: "UNKNOWN",
      result: "UNKNOWN",
      failed: true,
      confirmed: false,
    });

    expect(registerWalletFunding).not.toHaveBeenCalled();
    expect(localStorage.getItem("merit-pending-action:0x1111111111111111111111111111111111111111")).toBeNull();
    expect(mounted.host.textContent).toContain("Funding failed");
    expect(mounted.host.innerHTML).toContain(`/api/explorer/tx/${hash}`);
    expect(mounted.host.querySelector<HTMLButtonElement>("button.primary.large")?.disabled).toBe(false);
    await mounted.unmount();
    localStorage.clear();
  });
});
