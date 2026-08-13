import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { meritApi } from "@/lib/api";
import { sanitizeBackendPayload } from "@/lib/server/proxy-policy";

const root = process.cwd();

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function sourceFiles(directory: string): string[] {
  const absolute = join(root, directory);
  return readdirSync(absolute).flatMap((entry) => {
    const path = join(absolute, entry);
    if (statSync(path).isDirectory()) return sourceFiles(relative(root, path));
    return /\.(ts|tsx|js|jsx)$/.test(entry) ? [path] : [];
  });
}

describe("server-only environment boundary", () => {
  it("keeps the checked-in environment example limited to server variable names", () => {
    expect(readFileSync(join(root, ".env.example"), "utf8")).toBe(
      "RENDER_API_BASE_URL=\nGENLAYER_NETWORK=\nGENLAYER_EXPLORER_BASE_URL=\n",
    );
  });

  it("does not reference public-prefixed environment variables", () => {
    const files = [
      ...sourceFiles("app"),
      ...sourceFiles("components"),
      ...sourceFiles("lib"),
    ];
    for (const file of files) {
      expect(readFileSync(file, "utf8"), relative(root, file)).not.toContain("NEXT" + "_PUBLIC_");
    }
  });

  it("reads process environment values only in the server configuration module", () => {
    const files = [
      ...sourceFiles("app"),
      ...sourceFiles("components"),
      ...sourceFiles("lib"),
    ];
    const readers = files
      .filter((file) => readFileSync(file, "utf8").includes("process.env"))
      .map((file) => relative(root, file));
    expect(readers).toEqual(["lib/server/config.ts"]);
  });

  it("removes signature-shaped backend response fields without dropping public job data", () => {
    const signature = `0x${"ab".repeat(65)}`;
    const result = sanitizeBackendPayload({
      jobs: [{
        address: "0x1111111111111111111111111111111111111111",
        title: "Recovered client job",
        status: "UNFUNDED",
        signature,
        ownership_signature: signature,
        recoverySignatureProof: signature,
      }],
    }, "Bradbury testnet");

    expect(result).toEqual({
      jobs: [{
        address: "0x1111111111111111111111111111111111111111",
        title: "Recovered client job",
        status: "UNFUNDED",
      }],
    });
    expect(JSON.stringify(result)).not.toContain(signature);
  });

  it("keeps a recovery signature out of URLs and application logs", async () => {
    const signature = `0x${"cd".repeat(65)}`;
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [] }) });
    vi.stubGlobal("fetch", fetch);
    const loggers = [
      vi.spyOn(console, "debug").mockImplementation(() => undefined),
      vi.spyOn(console, "error").mockImplementation(() => undefined),
      vi.spyOn(console, "info").mockImplementation(() => undefined),
      vi.spyOn(console, "log").mockImplementation(() => undefined),
      vi.spyOn(console, "warn").mockImplementation(() => undefined),
    ];

    await meritApi.ownedJobs({
      address: "0x1111111111111111111111111111111111111111",
      message: "bounded recovery proof",
      signature,
      demo_mode: false,
    });

    const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/jobs/owned");
    expect(new URL(url, "https://merit.example").search).toBe("");
    expect(url).not.toContain(signature);
    expect(init.body).toContain(signature);
    for (const logger of loggers) {
      expect(JSON.stringify(logger.mock.calls)).not.toContain(signature);
    }
  });
});
