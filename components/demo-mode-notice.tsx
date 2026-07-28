"use client";

import { ShieldIcon, WalletIcon } from "@/components/icons";
import { useDemoMode, useWalletMode } from "@/components/providers";
import { shortAddress } from "@/lib/utils";
import { walletAccountPresentation } from "@/lib/wallet-presentation";

export function DemoModeNotice({ compact = false }: { compact?: boolean }) {
  const { demo, loading, error } = useDemoMode();
  const wallet = useWalletMode();
  const ready = Boolean(demo?.live_actions_enabled);
  const walletPresentation = walletAccountPresentation({
    mode: wallet.mode,
    providerAvailable: wallet.providerAvailable,
    address: wallet.address,
    onBradbury: wallet.onBradbury,
    balance: wallet.balance,
  });
  if (wallet.mode === "wallet") return <aside className="demo-notice wallet-notice" aria-label="Wallet mode notice">
    <div className="demo-icon"><WalletIcon/></div>
    <div className="demo-copy">
      <div className="demo-heading"><strong>Wallet mode</strong><span>{walletPresentation.notice}</span></div>
      <p>{wallet.address ? <>Connected as <b>{shortAddress(wallet.address)}</b>{wallet.balance ? ` · ${wallet.balance}` : ""}. Your wallet controls this account.</> : "Connect a browser wallet to use your own Bradbury account."}</p>
      <details className="demo-technical"><summary>Wallet Mode status</summary><div>Connected wallets sign supported actions only when their address matches the required client or worker role. New escrows require a separate worker address, on-chain deployment verification, and durable marketplace registration. If registration is interrupted, Restore deployed job retries registration without another deployment. The app never falls back to a demo signer in Wallet Mode.</div></details>
      {wallet.error && <div className="wallet-error" role="alert">{wallet.error}</div>}
    </div>
    {!wallet.address ? <button className="wallet-connect" onClick={() => void wallet.connectWallet()} disabled={wallet.status === "connecting"}><WalletIcon/><span>{wallet.status === "connecting" ? "Connecting…" : "Connect wallet"}</span><small>{wallet.providerAvailable ? "Use your Bradbury account" : "Browser wallet required"}</small></button> : !wallet.onBradbury ? <button className="wallet-connect" onClick={() => void wallet.switchToBradbury()} disabled={wallet.status === "switching"}><WalletIcon/><span>{wallet.status === "switching" ? "Switching…" : "Switch to Bradbury"}</span><small>Chain ID 4221 · GEN</small></button> : <button className="wallet-connect" onClick={wallet.useDemoMode}><ShieldIcon/><span>Use Demo Mode</span><small>Return to server-signed testing</small></button>}
  </aside>;
  return <aside className={`demo-notice ${compact ? "compact" : ""}`} aria-label="Demo mode notice">
    <div className="demo-icon"><ShieldIcon/></div>
    <div className="demo-copy">
      <div className="demo-heading"><strong>Demo mode</strong><span>Bradbury testnet</span></div>
      {!compact && <p>Demo mode uses two test accounts to show the complete client and worker flow. No personal wallet is connected.</p>}
      {!compact && <details className="demo-technical"><summary>Technical details</summary><div>{loading ? "Checking the separate server-side demo roles…" : error ? "The Render demo configuration is temporarily unavailable." : ready ? "Transactions are signed by separate server-held Bradbury client and worker accounts." : "Live transactions are disabled. This walkthrough never fakes an on-chain transaction."}</div>{ready && <div className="role-pair"><span>Client {shortAddress(demo?.client_address)}</span><span>Worker {shortAddress(demo?.worker_address)}</span></div>}</details>}
      {wallet.error && <div className="wallet-error" role="alert">{wallet.error}</div>}
    </div>
    <button className="wallet-connect" onClick={() => void wallet.connectWallet()} disabled={wallet.status === "connecting"}><WalletIcon/><span>{wallet.status === "connecting" ? "Connecting…" : "Connect wallet"}</span><small>{wallet.providerAvailable ? "Use your Bradbury account" : "Browser wallet required"}</small></button>
  </aside>;
}
