// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://localhost/"}

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const useJob = vi.hoisted(() => vi.fn());

vi.mock("next/link", () => ({ default: "a" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "0x1111111111111111111111111111111111111111" }),
  usePathname: () => "/jobs/0x1111111111111111111111111111111111111111/manage",
}));
vi.mock("@/components/providers", () => ({
  useDemoMode: () => ({ demo: { live_actions_enabled: true, client_address: "0xclient" } }),
  useWalletMode: () => ({ mode: "wallet", address: "0xclient", onBradbury: true, balance: "1 GEN" }),
}));
vi.mock("@/lib/hooks", () => ({ useJob }));
vi.mock("@/lib/api", () => ({
  meritApi: { fund: vi.fn(), acceptTerms: vi.fn(), submit: vi.fn(), closeSubmissions: vi.fn(), evaluate: vi.fn(), finalize: vi.fn(), registerWalletSettlement: vi.fn() },
  friendlyApiError: () => "Request failed.",
}));
vi.mock("@/lib/wallet-client", () => ({
  sameAddress: (left?: string | null, right?: string | null) => Boolean(left && right && left.toLowerCase() === right.toLowerCase()),
  writeWalletContract: vi.fn(),
}));

import ManageJobPage from "@/app/jobs/[id]/manage/page";

let host: HTMLDivElement;
let root: Root;

function jobData(status: "UNFUNDED" | "OPEN") {
  return {
    data: {
      meta: { address: "0x1111111111111111111111111111111111111111", title: "Focus target", status, client_address: "0xclient", worker_address: "0xworker" },
      job: { address: "0x1111111111111111111111111111111111111111", status, client: "0xclient", worker: "0xworker" },
      result: {}, addresses: {}, demo: { live_actions_enabled: true, client_address: "0xclient" },
    },
    error: null, loading: false, refresh: vi.fn(),
  };
}

async function render(status: "UNFUNDED" | "OPEN") {
  useJob.mockReturnValue(jobData(status));
  await act(async () => { root.render(createElement(ManageJobPage)); });
  await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
}

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() });
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { callback(0); return 1; });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  host.remove();
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
});

describe("funding hash focus", () => {
  it("focuses the funding heading for a verified unfunded job", async () => {
    window.history.replaceState(null, "", "#funding");

    await render("UNFUNDED");

    expect(document.activeElement).toBe(host.querySelector("#funding"));
  });

  it("does not move focus from an external control when the verified job is not unfunded", async () => {
    const external = document.createElement("button");
    document.body.append(external);
    external.focus();
    window.history.replaceState(null, "", "#funding");

    await render("OPEN");

    expect(document.activeElement).toBe(external);
    external.remove();
  });
});
