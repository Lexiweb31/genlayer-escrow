import {
  bountyContractSource,
  freelanceContractSource,
} from "@/lib/server/contract-sources.generated";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const kind = new URL(request.url).searchParams.get("type");
  const source = kind === "bounty" ? bountyContractSource : freelanceContractSource;
  return new Response(source, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
