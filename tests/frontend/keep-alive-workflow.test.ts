import { exec } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { promisify } from "node:util";
import { afterEach, describe, expect, it } from "vitest";

const execAsync = promisify(exec);
const workflowPath = new URL("../../.github/workflows/keep-alive.yml", import.meta.url);
const servers: ReturnType<typeof createServer>[] = [];

async function workflowCommand() {
  const workflow = await readFile(workflowPath, "utf8");
  const inline = workflow.match(/^\s*run:\s*(.+)$/m)?.[1];
  if (inline && inline !== "|") return inline;

  const block = workflow.match(/^\s*run:\s*\|\s*\n((?:\s{10,}.+\n?)+)/m)?.[1];
  if (!block) throw new Error("Keep-alive workflow has no executable command");
  return block
    .split("\n")
    .map((line) => line.replace(/^\s{10}/, ""))
    .join("\n");
}

async function localEndpoint(status: number) {
  const paths: string[] = [];
  const server = createServer((request, response) => {
    paths.push(request.url ?? "");
    response.writeHead(status, { "content-type": "application/json" });
    response.end(JSON.stringify({ status: status === 200 ? "healthy" : "unavailable" }));
  });
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Test server did not bind");
  return { baseUrl: `http://127.0.0.1:${address.port}`, paths };
}

async function runAgainst(baseUrl: string) {
  const command = (await workflowCommand())
    .replace("https://genlayer-escrow.onrender.com", baseUrl)
    .replace("--retry 4", "--retry 1")
    .replace("--retry-delay 10", "--retry-delay 0");
  return execAsync(command, { shell: "/bin/bash" });
}

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map((server) => new Promise<void>((resolve) => server.close(() => resolve()))),
  );
});

describe("Render keep-alive workflow", () => {
  it("checks the real health route", async () => {
    const endpoint = await localEndpoint(200);

    await runAgainst(endpoint.baseUrl);

    expect(endpoint.paths).toEqual(["/api/health"]);
  });

  it("fails visibly when Render stays unavailable", async () => {
    const endpoint = await localEndpoint(503);

    await expect(runAgainst(endpoint.baseUrl)).rejects.toMatchObject({ code: expect.any(Number) });
  });
});
