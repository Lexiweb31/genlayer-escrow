import Link from "next/link";
import { ClockIcon, ExternalIcon } from "@/components/icons";
import { MonoValue, StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { hasConfirmedEvaluation, recipientRole, settlementPresentation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";
import { relativeTime, shortAddress, txUrl } from "@/lib/utils";

export function JobCard({ job }: { job: JobRecord }) {
  const view = settlementPresentation(job);
  const scoreConfirmed = hasConfirmedEvaluation(job);
  const positiveTransfers = (job.settlement?.transfers || []).filter((transfer) => BigInt(transfer.amount || "0") > 0n);
  const parent = job.settlement?.parent_transaction;
  const parentLink = job.settlement?.parent_explorer || job.settlement?.explorer || txUrl(parent);
  const tone = view.status === "LEGACY_UNSAFE" ? "danger" : view.isPending ? "warning" : view.isFinalized ? "success" : "info";
  const outcomeClass = view.status === "LEGACY_UNSAFE" ? "outcome-danger" : view.isPending ? "outcome-pending" : view.isFinalized ? view.decision === "REFUNDED" ? "outcome-refund" : "outcome-success" : "";
  return <article className={`job-card ${outcomeClass}`.trim()}>
    <div className="job-card-top"><MonoValue>{shortAddress(job.address, 8, 4)}</MonoValue><StatusPill tone={tone}>{view.label}</StatusPill></div>
    <div><p className="card-kicker">Intelligent escrow</p><h2>{job.title || "Untitled escrow"}</h2><p className="job-spec">{job.spec || "Agreement specification unavailable."}</p></div>
    {view.status === "LEGACY_UNSAFE" && <div className="inline-alert danger"><b>Legacy settlement contract — do not fund.</b><span>This immutable contract predates the safe EOA transfer patch and is read-only.</span></div>}
    {view.isPending && <div className="pending-proof">
      <b>Settlement transfer pending finalization</b>
      {positiveTransfers.map((transfer, index) => <span key={`${transfer.recipient}-${index}`}>{recipientRole(transfer)} · <MonoValue title={transfer.recipient}>{shortAddress(transfer.recipient)}</MonoValue> · {formatWei(transfer.amount)}</span>)}
      {parent && <span>Parent transaction · <MonoValue title={parent}>{shortAddress(parent, 10, 8)}</MonoValue>{parentLink && <a href={parentLink} target="_blank" rel="noreferrer">Explorer <ExternalIcon size={14}/></a>}</span>}
    </div>}
    <div className="job-card-meta"><span>{scoreConfirmed ? `AI score ${job.score}/100` : "Not evaluated yet"}</span><span><ClockIcon size={14}/>{relativeTime(job.created_at) || "Registry record"}</span></div>
    <div className="job-card-foot"><div><small>Escrow value</small><strong>{formatWei(job.amount)}</strong></div><Link className="text-link" href={`/jobs/${encodeURIComponent(job.address)}`}>Open control room <span>→</span></Link></div>
  </article>;
}
