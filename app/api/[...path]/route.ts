import { getServerConfig, publicNetworkLabel, ServerConfigurationError } from "@/lib/server/config";
import {
  isAllowedMeritApiRoute,
  payloadMatchesNetwork,
  publicApiError,
  sanitizeBackendPayload,
} from "@/lib/server/proxy-policy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

const MAX_REQUEST_BYTES = 64 * 1024;
const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

type RouteContext = { params: Promise<{ path: string[] }> };

function json(payload: unknown, status: number): Response {
  return Response.json(payload, {
    status,
    headers: {
      "Cache-Control": "no-store, max-age=0",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function backendUrl(base: URL, segments: string[]): URL {
  const target = new URL(base.toString());
  const prefix = target.pathname.replace(/\/+$/, "");
  target.pathname = `${prefix}/api/${segments.map(encodeURIComponent).join("/")}`;
  return target;
}

function isSameOriginMutation(request: Request): boolean {
  const requestUrl = new URL(request.url);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (origin) {
    let originUrl: URL;
    try {
      originUrl = new URL(origin);
    } catch {
      return false;
    }
    const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
    const requestHost = request.headers.get("host")?.trim();
    const allowedHosts = new Set([requestUrl.host, forwardedHost, requestHost].filter(Boolean));
    const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim();
    const expectedProtocol = forwardedProtocol ? `${forwardedProtocol}:` : requestUrl.protocol;
    if (!allowedHosts.has(originUrl.host) || originUrl.protocol !== expectedProtocol) return false;
  }
  return fetchSite !== "cross-site";
}

async function proxyRequest(request: Request, context: RouteContext): Promise<Response> {
  const { path: segments } = await context.params;
  if (!isAllowedMeritApiRoute(request.method, segments)) {
    return json({ detail: { code: "ROUTE_NOT_ALLOWED", message: "This Merit API route is not available." } }, 404);
  }

  const incomingUrl = new URL(request.url);
  if (incomingUrl.search) {
    return json({ detail: { code: "QUERY_NOT_ALLOWED", message: "Query parameters are not accepted by this route." } }, 400);
  }

  let body: string | undefined;
  if (request.method === "POST") {
    if (!isSameOriginMutation(request)) {
      return json({ detail: { code: "CROSS_ORIGIN_REJECTED", message: "Cross-origin demo actions are not allowed." } }, 403);
    }
    if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
      return json({ detail: { code: "JSON_REQUIRED", message: "Demo actions require a JSON request body." } }, 415);
    }
    body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_REQUEST_BYTES) {
      return json({ detail: { code: "REQUEST_TOO_LARGE", message: "The request body is too large." } }, 413);
    }
    try {
      const parsed = JSON.parse(body);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("object required");
    } catch {
      return json({ detail: { code: "INVALID_JSON", message: "The request body must be a JSON object." } }, 400);
    }
  }

  try {
    const config = getServerConfig();
    const response = await fetch(backendUrl(config.renderApiBaseUrl, segments), {
      method: request.method,
      body,
      cache: "no-store",
      redirect: "error",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      signal: AbortSignal.timeout(115_000),
    });

    const declaredLength = Number(response.headers.get("content-length") || 0);
    if (declaredLength > MAX_RESPONSE_BYTES) {
      return json({ detail: { code: "UPSTREAM_RESPONSE_TOO_LARGE", message: "The demo service returned an oversized response." } }, 502);
    }
    const raw = await response.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_RESPONSE_BYTES) {
      return json({ detail: { code: "UPSTREAM_RESPONSE_TOO_LARGE", message: "The demo service returned an oversized response." } }, 502);
    }

    let payload: unknown = {};
    if (raw) {
      try {
        payload = JSON.parse(raw);
      } catch {
        return json({ detail: { code: "INVALID_UPSTREAM_RESPONSE", message: "The demo service returned an invalid response." } }, 502);
      }
    }

    if (!response.ok) {
      return json(publicApiError(payload, "The Bradbury demo service could not complete this request."), response.status);
    }
    if (!payloadMatchesNetwork(payload, config.genlayerNetwork)) {
      return json({ detail: { code: "NETWORK_MISMATCH", message: "The demo service is connected to an unexpected GenLayer network." } }, 502);
    }
    return json(sanitizeBackendPayload(payload, publicNetworkLabel(config.genlayerNetwork)), response.status);
  } catch (error) {
    if (error instanceof ServerConfigurationError) {
      return json({ detail: { code: "SERVER_CONFIGURATION_ERROR", message: "The Merit server connection is not configured." } }, 503);
    }
    if (error instanceof Error && error.name === "TimeoutError") {
      return json({ detail: { code: "UPSTREAM_TIMEOUT", message: "The Bradbury demo service did not respond in time. Check the transaction before retrying." } }, 504);
    }
    return json({ detail: { code: "UPSTREAM_UNAVAILABLE", message: "The Bradbury demo service is temporarily unavailable." } }, 502);
  }
}

export function GET(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}

export function POST(request: Request, context: RouteContext) {
  return proxyRequest(request, context);
}
