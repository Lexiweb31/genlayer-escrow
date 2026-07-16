import { describe, expect, it } from "vitest";
import { BRADBURY_CHAIN_ID, BRADBURY_CHAIN_ID_HEX, isBradburyChain, walletErrorMessage } from "@/lib/wallet";

describe("Bradbury wallet configuration", () => {
  it("uses the documented Bradbury chain id", () => {
    expect(BRADBURY_CHAIN_ID).toBe(4221);
    expect(BRADBURY_CHAIN_ID_HEX).toBe("0x107d");
    expect(isBradburyChain("0x107d")).toBe(true);
    expect(isBradburyChain("4221")).toBe(true);
    expect(isBradburyChain("0x1")).toBe(false);
  });

  it("turns wallet rejection codes into useful messages", () => {
    expect(walletErrorMessage({ code: 4001 })).toBe("The wallet request was canceled.");
    expect(walletErrorMessage({ code: -32002 })).toContain("already open");
  });
});
