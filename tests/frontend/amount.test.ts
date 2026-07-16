import { describe, expect, it } from "vitest";
import { formatWei, genToWei, isAtLeastMinimumDemoAmount, MIN_DEMO_AMOUNT_WEI } from "@/lib/amount";

describe("GEN and wei conversion", () => {
  it("converts decimal GEN without floating-point math", () => {
    expect(genToWei("0.001")).toBe("1000000000000000");
    expect(genToWei("1.000000000000000001")).toBe("1000000000000000001");
    expect(genToWei("9007199254740993.123456789012345678")).toBe(
      "9007199254740993123456789012345678",
    );
  });

  it("rejects unsafe or ambiguous numeric syntax", () => {
    expect(() => genToWei("1e-3")).toThrow();
    expect(() => genToWei("0.0000000000000000001")).toThrow();
    expect(() => genToWei("-1")).toThrow();
    expect(() => genToWei("1.2.3")).toThrow();
  });

  it("enforces the 0.001 GEN demo minimum", () => {
    expect(MIN_DEMO_AMOUNT_WEI).toBe(1_000_000_000_000_000n);
    expect(isAtLeastMinimumDemoAmount("0.001")).toBe(true);
    expect(isAtLeastMinimumDemoAmount("0.000999999999999999")).toBe(false);
  });

  it("never rounds nonzero wei to zero GEN", () => {
    expect(formatWei("1")).toBe("0.000000000000000001 GEN");
    expect(formatWei("999")).toBe("0.000000000000000999 GEN");
    expect(formatWei("980000000000000")).toBe("0.00098 GEN");
    expect(formatWei("0")).toBe("0 GEN");
  });
});
