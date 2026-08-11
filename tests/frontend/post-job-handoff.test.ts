// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://localhost/"}

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.hoisted(() => vi.fn());
const wallet = vi.hoisted(() => ({ current: { mode: "demo" as "demo" | "wallet", address: null as string | null, onBradbury: true, balance: "1 GEN" } }));
const createJob = vi.hoisted(() => vi.fn());
const registerWalletJob = vi.hoisted(() => vi.fn());
const deployWalletEscrow = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/components/providers", () => ({
  useDemoMode: () => ({ demo: { live_actions_enabled: true, platform_address: "0xplatform" } }),
  useWalletMode: () => wallet.current,
}));
vi.mock("@/lib/api", () => ({ meritApi: { createJob, registerWalletJob }, friendlyApiError: () => "Request failed." }));
vi.mock("@/lib/wallet-client", () => ({
  deployWalletEscrow,
  deployWalletBounty: vi.fn(),
  sameAddress: (left?: string | null, right?: string | null) => Boolean(left && right && left.toLowerCase() === right.toLowerCase()),
}));

import PostJobPage from "@/app/jobs/new/page";

let host: HTMLDivElement;
let root: Root;
const storage = new Map<string, string>();
const localStore = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
  removeItem: (key: string) => { storage.delete(key); },
  clear: () => { storage.clear(); },
};

function button(label: string) {
  const match = [...host.querySelectorAll("button")].find((element) => element.textContent?.includes(label));
  if (!match) throw new Error(`Missing button: ${label}`);
  return match;
}

async function click(label: string) {
  await act(async () => { button(label).click(); });
}

async function waitForEffects() {
  await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
}

async function completeBuilder() {
  const requirements = host.querySelector("textarea");
  if (!requirements) throw new Error("Missing requirements input");
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  setter?.call(requirements, "Build a public, accessible, and testable deliverable with clear acceptance criteria.");
  await act(async () => { requirements.dispatchEvent(new Event("input", { bubbles: true })); });
  await click("Continue");
  await click("Continue");
  await click(wallet.current.mode === "wallet" ? "Deploy with connected wallet" : "Confirm and deploy");
}

beforeEach(async () => {
  wallet.current = { mode: "demo", address: null, onBradbury: true, balance: "1 GEN" };
  push.mockReset();
  createJob.mockReset();
  registerWalletJob.mockReset();
  deployWalletEscrow.mockReset();
  storage.clear();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("localStorage", localStore);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, text: async () => "contract source" }));
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => { root.render(createElement(PostJobPage)); });
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  host.remove();
  storage.clear();
  vi.unstubAllGlobals();
});

describe("post-publish funding handoff", () => {
  it("routes a demo createJob response to the funding panel", async () => {
    createJob.mockResolvedValue({ job: { address: "0xdemo" } });

    await completeBuilder();

    expect(push).toHaveBeenCalledWith("/jobs/0xdemo/manage#funding");
  });

  it("routes a wallet registerWalletJob response to the funding panel", async () => {
    wallet.current = { mode: "wallet", address: "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", onBradbury: true, balance: "1 GEN" };
    deployWalletEscrow.mockResolvedValue({ address: "0xwallet", hash: "0xdeploy" });
    registerWalletJob.mockResolvedValue({ job: { address: "0xwallet" } });
    await act(async () => { root.render(createElement(PostJobPage)); });
    const worker = host.querySelector<HTMLInputElement>('input[placeholder="0x…"]');
    if (!worker) throw new Error("Missing worker input");
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(worker, `0x${"b".repeat(40)}`);
    await act(async () => { worker.dispatchEvent(new Event("input", { bubbles: true })); });

    await completeBuilder();

    expect(registerWalletJob).toHaveBeenCalledOnce();
    expect(push).toHaveBeenCalledWith("/jobs/0xwallet/manage#funding");
  });

  it("routes resumed wallet registration to the funding panel", async () => {
    localStore.setItem("merit-pending-wallet-job", JSON.stringify({
      address: "0xresume", client_address: "0xclient", worker_address: "0xworker", deployment_tx: "0xtx",
      spec: "A sufficiently detailed public deliverable.", fee_bps: 200, min_score: 70, partial_floor: 40, job_type: "DIRECT_HIRE", max_submissions: 5,
    }));
    registerWalletJob.mockResolvedValue({ job: { address: "0xresume" } });
    await act(async () => { root.unmount(); });
    root = createRoot(host);
    await act(async () => { root.render(createElement(PostJobPage)); });
    await waitForEffects();

    await click("Restore deployed job");

    expect(push).toHaveBeenCalledWith("/jobs/0xresume/manage#funding");
  });
});
