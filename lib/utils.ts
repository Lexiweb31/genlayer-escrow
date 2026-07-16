import { explorerRedirectPath } from "@/lib/explorer";

export function shortAddress(value?: string | null, leading = 6, trailing = 4): string {
  if (!value) return "Not available";
  if (value.length <= leading + trailing + 3) return value;
  return `${value.slice(0, leading)}…${value.slice(-trailing)}`;
}

export function txUrl(hash?: string | null): string | null {
  return explorerRedirectPath("tx", hash);
}

export function addressUrl(address?: string | null): string | null {
  return explorerRedirectPath("address", address);
}

export function relativeTime(value?: string): string {
  if (!value) return "";
  const elapsed = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(elapsed)) return "";
  const minutes = Math.max(0, Math.floor(elapsed / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
