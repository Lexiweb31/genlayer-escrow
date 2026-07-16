import { CheckIcon, ClockIcon, ExternalIcon } from "@/components/icons";
import { MonoValue, StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { recipientRole, settlementPresentation } from "@/lib/settlement";
import type { EvaluationResult, JobRecord } from "@/lib/types";
import { shortAddress, txUrl } from "@/lib/utils";

export function SettlementProof({ job, result }: { job: JobRecord; result?: EvaluationResult }) {
  const view = settlementPresentation(job, result);
  const settlement = job.settlement || {};
  const transfers = (settlement.transfers || []).filter((transfer) => BigInt(transfer.amount || "0") > 0n);
  const parentLink = settlement.parent_explorer || settlement.explorer || txUrl(settlement.parent_transaction);
  if (!settlement.parent_transaction && !view.isFinalized) {
    return <section className="panel settlement-panel"><div className="panel-heading"><div><p className="card-kicker">Settlement evidence</p><h2>Not queued yet</h2></div><StatusPill>Waiting</StatusPill></div><p className="muted">A recipient, amount, and explorer reference will appear only after the contract queues an outbound transfer.</p></section>;
  }
  return <section className="panel settlement-panel">
    <div className="panel-heading"><div><p className="card-kicker">Settlement evidence</p><h2>{view.label}</h2></div><StatusPill tone={view.isFinalized ? "success" : "warning"}>{view.isFinalized ? <><CheckIcon size={14}/> Finalized</> : <><ClockIcon size={14}/> Pending finalization</>}</StatusPill></div>
    {view.decision && <div className="decision-row"><span>Contract decision</span><strong>{view.decision}</strong><small>{view.isFinalized ? "Outbound transfer verified" : "Decision recorded; transfer is not complete"}</small></div>}
    <div className="transfer-list">{transfers.length ? transfers.map((transfer, index) => {
      const evidence = settlement.transfer_evidence?.find((item) => item.recipient === transfer.recipient && item.settlement_type === transfer.settlement_type);
      const link = evidence?.explorer || parentLink;
      return <article className="transfer-row" key={`${transfer.recipient}-${index}`}><div><span>{recipientRole(transfer)}</span><MonoValue title={transfer.recipient}>{shortAddress(transfer.recipient, 8, 6)}</MonoValue></div><strong>{formatWei(transfer.amount)}</strong><div><StatusPill tone={view.isFinalized ? "success" : "warning"}>{evidence?.status || (view.isFinalized ? "CONFIRMED" : "PENDING")}</StatusPill>{link && <a className="icon-link" href={link} target="_blank" rel="noreferrer" aria-label={`Open ${recipientRole(transfer)} transaction in explorer`}><ExternalIcon/></a>}</div></article>;
    }) : <p className="muted">The contract has not exposed non-zero transfer rows yet. Refresh safely before retrying any action.</p>}</div>
    {settlement.parent_transaction && <div className="parent-proof"><span>Parent transaction</span><MonoValue title={settlement.parent_transaction}>{settlement.parent_transaction}</MonoValue>{parentLink && <a href={parentLink} target="_blank" rel="noreferrer">Inspect on Bradbury <ExternalIcon size={14}/></a>}</div>}
  </section>;
}
