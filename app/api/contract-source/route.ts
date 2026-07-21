import { readFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  try {
    const kind = new URL(request.url).searchParams.get("type");
    const filename = kind === "bounty" ? "bounty_escrow.py" : "freelance_escrow.py";
    const source = await readFile(path.join(process.cwd(), "contracts", filename), "utf8");
    return new Response(source, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return Response.json({ detail: { code: "CONTRACT_SOURCE_UNAVAILABLE", message: "The verified escrow source is unavailable." } }, { status: 503 });
  }
}
