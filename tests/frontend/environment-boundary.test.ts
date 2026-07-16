import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

const root = process.cwd();

function sourceFiles(directory: string): string[] {
  const absolute = join(root, directory);
  return readdirSync(absolute).flatMap((entry) => {
    const path = join(absolute, entry);
    if (statSync(path).isDirectory()) return sourceFiles(relative(root, path));
    return /\.(ts|tsx|js|jsx)$/.test(entry) ? [path] : [];
  });
}

describe("server-only environment boundary", () => {
  it("keeps the checked-in environment example limited to server variable names", () => {
    expect(readFileSync(join(root, ".env.example"), "utf8")).toBe(
      "RENDER_API_BASE_URL=\nGENLAYER_NETWORK=\nGENLAYER_EXPLORER_BASE_URL=\n",
    );
  });

  it("does not reference public-prefixed environment variables", () => {
    const files = [
      ...sourceFiles("app"),
      ...sourceFiles("components"),
      ...sourceFiles("lib"),
    ];
    for (const file of files) {
      expect(readFileSync(file, "utf8"), relative(root, file)).not.toContain("NEXT" + "_PUBLIC_");
    }
  });

  it("reads process environment values only in the server configuration module", () => {
    const files = [
      ...sourceFiles("app"),
      ...sourceFiles("components"),
      ...sourceFiles("lib"),
    ];
    const readers = files
      .filter((file) => readFileSync(file, "utf8").includes("process.env"))
      .map((file) => relative(root, file));
    expect(readers).toEqual(["lib/server/config.ts"]);
  });
});
