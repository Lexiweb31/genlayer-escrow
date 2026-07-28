import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const root = process.cwd();

describe("Vercel build package", () => {
  it("includes every file required by the prebuild contract-source generator", () => {
    const ignore = readFileSync(join(root, ".vercelignore"), "utf8");

    expect(ignore).toContain("!/scripts/generate-contract-sources.mjs");
    expect(ignore).toContain("!/contracts/freelance_escrow.py");
    expect(ignore).toContain("!/contracts/bounty_escrow.py");
  });
});
