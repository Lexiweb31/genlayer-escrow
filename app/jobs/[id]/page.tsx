"use client";

import { useParams } from "next/navigation";
import { ExternalIcon, RefreshIcon, ShieldIcon } from "@/components/icons";
import { JobNavigation } from "@/components/job-navigation";
import { Lifecycle } from "@/components/lifecycle";
import { SettlementProof } from "@/components/settlement-proof";
import { ErrorState, LoadingState, MonoValue, PageHeader, StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { useJob } from "@/lib/hooks";
import { hasConfirmedEvaluation, settlementPresentation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";
import { addressUrl, shortAddress, txUrl } from "@/lib/utils";

export default function JobOverviewPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { data, error, loading, refresh } = useJob(id);
  if (loading && !data) return <div className="page-container"><JobNavigation id={id}/><LoadingState label="Opening the escrow control room…"/></div>;
  if (error && !data) return <div className="page-container"><JobNavigation id={id}/><ErrorState message={error.message} retry={refresh}/></div>;
  if (!data) return null;
  const job: JobRecord = { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status };
  const view = settlementPresentation(job, data.result);
  const scoreConfirmed = hasConfirmedEvaluation(job, data.result);
  const deploymentLink = txUrl(data.meta.deployment_tx);
  const escrowLink = data.addresses.explorer_escrow || addressUrl(job.address);
  return <div className="page-container">
    <JobNavigation id={id}/>
    <PageHeader eyebrow="Escrow control room" title={data.meta.title || "Intelligent escrow"} description={data.meta.spec || job.spec || "Agreement specification unavailable."} actions={<button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh state</button>}/>
    {job.legacy_contract && <div className="legacy-banner" role="alert"><ShieldIcon/><div><b>Legacy settlement contract — do not fund</b><p>This immutable deployment predates the safe EOA external-message patch. It remains read-only and is not silently migrated.</p></div></div>}
    <section className="overview-grid">
      <article className="panel overview-summary"><div className="panel-heading"><div><p className="card-kicker">Current state</p><h2>{view.label}</h2></div><StatusPill tone={view.isPending ? "warning" : view.isFinalized ? "success" : job.legacy_contract ? "danger" : "info"}>{view.status}</StatusPill></div><div className="amount-display"><span>Contract balance</span><strong>{formatWei(job.amount)}</strong><small>{view.isPending ? "Outbound settlement is queued, not finalized" : view.isFinalized ? "Settlement transfer finalized" : "Locked according to the active lifecycle"}</small></div><div className="summary-grid"><div><span>AI evaluation</span><strong>{scoreConfirmed ? `${data.result.score ?? job.score}/100` : "Not evaluated yet"}</strong></div><div><span>Full-payment threshold</span><strong>{job.min_score ?? 70}/100</strong></div><div><span>Partial floor</span><strong>{job.partial_floor ?? 40}/100</strong></div><div><span>Declared fee</span><strong>{((job.fee_bps ?? 0) / 100).toFixed(2).replace(/\.00$/, "")}%</strong></div></div></article>
      <article className="panel lifecycle-panel"><div className="panel-heading"><div><p className="card-kicker">Lifecycle</p><h2>Agreement → finality</h2></div></div><Lifecycle job={job} result={data.result}/></article>
    </section>
    <SettlementProof job={job} result={data.result}/>
    <section className="panel agreement-panel"><div className="panel-heading"><div><p className="card-kicker">Immutable agreement</p><h2>Acceptance specification</h2></div><StatusPill>Public evidence required</StatusPill></div><blockquote>{data.meta.spec || job.spec}</blockquote><div className="agreement-meta"><div><span>Escrow contract</span><MonoValue title={job.address}>{job.address}</MonoValue>{escrowLink && <a href={escrowLink} target="_blank" rel="noreferrer">Explorer <ExternalIcon size={14}/></a>}</div><div><span>Deployment transaction</span><MonoValue title={data.meta.deployment_tx}>{shortAddress(data.meta.deployment_tx, 12, 8)}</MonoValue>{deploymentLink && <a href={deploymentLink} target="_blank" rel="noreferrer">Explorer <ExternalIcon size={14}/></a>}</div></div></section>
  </div>;
}
