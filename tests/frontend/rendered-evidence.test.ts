import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const contractSources = [
  "evaluate_submission.py",
  "freelance_escrow.py",
  "bounty_escrow.py",
].map((name) => ({
  name,
  source: readFileSync(new URL(`../../contracts/${name}`, import.meta.url), "utf8"),
}));
const nextConfig = readFileSync(new URL("../../next.config.ts", import.meta.url), "utf8");

describe("rendered public evidence", () => {
  for (const contract of contractSources) {
    it(`${contract.name} renders the submitted page before evaluation`, () => {
      expect(contract.source).toContain("gl.nondet.web.render");
      expect(contract.source).toContain('mode="text"');
      expect(contract.source).toContain('wait_after_loaded="3s"');
      expect(contract.source).not.toContain("gl.nondet.web.get");
    });
  }

  it("packages both escrow sources with the deployed contract-source endpoint", () => {
    expect(nextConfig).toContain('"./contracts/freelance_escrow.py"');
    expect(nextConfig).toContain('"./contracts/bounty_escrow.py"');
  });
});
