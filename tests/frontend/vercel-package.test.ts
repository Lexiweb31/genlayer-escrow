import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { FundingActivationBanner } from "@/components/funding-activation-banner";
import { fundingFailurePresentation, type FundingFailureCase } from "@/lib/funding-activation";

const useJobs = vi.hoisted(() => vi.fn());
const useOwnedUnfundedJobs = vi.hoisted(() => vi.fn());
const walletMode = vi.hoisted(() => ({ current: { mode: "wallet", address: null as string | null } }));

vi.mock("next/link", () => ({ default: "a" }));
vi.mock("@/components/providers", () => ({
  useWalletMode: () => walletMode.current,
}));
vi.mock("@/lib/hooks", () => ({ useJobs, useOwnedUnfundedJobs }));

import BrowseJobsPage from "@/app/jobs/page";

const root = process.cwd();

function filesBelow(directory: string): string[] {
  if (!existsSync(directory)) return [];
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory() ? filesBelow(path) : [path];
  });
}

function renderEmptyPublicMarketplace() {
  useJobs.mockReturnValue({
    data: {
      jobs: [],
      stats: {
        locked_wei: "0", pending_settlement_wei: "0", settlement_pending: 0,
        finalized_settlement_wei: "0", finalized_settlements: 0, total_jobs: 0,
        legacy_jobs: 0, degraded_jobs: 0,
      },
    },
    error: null,
    loading: false,
    refresh: vi.fn(),
  });
  useOwnedUnfundedJobs.mockReturnValue({
    data: { jobs: [{ address: "0x9999999999999999999999999999999999999999", title: "Private owned draft", status: "UNFUNDED" }] },
    error: null,
    loading: false,
    load: vi.fn(),
  });
  return renderToStaticMarkup(createElement(BrowseJobsPage));
}

describe("Vercel build package", () => {
  it("includes every file required by the prebuild contract-source generator", () => {
    const ignore = readFileSync(join(root, ".vercelignore"), "utf8");

    expect(ignore).toContain("!/scripts/generate-contract-sources.mjs");
    expect(ignore).toContain("!/contracts/freelance_escrow.py");
    expect(ignore).toContain("!/contracts/bounty_escrow.py");
  });

  it("does not embed a recovery signature in generated browser assets", () => {
    const signature = `0x${"9d".repeat(65)}`;
    const browserAssets = filesBelow(join(root, ".next", "static"));

    expect(browserAssets.length).toBeGreaterThan(0);

    for (const asset of browserAssets) {
      expect(readFileSync(asset).includes(Buffer.from(signature)), asset).toBe(false);
    }
  });

  it.each([
    ["wallet rejection", "REQUIRED", "No GEN moved"],
    ["malformed hash", "FAILED", "transaction hash"],
    ["network timeout", "CONFIRMING", "Check funding status"],
    ["stale snapshot", "CONFIRMING", "confirming on Bradbury"],
    ["contract rejection", "FAILED", "Funding failed"],
    ["API unavailable", "CONFIRMING", "Live updates unavailable"],
  ] as const)("keeps %s truthful", (failure, expectedKind, expectedCopy) => {
    expect(fundingFailurePresentation(failure as FundingFailureCase)).toMatchObject({
      kind: expectedKind,
      copy: expect.stringContaining(expectedCopy),
    });
  });

  it("keeps an empty public marketplace anonymous while explaining client funding recovery", () => {
    const markup = renderEmptyPublicMarketplace();

    expect(markup).toContain("Unpublished jobs may still need client funding");
    expect(markup).not.toContain("Private client recovery");
    expect(markup).not.toContain("Fund your job to publish it");
    expect(markup).not.toContain("Private owned draft");
    expect(markup).not.toContain("0x9999999999999999999999999999999999999999");
    expect(markup).not.toMatch(/0x[0-9a-fA-F]{40}/);
  });

  it("announces the client activation banner as status", () => {
    const markup = renderToStaticMarkup(createElement(FundingActivationBanner, {
      job: { address: "0x1111111111111111111111111111111111111111", status: "UNFUNDED", client_address: "0xclient" },
      viewerAddress: "0xclient",
      role: "client",
      state: { kind: "REQUIRED", label: "Funding required", detail: "Not active", canFund: true },
      href: "/jobs/example/manage#funding",
    }));

    expect(markup).toContain('role="status"');
  });
});
