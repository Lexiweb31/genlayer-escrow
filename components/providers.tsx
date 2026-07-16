"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { meritApi } from "@/lib/api";
import { formatWei } from "@/lib/amount";
import type { DemoConfig } from "@/lib/types";
import { BRADBURY_CHAIN, BRADBURY_CHAIN_ID_HEX, isBradburyChain, walletErrorMessage } from "@/lib/wallet";

interface DemoContextValue {
  demo: DemoConfig | null;
  loading: boolean;
  error: Error | null;
}

const DemoContext = createContext<DemoContextValue>({ demo: null, loading: true, error: null });

type AccountMode = "demo" | "wallet";
type WalletStatus = "idle" | "connecting" | "connected" | "switching";

interface InjectedProvider {
  request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>;
  on?(event: "accountsChanged" | "chainChanged", listener: (value: unknown) => void): void;
  removeListener?(event: "accountsChanged" | "chainChanged", listener: (value: unknown) => void): void;
}

interface WalletContextValue {
  mode: AccountMode;
  address: string | null;
  balance: string | null;
  chainId: string | null;
  providerAvailable: boolean;
  status: WalletStatus;
  error: string | null;
  onBradbury: boolean;
  connectWallet(): Promise<void>;
  switchToBradbury(): Promise<void>;
  useDemoMode(): void;
}

const WalletContext = createContext<WalletContextValue | null>(null);

