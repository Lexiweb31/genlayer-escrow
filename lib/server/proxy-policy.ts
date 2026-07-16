import { explorerRedirectPath, isSafeExplorerReference } from "@/lib/explorer";

const ACTIONS = new Set(["fund", "accept_terms", "submit", "evaluate", "appeal", "finalize"]);
const MAX_SANITIZE_DEPTH = 20;

const BLOCKED_RESPONSE_KEYS = new Set([
  "config",
  "configuration",
  "database_url",
  "db_url",
  "demo_client_private_key",
  "demo_worker_private_key",
  "deployer_private_key",
  "env",
  "environment",
  "error",
  "password",
  "persist_data_dir",
  "private_key",
  "render_api_base_url",
  "secret",
  "server_signer_configuration",
  "signer_configuration",
  "status_error",
  "testnet_detail",
  "token",
]);

function normalizedKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function isBlockedResponseKey(key: string): boolean {
  const normalized = normalizedKey(key);
  return BLOCKED_RESPONSE_KEYS.has(normalized) || normalized.endsWith("_private_key");
}

function rewriteExplorerUrl(value: string): string | null {
  try {
    const url = new URL(value);
    const parts = url.pathname.split("/").filter(Boolean);
    const kindIndex = parts.findIndex((part) => part === "tx" || part === "address");
    if (kindIndex < 0 || !parts[kindIndex + 1]) return null;
    const kind = parts[kindIndex] as "tx" | "address";
    return explorerRedirectPath(kind, decodeURIComponent(parts[kindIndex + 1]));
  } catch {
    return null;
  }
}

export function isAllowedMeritApiRoute(method: string, segments: string[]): boolean {
  if (method === "GET") {
    if (segments.length === 1) return segments[0] === "demo-mode" || segments[0] === "jobs";
    return segments.length === 2 && segments[0] === "jobs" && isSafeExplorerReference(segments[1]);
  }

  if (method === "POST") {
    if (segments.length === 1) return segments[0] === "jobs";
    if (segments.length === 2) return segments[0] === "jobs" && segments[1] === "register";
    return segments.length === 3
      && segments[0] === "jobs"
      && isSafeExplorerReference(segments[1])
      && ACTIONS.has(segments[2]);
  }

  return false;
}

function normalizedNetwork(value: string): string {
  return value.toLowerCase().replace(/^testnet[_-]?/, "").replace(/[^a-z0-9]/g, "");
}

export function payloadMatchesNetwork(payload: unknown, expectedNetwork: string): boolean {
  const expected = normalizedNetwork(expectedNetwork);
  const visit = (value: unknown, depth: number): boolean => {
    if (depth > MAX_SANITIZE_DEPTH || value === null || typeof value !== "object") return true;
    if (Array.isArray(value)) return value.every((item) => visit(item, depth + 1));
    return Object.entries(value).every(([key, item]) => {
      if (normalizedKey(key) === "network" && typeof item === "string") {
        return normalizedNetwork(item) === expected;
      }
      return visit(item, depth + 1);
    });
  };
  return visit(payload, 0);
}

export function sanitizeBackendPayload(
  payload: unknown,
  networkLabel: string,
  depth = 0,
): unknown {
  if (depth > MAX_SANITIZE_DEPTH) return null;
  if (payload === null || typeof payload === "string" || typeof payload === "number" || typeof payload === "boolean") {
    return payload;
  }
  if (Array.isArray(payload)) {
    return payload.map((item) => sanitizeBackendPayload(item, networkLabel, depth + 1));
  }
  if (typeof payload !== "object") return null;

  const output: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (isBlockedResponseKey(key)) continue;
    const normalized = normalizedKey(key);
    if (normalized === "network") {
      output[key] = networkLabel;
      continue;
    }
    if (normalized.includes("explorer")) {
      output[key] = typeof value === "string" ? rewriteExplorerUrl(value) : null;
      continue;
    }
    output[key] = sanitizeBackendPayload(value, networkLabel, depth + 1);
  }
  return output;
}

function safeText(value: unknown, fallback: string, maxLength = 300): string {
  if (typeof value !== "string") return fallback;
  const text = value.trim();
  return text ? text.slice(0, maxLength) : fallback;
}

export function publicApiError(payload: unknown, fallbackMessage: string): { detail: Record<string, string> } {
  const source = payload && typeof payload === "object" && "detail" in payload
    ? (payload as { detail?: unknown }).detail
    : null;
  const detail = source && typeof source === "object" ? source as Record<string, unknown> : {};
  const codeValue = typeof detail.code === "string" && /^[A-Z0-9_]{2,64}$/.test(detail.code)
    ? detail.code
    : "UPSTREAM_ERROR";
  const result: Record<string, string> = {
    code: codeValue,
    message: safeText(detail.message, fallbackMessage),
  };
  if (typeof detail.action === "string") result.action = safeText(detail.action, "", 240);
  if (typeof detail.minimum_wei === "string" && /^\d{1,80}$/.test(detail.minimum_wei)) {
    result.minimum_wei = detail.minimum_wei;
  }
  return { detail: result };
}
