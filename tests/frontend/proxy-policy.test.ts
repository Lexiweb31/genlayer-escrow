import { describe, expect, it } from "vitest";
import { explorerRedirectPath } from "@/lib/explorer";
import {
  isAllowedMeritApiRoute,
  payloadMatchesNetwork,
  publicApiError,
  sanitizeBackendPayload,
} from "@/lib/server/proxy-policy";

describe("same-origin Merit proxy policy", () => {
  const address = "0x1234567890abcdef1234567890abcdef12345678";
  const hash = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd";

  it("allows only the frontend's explicit API surface", () => {
    expect(isAllowedMeritApiRoute("GET", ["jobs"])).toBe(true);
    expect(isAllowedMeritApiRoute("GET", ["jobs", address])).toBe(true);
    expect(isAllowedMeritApiRoute("POST", ["jobs", address, "finalize"])).toBe(true);
    expect(isAllowedMeritApiRoute("POST", ["jobs", address, "close_submissions"])).toBe(true);
    expect(isAllowedMeritApiRoute("POST", ["jobs", address, "register_settlement"])).toBe(true);
    expect(isAllowedMeritApiRoute("POST", ["jobs", "register"])).toBe(true);
    expect(isAllowedMeritApiRoute("GET", ["health"])).toBe(false);
    expect(isAllowedMeritApiRoute("POST", ["jobs", address, "admin"])).toBe(false);
    expect(isAllowedMeritApiRoute("DELETE", ["jobs", address])).toBe(false);
    expect(isAllowedMeritApiRoute("GET", ["jobs", "../../secrets"])).toBe(false);
  });

  it("removes private configuration and rewrites explorer links to same-origin routes", () => {
    const result = sanitizeBackendPayload({
      network: "testnet_bradbury",
      explorer: `https://explorer-bradbury.genlayer.com/tx/${hash}`,
      nested: {
        client_address: address,
        DEMO_CLIENT_PRIVATE_KEY: "must-not-leak",
        databaseUrl: "must-not-leak",
        testnet_detail: "internal provider detail",
      },
    }, "Bradbury testnet") as Record<string, unknown>;

    expect(result.network).toBe("Bradbury testnet");
    expect(result.explorer).toBe(`/api/explorer/tx/${hash}`);
    expect(JSON.stringify(result)).not.toContain("must-not-leak");
    expect(result.nested).toEqual({ client_address: address });
  });

  it("returns only allowlisted error fields", () => {
    expect(publicApiError({
      detail: {
        code: "STALE_STATE",
        message: "Refresh before retrying.",
        action: "Refresh the job.",
        minimum_wei: "1000000000000000",
        testnet_detail: "private backend exception",
        configured_address: address,
      },
    }, "Fallback")).toEqual({
      detail: {
        code: "STALE_STATE",
        message: "Refresh before retrying.",
        action: "Refresh the job.",
        minimum_wei: "1000000000000000",
      },
    });
  });

  it("rejects mismatched networks and builds safe explorer paths", () => {
    expect(payloadMatchesNetwork({ demo: { network: "testnet_bradbury" } }, "testnet_bradbury")).toBe(true);
    expect(payloadMatchesNetwork({ demo: { network: "testnet_other" } }, "testnet_bradbury")).toBe(false);
    expect(explorerRedirectPath("address", address)).toBe(`/api/explorer/address/${address}`);
    expect(explorerRedirectPath("tx", "javascript:alert(1)")).toBeNull();
  });
});
