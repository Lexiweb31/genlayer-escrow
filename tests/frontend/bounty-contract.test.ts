import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("../../contracts/bounty_escrow.py", import.meta.url), "utf8");

describe("Bounty contract safeguards", () => {
  it("keeps Bounty as a separate on-chain lifecycle", () => {
    expect(source).toContain('"job_type": "BOUNTY"');
    expect(source).toContain("def close_submissions");
    expect(source).toContain("def evaluate");
    expect(source).toContain("def finalize");
  });

  it("limits entries and prevents duplicate-wallet submissions", () => {
    expect(source).toContain("max_submissions must be between 2 and 5");
    expect(source).toContain("One submission per wallet");
    expect(source).toContain("Bounty submission limit reached");
  });

  it("uses an explicit qualifying score and deterministic tie-break", () => {
    expect(source).toContain("score > self.winning_score");
    expect(source).toContain("earliest submission as the deterministic tie-breaker");
    expect(source).toContain("NO_QUALIFYING_SUBMISSION");
  });

  it("ranks the complete field in one validator-consensus operation", () => {
    expect(source.match(/run_nondet_unsafe/g)).toHaveLength(1);
    expect(source).toContain("def _run_bounty_evaluation");
    expect(source).toContain("Apply the exact same rubric to every candidate");
    expect(source).toContain("leader_winner == mine_winner");
  });

  it("renders every public entry before the validators score it", () => {
    expect(source).toContain("gl.nondet.web.render");
    expect(source).toContain('mode="text"');
    expect(source).toContain('wait_after_loaded="3s"');
    expect(source).not.toContain("gl.nondet.web.get");
  });

  it("queues either winner payout or client refund through the contract", () => {
    expect(source).toContain("BOUNTY_WINNER_PAYOUT");
    expect(source).toContain("self.settlement_winner_amount = payout");
    expect(source).toContain("self.settlement_client_amount = amount");
  });
});
