"use client";

import { ShieldIcon, WalletIcon } from "@/components/icons";
import { useDemoMode } from "@/components/providers";
import { shortAddress } from "@/lib/utils";

export function DemoModeNotice({ compact = false }: { compact?: boolean }) {
  const { demo, loading, error } = useDemoMode();
  const ready = Boolean(demo?.live_actions_enabled);
  return <aside className={`demo-notice ${compact ? "compact" : ""}`} aria-label="Demo mode notice">
    <div className="demo-icon"><ShieldIcon/></div>
    <div className="demo-copy">
      <div className="demo-heading"><strong>Demo mode</strong><span>Bradbury testnet</span></div>
      {!compact && <p>Demo mode uses two test accounts to show the complete client and worker flow. No personal wallet is connected.</p>}
      {!compact && <details className="demo-technical"><summary>Technical details</summary><div>{loading ? "Checking the separate server-side demo roles…" : error ? "The Render demo configuration is temporarily unavailable." : ready ? "Transactions are signed by separate server-held Bradbury client and worker accounts." : "Live transactions are disabled. This walkthrough never fakes an on-chain transaction."}</div>{ready && <div className="role-pair"><span>Client {shortAddress(demo?.client_address)}</span><span>Worker {shortAddress(demo?.worker_address)}</span></div>}</details>}
    </div>
    <button className="wallet-soon" disabled title="Wallet signing is not implemented"><WalletIcon/><span>Wallet mode</span><small>Coming soon — connect a Bradbury wallet</small></button>
  </aside>;
}
