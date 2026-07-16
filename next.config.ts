import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  outputFileTracingIncludes: {
    "/api/contract-source": ["./contracts/freelance_escrow.py"],
  },
};

export default nextConfig;
