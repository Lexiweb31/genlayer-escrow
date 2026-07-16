import { readFile } from "node:fs/promises";
import path from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const source = await readFile(path.join(process.cwd(), "contracts", "freelance_escrow.py"), "utf8");
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
