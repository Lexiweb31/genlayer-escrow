const SAFE_REFERENCE = /^0x[a-fA-F0-9]{8,128}$/;

export function isSafeExplorerReference(value: string): boolean {
  return SAFE_REFERENCE.test(value);
}

export function explorerRedirectPath(kind: "tx" | "address", value?: string | null): string | null {
  if (!value || !isSafeExplorerReference(value)) return null;
  return `/api/explorer/${kind}/${encodeURIComponent(value)}`;
}
