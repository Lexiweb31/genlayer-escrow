import { CheckIcon, ClockIcon, ExternalIcon } from "@/components/icons";
import { EscrowCoreMark } from "@/components/escrow-core-mark";
import { MonoValue, StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { recipientRole, settlementPresentation } from "@/lib/settlement";
import type { EvaluationResult, JobRecord } from "@/lib/types";
import { shortAddress, txUrl } from "@/lib/utils";

export function SettlementProof({ job, result }: { job: JobRecord; result?: EvaluationResult }) {
  const view = settlementPresentation(job, result);
  const settlement = job.settlement || {};
  const parentStatus = String(settlement.parent_status || "UNKNOWN").toUpperCase();
  const failed = ["CANCELED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"].includes(parentStatus);
  const transfers = (settlement.transfers || []).filter((transfer) => BigInt(transfer.amount || "0") > 0n);
  const parentLink = settlement.parent_explorer || settlement.explorer || txUrl(settlement.parent_transaction);
  if (!settlement.parent_transaction && !view.isFinalized) {
    return <section className="panel settlement-panel"><div className="panel-heading"><div><p className="card-kicker">Payment</p><h2>No payment transaction yet</h2></div><StatusPill>Waiting</StatusPill></div><p className="muted">The recipient, amount, and transaction link will appear after the evaluation result submits a payment or refund.</p></section>;
  }
  const outcomeClass = view.isFinalized ? view.decision === "REFUNDED" ? "outcome-refund" : "outcome-success" : "outcome-pending";
  return <section className={`panel settlement-panel ${outcomeClass}`}>
    <div className="panel-heading settlement-heading"><EscrowCoreMark size="small" tone={view.isFinalized ? view.decision === "REFUNDED" ? "danger" : "success" : "pending"}/><div><p className="card-kicker">Payment record</p><h2>{view.label}</h2></div><StatusPill tone={view.isFinalized ? "success" : failed ? "danger" : "warning"}>{view.isFinalized ? <><CheckIcon size={14}/> Payment confirmed</> : failed ? "Transaction failed" : <><ClockIcon size={14}/> Awaiting finality</>}</StatusPill></div>
    {view.decision && <div className="decision-row"><span>Evaluation result</span><strong>{view.decision === "ACCEPTED" ? "Full payment" : view.decision === "REFUNDED" ? "Client refund" : "Split payment"}</strong><small>{view.isFinalized ? "Payment transaction verified" : "Result recorded; payment is not confirmed yet"}</small></div>}
    {transfers.length > 0 && <div className="payment-summary">{transfers.map((transfer, index) => <div key={`${transfer.recipient}-summary-${index}`}><span>{recipientRole(transfer)}</span><strong>{formatWei(transfer.amount)}</strong><small>{shortAddress(transfer.recipient, 8, 6)}</small></div>)}</div>}
    <details className="technical-details"><summary>Technical payment details</summary><div className="transfer-list">{transfers.length ? transfers.map((transfer, index) => {
      const evidence = settlement.transfer_evidence?.find((item) => item.recipient === transfer.recipient && item.settlement_type === transfer.settlement_type);
      const link = evidence?.explorer || parentLink;
      return <article className="transfer-row" key={`${transfer.recipient}-${index}`}><div><span>{recipientRole(transfer)}</span><MonoValue title={transfer.recipient}>{shortAddress(transfer.recipient, 8, 6)}</MonoValue></div><strong>{formatWei(transfer.amount)}</strong><div><StatusPill tone={view.isFinalized ? "success" : "warning"}>{evidence?.status || (view.isFinalized ? "CONFIRMED" : "PENDING")}</StatusPill>{link && <a className="icon-link" href={link} target="_blank" rel="noreferrer" aria-label={`Open ${recipientRole(transfer)} transaction in explorer`}><ExternalIcon/></a>}</div></article>;
    }) : <p className="muted">The contract has not exposed non-zero transfer rows yet. Refresh safely before retrying any action.</p>}</div>
    {settlement.parent_transaction && <div className="parent-proof"><span>Bradbury transaction · {parentStatus}</span><MonoValue title={settlement.parent_transaction}>{settlement.parent_transaction}</MonoValue>{parentLink && <a href={parentLink} target="_blank" rel="noreferrer">Inspect on Bradbury <ExternalIcon size={14}/></a>}</div>}</details>
  </section>;
}
