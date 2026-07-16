export const BRADBURY_CHAIN_ID = 4221;
export const BRADBURY_CHAIN_ID_HEX = "0x107d";

export const BRADBURY_CHAIN = {
  chainId: BRADBURY_CHAIN_ID_HEX,
  chainName: "GenLayer Bradbury Testnet",
  nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 },
  rpcUrls: ["https://rpc-bradbury.genlayer.com"],
  blockExplorerUrls: ["https://explorer.testnet-chain.genlayer.com"],
} as const;

export function isBradburyChain(chainId?: string | null): boolean {
  if (!chainId) return false;
  try {
    return Number(BigInt(chainId)) === BRADBURY_CHAIN_ID;
  } catch {
    return false;
  }
}

export function walletErrorMessage(error: unknown): string {
  const candidate = error as { code?: number; message?: string } | null;
  if (candidate?.code === 4001) return "The wallet request was canceled.";
  if (candidate?.code === -32002) return "A wallet request is already open. Finish it in your wallet.";
  if (candidate?.message?.toLowerCase().includes("user rejected")) return "The wallet request was canceled.";
  return candidate?.message || "The wallet could not complete this request.";
}
