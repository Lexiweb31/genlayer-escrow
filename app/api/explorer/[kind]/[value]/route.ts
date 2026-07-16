import { getServerConfig, ServerConfigurationError } from "@/lib/server/config";
import { isSafeExplorerReference } from "@/lib/explorer";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ExplorerContext = { params: Promise<{ kind: string; value: string }> };

export async function GET(request: Request, context: ExplorerContext): Promise<Response> {
  const { kind, value } = await context.params;
  if ((kind !== "tx" && kind !== "address") || !isSafeExplorerReference(value)) {
    return Response.json(
      { detail: { code: "INVALID_EXPLORER_REFERENCE", message: "This explorer reference is invalid." } },
      { status: 400, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }
  if (new URL(request.url).search) {
    return Response.json(
      { detail: { code: "QUERY_NOT_ALLOWED", message: "Explorer redirects do not accept query parameters." } },
      { status: 400, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }

  try {
    const { genlayerExplorerBaseUrl } = getServerConfig();
    const target = new URL(genlayerExplorerBaseUrl.toString());
    const prefix = target.pathname.replace(/\/+$/, "");
    target.pathname = `${prefix}/${kind}/${encodeURIComponent(value)}`;
    return new Response(null, {
      status: 307,
      headers: {
        Location: target.toString(),
        "Cache-Control": "no-store, max-age=0",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    if (error instanceof ServerConfigurationError) {
      return Response.json(
        { detail: { code: "SERVER_CONFIGURATION_ERROR", message: "The explorer connection is not configured." } },
        { status: 503, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
      );
    }
    return Response.json(
      { detail: { code: "EXPLORER_UNAVAILABLE", message: "The explorer is temporarily unavailable." } },
      { status: 502, headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  }
}
