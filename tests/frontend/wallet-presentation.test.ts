import { describe, expect, it } from "vitest";
import { builderConnectionPresentation, walletAccountPresentation } from "@/lib/wallet-presentation";

describe("wallet status presentation", () => {
  it("shows demo mode as an available test account", () => {
    expect(walletAccountPresentation({
      mode: "demo",
      providerAvailable: false,
      address: null,
      onBradbury: false,
      balance: null,
    })).toEqual({
      title: "Demo account",
      subtitle: "Bradbury testnet",
      indicator: "online",
      notice: "Bradbury testnet",
    });
  });

  it("does not show a disconnected wallet as connected or online", () => {
    expect(walletAccountPresentation({
      mode: "wallet",
      providerAvailable: true,
      address: null,
      onBradbury: false,
      balance: null,
    })).toEqual({
      title: "Wallet not connected",
      subtitle: "Connect to continue",
      indicator: "offline",
      notice: "Wallet not connected",
    });
  });

  it("distinguishes a missing provider, wrong network, and a ready wallet", () => {
    expect(walletAccountPresentation({
      mode: "wallet",
      providerAvailable: false,
      address: null,
      onBradbury: false,
      balance: null,
    })).toEqual({
      title: "Wallet unavailable",
      subtitle: "Install a browser wallet",
      indicator: "offline",
      notice: "Browser wallet required",
    });
    expect(walletAccountPresentation({
      mode: "wallet",
      providerAvailable: true,
      address: "0x1234567890abcdef1234567890abcdef12345678",
      onBradbury: false,
      balance: null,
    })).toEqual({
      title: "0x1234…5678",
      subtitle: "Switch to Bradbury",
      indicator: "warning",
      notice: "Switch network",
    });
    expect(walletAccountPresentation({
      mode: "wallet",
      providerAvailable: true,
      address: "0x1234567890abcdef1234567890abcdef12345678",
      onBradbury: true,
      balance: "3 GEN",
    })).toEqual({
      title: "0x1234…5678",
      subtitle: "3 GEN",
      indicator: "online",
      notice: "Bradbury connected",
    });
  });
});

describe("job builder connection presentation", () => {
  it("does not claim that a wallet is connected when it is absent", () => {
    expect(builderConnectionPresentation({
      mode: "wallet",
      live: false,
      providerAvailable: true,
      address: null,
      onBradbury: false,
    })).toEqual({
      label: "Wallet not connected",
      detail: "Connect a wallet to deploy",
      tone: "warning",
    });
  });

  it("describes ready wallet and demo signing accurately", () => {
    expect(builderConnectionPresentation({
      mode: "wallet",
      live: true,
      providerAvailable: true,
      address: "0x1234567890abcdef1234567890abcdef12345678",
      onBradbury: true,
    })).toEqual({
      label: "Wallet ready",
      detail: "Connected wallet · Bradbury transaction",
      tone: "success",
    });
    expect(builderConnectionPresentation({
      mode: "demo",
      live: true,
      providerAvailable: false,
      address: null,
      onBradbury: false,
    })).toEqual({
      label: "Separate demo roles ready",
      detail: "Server-signed Bradbury testnet transaction",
      tone: "success",
    });
  });
});
