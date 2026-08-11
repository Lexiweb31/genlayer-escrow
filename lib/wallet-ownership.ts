"use client";

import type { OwnedJobsRequest } from "@/lib/types";

const ACCESS_DURATION_MS = 10 * 60_000;
const STORAGE_KEY_PREFIX = "merit-owned-jobs-access:";

interface BrowserProvider {
  request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>;
}

function browserProvider(): BrowserProvider | null {
  if (typeof window === "undefined") return null;
  return (window as Window & { ethereum?: BrowserProvider }).ethereum || null;
}

function storageFor(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function storageKey(address: string): string {
  return `${STORAGE_KEY_PREFIX}${address.toLowerCase()}`;
}

export function ownershipMessage(address: string, expiresAt: Date): string {
  return [
    "Merit needs-funding access",
    `Address: ${address.toLowerCase()}`,
    "Network: testnet_bradbury",
    `Expires: ${expiresAt.toISOString()}`,
  ].join("\n");
}

function cachedProof(address: string): OwnedJobsRequest | null {
  const storage = storageFor();
  if (!storage) return null;
  const key = storageKey(address);
  try {
    const value: unknown = JSON.parse(storage.getItem(key) || "null");
    if (!value || typeof value !== "object") return null;
    const input = value as Partial<OwnedJobsRequest>;
    if (input.address !== address || input.demo_mode !== false || typeof input.message !== "string" || typeof input.signature !== "string") {
      storage.removeItem(key);
      return null;
    }
    const expires = /^Merit needs-funding access\nAddress: [^\n]+\nNetwork: testnet_bradbury\nExpires: (.+)$/.exec(input.message)?.[1];
    const expiresAt = expires ? new Date(expires) : null;
    if (!expiresAt || Number.isNaN(expiresAt.getTime()) || expiresAt.getTime() <= Date.now() || input.message !== ownershipMessage(address, expiresAt)) {
      storage.removeItem(key);
      return null;
    }
    return input as OwnedJobsRequest;
  } catch {
    try { storage.removeItem(key); } catch { /* session storage is optional */ }
    return null;
  }
}

function cacheProof(input: OwnedJobsRequest): void {
  const storage = storageFor();
  if (!storage) return;
  try {
    storage.setItem(storageKey(input.address), JSON.stringify(input));
  } catch {
    // Private browsing or a full session store should not prevent recovery.
  }
}

export async function signOwnedJobsAccess(address: string): Promise<OwnedJobsRequest> {
  const cached = cachedProof(address);
  if (cached) return cached;

  const provider = browserProvider();
  if (!provider) throw new Error("Connect the client wallet to load jobs that still need funding.");
  const expiresAt = new Date(Date.now() + ACCESS_DURATION_MS);
  const message = ownershipMessage(address, expiresAt);
  const signature = String(await provider.request({ method: "personal_sign", params: [message, address] }));
  const input: OwnedJobsRequest = { address, message, signature, demo_mode: false };
  cacheProof(input);
  return input;
}
