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
      <div className="demo-heading"><strong>Demo mode</strong><span>Server-signed · Bradbury testnet</span></div>
      {!compact && <p>{loading ? "Checking separate server-side demo roles…" : error ? "The Render demo configuration is temporarily unavailable." : ready ? "Separate Bradbury demo client and worker accounts sign on the server. Visitors do not control deposited GEN." : "Live transactions are disabled. The interface remains an explicitly simulated walkthrough and never fakes an on-chain transaction."}</p>}
      {!compact && ready && <div className="role-pair"><span>Client {shortAddress(demo?.client_address)}</span><span>Worker {shortAddress(demo?.worker_address)}</span></div>}
    </div>
    <button className="wallet-soon" disabled title="Wallet signing is not implemented"><WalletIcon/><span>Wallet mode</span><small>Coming soon — connect a Bradbury wallet</small></button>
  </aside>;
}
