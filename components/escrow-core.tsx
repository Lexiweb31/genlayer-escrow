import { CheckIcon, ClockIcon, ExternalIcon, FileIcon, UserIcon } from "@/components/icons";
import { EscrowCoreMark } from "@/components/escrow-core-mark";
import { MonoValue, StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { shortAddress } from "@/lib/utils";

export { EscrowCoreMark } from "@/components/escrow-core-mark";

export function ValidatorQuorum({ confirmed = false, illustrative = false, score }: { confirmed?: boolean; illustrative?: boolean; score?: number | null }) {
  const center = Math.min(100, Math.max(0, score ?? 82));
  const illustrativeScores = [-2, 1, 0, -1, 2].map((offset) => Math.min(100, Math.max(0, center + offset)));
  return <div className={`validator-quorum ${confirmed ? "confirmed" : "pending"}`} aria-label={illustrative ? "Illustrative five-validator score sequence" : confirmed ? "Consensus confirmed; individual validator votes are not exposed by the backend" : "Validator results pending"}>
    {illustrativeScores.map((nodeScore, index) => <div className="validator-node" key={`validator-${index}`} style={{ "--node-delay": `${index * 120}ms` } as React.CSSProperties}>
      <span>V{index + 1}</span>
      <strong>{illustrative ? nodeScore : confirmed ? "✓" : "—"}</strong>
      <small>{illustrative ? "illustrative" : confirmed ? "quorum" : "waiting"}</small>
    </div>)}
    {confirmed && score != null && <p className="validator-consensus"><CheckIcon size={14}/> Consensus {score}/100 <span>Individual votes not returned</span></p>}
  </div>;
}

export function EscrowProductVisual({ amount = "1000000000000000", score = 82, address = "0x8F12A6e2C934bF91", transaction = "0x7bd4e9a31c...a821", outcome = "Worker payout" }: { amount?: string; score?: number; address?: string; transaction?: string; outcome?: string }) {
  return <div className="product-composition" aria-label="Illustrative Merit escrow product preview">
    <div className="composition-label"><span>Illustrative product preview</span><StatusPill tone="success"><i className="live-dot"/> Bradbury</StatusPill></div>
    <div className="composition-stage">
      <div className="party-card client"><span className="party-icon"><UserIcon/></span><div><small>Demo client</small><b>Agreement owner</b><MonoValue>0x5955…E2A7</MonoValue></div><StatusPill tone="info">Funded</StatusPill></div>
      <div className="party-card worker"><span className="party-icon"><UserIcon/></span><div><small>Demo worker</small><b>Evidence author</b><MonoValue>0xf55d…599f</MonoValue></div><StatusPill tone="success">Submitted</StatusPill></div>
      <div className="proof-line line-client"><i/></div><div className="proof-line line-worker"><i/></div>
      <div className="hero-core"><EscrowCoreMark size="large"/><small>Locked escrow</small><strong>{formatWei(amount)}</strong><MonoValue>{shortAddress(address, 8, 5)}</MonoValue></div>
      <div className="evidence-float"><FileIcon size={16}/><div><small>Public evidence</small><b>deliverable.vercel.app</b></div><CheckIcon size={15}/></div>
      <div className="validator-float"><span>Illustrative validator sequence</span><ValidatorQuorum illustrative score={score}/><div className="consensus-score"><small>Illustrative consensus</small><strong>{score}<i>/100</i></strong></div></div>
      <div className="receipt-float"><div><small>Settlement result</small><b>{outcome}</b><MonoValue>Registry-linked preview</MonoValue></div><div className="receipt-amount"><CheckIcon/><strong>{formatWei(amount)}</strong></div><a href="#product-proof" aria-label="See live explorer proof below">Explorer proof <ExternalIcon size={13}/></a><MonoValue>{transaction}</MonoValue></div>
    </div>
  </div>;
}

export function StoryEscrowCore({ activeStep }: { activeStep: number }) {
  return <div className={`story-core stage-${activeStep}`} aria-hidden="true">
    <span className="story-party client"><UserIcon/><b>Client</b></span>
    <span className="story-party worker"><UserIcon/><b>Worker</b></span>
    <div className="story-proof client-proof"><i/></div><div className="story-proof worker-proof"><i/></div>
    <EscrowCoreMark size="large" tone={activeStep >= 7 ? "success" : activeStep >= 6 ? "pending" : "active"}/>
    <div className="story-validators">{[1,2,3,4,5].map((node) => <i key={node} className={activeStep >= 4 + node / 6 ? "on" : ""}>{node}</i>)}</div>
    <span className="story-result">{activeStep >= 7 ? <><CheckIcon/> Explorer proof</> : activeStep >= 6 ? <><ClockIcon/> Settlement queued</> : activeStep >= 5 ? `${82}/100 consensus` : "Evidence routing"}</span>
  </div>;
}