function injectedProvider(): InjectedProvider | null {
  if (typeof window === "undefined") return null;
  return (window as Window & { ethereum?: InjectedProvider }).ethereum || null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [demo, setDemo] = useState<DemoConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [mode, setMode] = useState<AccountMode>("demo");
  const [address, setAddress] = useState<string | null>(null);
  const [balance, setBalance] = useState<string | null>(null);
  const [chainId, setChainId] = useState<string | null>(null);
  const [providerAvailable, setProviderAvailable] = useState(false);
  const [walletStatus, setWalletStatus] = useState<WalletStatus>("idle");
  const [walletError, setWalletError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    meritApi.demoMode(controller.signal).then(setDemo).catch((nextError: unknown) => {
      if ((nextError as Error).name !== "AbortError") {
        setError(nextError instanceof Error ? nextError : new Error("Demo configuration unavailable."));
      }
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const refreshBalance = useCallback(async (nextAddress: string, provider = injectedProvider()) => {
    if (!provider) return;
    const wei = await provider.request({ method: "eth_getBalance", params: [nextAddress, "latest"] });
    setBalance(formatWei(String(wei)));
  }, []);

  const switchToBradbury = useCallback(async () => {
    const provider = injectedProvider();
    if (!provider) {
      setWalletError("Install a browser wallet such as MetaMask to use Wallet Mode.");
      return;
    }
    setWalletStatus("switching");
    setWalletError(null);
    try {
      await provider.request({ method: "wallet_switchEthereumChain", params: [{ chainId: BRADBURY_CHAIN_ID_HEX }] });
      setChainId(BRADBURY_CHAIN_ID_HEX);
    } catch (nextError) {
      const candidate = nextError as { code?: number };
      if (candidate?.code !== 4902) {
        setWalletError(walletErrorMessage(nextError));
        setWalletStatus(address ? "connected" : "idle");
        return;
      }
      try {
        await provider.request({ method: "wallet_addEthereumChain", params: [BRADBURY_CHAIN] });
        setChainId(BRADBURY_CHAIN_ID_HEX);
      } catch (addError) {
        setWalletError(walletErrorMessage(addError));
        setWalletStatus(address ? "connected" : "idle");
        return;
      }
    }
    setWalletStatus(address ? "connected" : "idle");
  }, [address]);

  const connectWallet = useCallback(async () => {
    // Record the user's mode choice before touching the provider. A missing,
    // disconnected, or rejected wallet must never fall back to demo signing.
    setMode("wallet");
    localStorage.setItem("merit-account-mode", "wallet");
    const provider = injectedProvider();
    if (!provider) {
      setProviderAvailable(false);
      setWalletError("Install a browser wallet such as MetaMask to use Wallet Mode.");
      return;
    }
    setWalletStatus("connecting");
    setWalletError(null);
    try {
      const accounts = await provider.request({ method: "eth_requestAccounts" }) as string[];
      const nextAddress = accounts[0] || null;
      if (!nextAddress) throw new Error("The wallet did not return an account.");
      setAddress(nextAddress);
      const nextChain = String(await provider.request({ method: "eth_chainId" }));
      setChainId(nextChain);
      if (isBradburyChain(nextChain)) await refreshBalance(nextAddress, provider);
      setWalletStatus("connected");
    } catch (nextError) {
      setWalletError(walletErrorMessage(nextError));
      setWalletStatus("idle");
    }
  }, [refreshBalance]);

  const useDemoMode = useCallback(() => {
    setMode("demo");
    setWalletError(null);
    localStorage.setItem("merit-account-mode", "demo");
  }, []);

  useEffect(() => {
    const provider = injectedProvider();
    const savedMode = localStorage.getItem("merit-account-mode");
    queueMicrotask(() => {
      setProviderAvailable(Boolean(provider));
      if (savedMode === "wallet") setMode("wallet");
    });
    if (!provider) return;

    const sync = async () => {
      try {
        const [accounts, nextChain] = await Promise.all([
          provider.request({ method: "eth_accounts" }) as Promise<string[]>,
          provider.request({ method: "eth_chainId" }) as Promise<string>,
        ]);
        const nextAddress = accounts[0] || null;
        setAddress(nextAddress);
        setChainId(nextChain);
        if (nextAddress) {
          setWalletStatus("connected");
          if (isBradburyChain(nextChain)) await refreshBalance(nextAddress, provider);
          if (localStorage.getItem("merit-account-mode") === "wallet") setMode("wallet");
        }
      } catch (nextError) {
        setWalletError(walletErrorMessage(nextError));
      }
    };
    void sync();

    const onAccountsChanged = (value: unknown) => {
      const accounts = value as string[];
      const nextAddress = accounts[0] || null;
      setAddress(nextAddress);
      setBalance(null);
      if (!nextAddress) {
        setWalletStatus("idle");
        setWalletError("The wallet disconnected. Reconnect it or explicitly choose Demo Mode.");
      } else {
        setWalletStatus("connected");
        if (isBradburyChain(chainId)) void refreshBalance(nextAddress, provider);
      }
    };
    const onChainChanged = (value: unknown) => {
      const nextChain = String(value);
      setChainId(nextChain);
      setBalance(null);
      if (address && isBradburyChain(nextChain)) void refreshBalance(address, provider);
    };
    provider.on?.("accountsChanged", onAccountsChanged);
    provider.on?.("chainChanged", onChainChanged);
    return () => {
      provider.removeListener?.("accountsChanged", onAccountsChanged);
      provider.removeListener?.("chainChanged", onChainChanged);
    };
  }, [address, chainId, refreshBalance]);

  const value = useMemo(() => ({ demo, loading, error }), [demo, loading, error]);
  const walletValue = useMemo<WalletContextValue>(() => ({
    mode, address, balance, chainId, providerAvailable, status: walletStatus, error: walletError,
    onBradbury: isBradburyChain(chainId), connectWallet, switchToBradbury, useDemoMode,
  }), [mode, address, balance, chainId, providerAvailable, walletStatus, walletError, connectWallet, switchToBradbury, useDemoMode]);
  return <DemoContext.Provider value={value}><WalletContext.Provider value={walletValue}>{children}</WalletContext.Provider></DemoContext.Provider>;
}

export function useDemoMode() {
  return useContext(DemoContext);
}

export function useWalletMode() {
  const value = useContext(WalletContext);
  if (!value) throw new Error("useWalletMode must be used inside Providers.");
  return value;
}
