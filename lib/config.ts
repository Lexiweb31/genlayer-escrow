export const config = {
  apiBaseUrl: (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, ""),
  network: process.env.NEXT_PUBLIC_GENLAYER_NETWORK || "testnet_bradbury",
  explorerBaseUrl: (
    process.env.NEXT_PUBLIC_EXPLORER_BASE_URL || "https://explorer-bradbury.genlayer.com"
  ).replace(/\/$/, ""),
} as const;
