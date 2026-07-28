import { shortAddress } from "@/lib/utils";

interface WalletPresentationInput {
  mode: "demo" | "wallet";
  providerAvailable: boolean;
  address: string | null;
  onBradbury: boolean;
  balance: string | null;
}

interface BuilderPresentationInput extends Omit<WalletPresentationInput, "balance"> {
  live: boolean;
}

export function walletAccountPresentation(input: WalletPresentationInput) {
  if (input.mode === "demo") {
    return {
      title: "Demo account",
      subtitle: "Bradbury testnet",
      indicator: "online" as const,
      notice: "Bradbury testnet",
    };
  }
  if (!input.providerAvailable) {
    return {
      title: "Wallet unavailable",
      subtitle: "Install a browser wallet",
      indicator: "offline" as const,
      notice: "Browser wallet required",
    };
  }
  if (!input.address) {
    return {
      title: "Wallet not connected",
      subtitle: "Connect to continue",
      indicator: "offline" as const,
      notice: "Wallet not connected",
    };
  }
  if (!input.onBradbury) {
    return {
      title: shortAddress(input.address),
      subtitle: "Switch to Bradbury",
      indicator: "warning" as const,
      notice: "Switch network",
    };
  }
  return {
    title: shortAddress(input.address),
    subtitle: input.balance || "Bradbury connected",
    indicator: "online" as const,
    notice: "Bradbury connected",
  };
}

export function builderConnectionPresentation(input: BuilderPresentationInput) {
  if (input.mode === "demo") {
    return input.live
      ? { label: "Separate demo roles ready", detail: "Server-signed Bradbury testnet transaction", tone: "success" as const }
      : { label: "Demo transactions unavailable", detail: "Render signer configuration required", tone: "warning" as const };
  }
  if (!input.providerAvailable) {
    return { label: "Browser wallet required", detail: "Install a wallet to deploy", tone: "warning" as const };
  }
  if (!input.address) {
    return { label: "Wallet not connected", detail: "Connect a wallet to deploy", tone: "warning" as const };
  }
  if (!input.onBradbury) {
    return { label: "Wrong network", detail: "Switch to Bradbury to deploy", tone: "warning" as const };
  }
  return input.live
    ? { label: "Wallet ready", detail: "Connected wallet · Bradbury transaction", tone: "success" as const }
    : { label: "Wallet actions unavailable", detail: "Bradbury deployment is temporarily disabled", tone: "warning" as const };
}
