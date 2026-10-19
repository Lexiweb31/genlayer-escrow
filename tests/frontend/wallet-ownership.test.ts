import { afterEach, describe, expect, it, vi } from "vitest";
import { meritApi } from "@/lib/api";
import { ownershipMessage, signOwnedJobsAccess } from "@/lib/wallet-ownership";

const address = "0xAbC0000000000000000000000000000000000000";
const storage = new Map<string, string>();

function installBrowser(request: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("window", {
    ethereum: { request },
    sessionStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    },
  });
}

afterEach(() => {
  storage.clear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("owned-job wallet proof", () => {
  it("creates the exact bounded Bradbury ownership message", () => {
    expect(ownershipMessage("0xAbC", new Date("2026-08-11T12:15:00.000Z"))).toBe(
      "Merit needs-funding access\nAddress: 0xabc\nNetwork: testnet_bradbury\nExpires: 2026-08-11T12:15:00.000Z",
    );
  });

  it("signs the canonical message and keeps the proof only in session storage", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:05:00.000Z"));
    const request = vi.fn().mockResolvedValue("0xsigned-proof");
    installBrowser(request);

    await expect(signOwnedJobsAccess(address)).resolves.toEqual({
      address,
      message: "Merit needs-funding access\nAddress: 0xabc0000000000000000000000000000000000000\nNetwork: testnet_bradbury\nExpires: 2026-08-11T12:15:00.000Z",
      signature: "0xsigned-proof",
      demo_mode: false as const,
    });
    expect(request).toHaveBeenCalledWith({
      method: "personal_sign",
      params: [
        "Merit needs-funding access\nAddress: 0xabc0000000000000000000000000000000000000\nNetwork: testnet_bradbury\nExpires: 2026-08-11T12:15:00.000Z",
        address,
      ],
    });
    expect([...storage.values()].join(" ")).toContain("0xsigned-proof");
  });

  it("reuses an unexpired proof but signs again after its expiry", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-11T12:05:00.000Z"));
    const request = vi.fn().mockResolvedValue("0xfresh-proof");
    installBrowser(request);

    await signOwnedJobsAccess(address);
    await signOwnedJobsAccess(address);
    expect(request).toHaveBeenCalledTimes(1);

    vi.setSystemTime(new Date("2026-08-11T12:15:00.001Z"));
    await signOwnedJobsAccess(address);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("sends the signed proof in a same-origin POST body", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [] }) });
    vi.stubGlobal("fetch", fetch);
    const input = {
      address,
      message: "Merit needs-funding access\nAddress: 0xabc0000000000000000000000000000000000000\nNetwork: testnet_bradbury\nExpires: 2026-08-11T12:15:00.000Z",
      signature: "0xsigned-proof",
      demo_mode: false as const,
    };

    await expect(meritApi.ownedJobs(input)).resolves.toEqual({ jobs: [] });
    expect(fetch).toHaveBeenCalledWith("/api/jobs/owned", expect.objectContaining({
      method: "POST",
      body: JSON.stringify(input),
    }));
  });
});
