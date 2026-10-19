// @vitest-environment jsdom
// @vitest-environment-options {"url":"http://localhost/"}

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JobRecord } from "@/lib/types";

const wallet = vi.hoisted(() => ({ current: { mode: "wallet", address: "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" } }));
const jobs = vi.hoisted(() => vi.fn());

vi.mock("next/link", () => ({ default: "a" }));
vi.mock("@/components/providers", () => ({ useWalletMode: () => wallet.current }));
vi.mock("@/lib/api", () => ({ meritApi: { jobs } }));

import { NotificationCenter } from "@/components/notification-center";

const clientA = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const clientB = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const draft: JobRecord = {
  address: "0x1111111111111111111111111111111111111111",
  title: "Private client draft",
  status: "UNFUNDED",
  client_address: clientA,
};

let host: HTMLDivElement;
let root: Root;
const storage = new Map<string, string>();
const localStore = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
  removeItem: (key: string) => { storage.delete(key); },
  clear: () => { storage.clear(); },
};

async function render() {
  await act(async () => { root.render(createElement(NotificationCenter)); });
}

async function tick() {
  await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
}

async function openNotifications() {
  await act(async () => { host.querySelector<HTMLButtonElement>(".notification-trigger")?.click(); });
}

function dispatchOwned(address: string, owned: JobRecord[]) {
  act(() => window.dispatchEvent(new CustomEvent("merit:owned-unfunded-jobs", { detail: { address, jobs: owned } })));
}

beforeEach(async () => {
  wallet.current = { mode: "wallet", address: clientA };
  jobs.mockReset();
  jobs.mockResolvedValue({ jobs: [] });
  storage.clear();
  vi.stubGlobal("localStorage", localStore);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await render();
  await tick();
});

afterEach(async () => {
  await act(async () => { root.unmount(); });
  host.remove();
  storage.clear();
  vi.unstubAllGlobals();
});

describe("owned funding reminders", () => {
  it("shows the authenticated client's recovered unfunded reminder", async () => {
    dispatchOwned(clientA, [draft]);
    await openNotifications();

    expect(host.textContent).toContain("Fund your job to publish it");
    expect(host.querySelector("a")?.getAttribute("href")).toBe(`/jobs/${draft.address}/manage#funding`);
  });

  it("ignores an owned-jobs event for a different viewer", async () => {
    dispatchOwned(clientB, [draft]);
    await openNotifications();

    expect(host.textContent).not.toContain("Fund your job to publish it");
    expect(host.textContent).toContain("You’re all caught up");
  });

  it("removes the reminder when an authenticated refresh returns no drafts", async () => {
    dispatchOwned(clientA, [draft]);
    dispatchOwned(clientA, []);
    await openNotifications();

    expect(host.textContent).not.toContain("Fund your job to publish it");
  });

  it("never renders client A's reminder or funding href after a synchronous switch to client B", async () => {
    dispatchOwned(clientA, [draft]);
    wallet.current = { mode: "wallet", address: clientB };
    await render();
    await openNotifications();

    expect(host.textContent).not.toContain("Fund your job to publish it");
    expect(host.innerHTML).not.toContain(`/jobs/${draft.address}/manage#funding`);
  });

  it("does not let a stale client A registry check repopulate client B", async () => {
    let resolveJobs: (value: { jobs: JobRecord[] }) => void;
    jobs.mockImplementationOnce(() => new Promise<{ jobs: JobRecord[] }>((resolve) => { resolveJobs = resolve; }));
    localStore.setItem(`merit-notification-snapshot-v2:${clientA}`, JSON.stringify({ [draft.address]: "OPEN" }));
    await act(async () => { root.unmount(); });
    root = createRoot(host);
    await render();
    await tick();
    wallet.current = { mode: "wallet", address: clientB };
    await render();
    await tick();
    await act(async () => { resolveJobs!({ jobs: [{ ...draft, status: "AGREED" }] }); });
    await openNotifications();

    expect(host.textContent).not.toContain("Worker accepted the job");
    expect(host.innerHTML).not.toContain(`/jobs/${draft.address}`);
  });
});
