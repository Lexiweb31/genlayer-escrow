export const WEI_PER_GEN = 1_000_000_000_000_000_000n;
export const MIN_DEMO_AMOUNT_WEI = 1_000_000_000_000_000n;

export function genToWei(value: string): string {
  const input = value.trim();
  if (!/^\d+(?:\.\d{0,18})?$/.test(input)) {
    throw new Error("Enter a decimal GEN amount with no more than 18 decimal places.");
  }
  const [whole, fraction = ""] = input.split(".");
  const wei = BigInt(whole) * WEI_PER_GEN + BigInt((fraction + "0".repeat(18)).slice(0, 18));
  return wei.toString();
}

export function formatWei(value: string | number | bigint | null | undefined): string {
  let wei: bigint;
  try {
    wei = BigInt(value ?? 0);
  } catch {
    wei = 0n;
  }
  if (wei === 0n) return "0 GEN";
  const sign = wei < 0n ? "-" : "";
  const absolute = wei < 0n ? -wei : wei;
  const whole = absolute / WEI_PER_GEN;
  const fraction = (absolute % WEI_PER_GEN).toString().padStart(18, "0").replace(/0+$/, "");
  return `${sign}${whole}${fraction ? `.${fraction}` : ""} GEN`;
}

export function isAtLeastMinimumDemoAmount(value: string): boolean {
  try {
    return BigInt(genToWei(value)) >= MIN_DEMO_AMOUNT_WEI;
  } catch {
    return false;
  }
}
