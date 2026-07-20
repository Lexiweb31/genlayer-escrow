"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowIcon, ClockIcon, ExternalIcon, FileIcon, RefreshIcon, ShieldIcon, UserIcon } from "@/components/icons";
import { JobNavigation } from "@/components/job-navigation";
import { Lifecycle } from "@/components/lifecycle";
import { SettlementProof } from "@/components/settlement-proof";
import { useWalletMode } from "@/components/providers";
import { ErrorState, LoadingState, MonoValue, PageHeader, StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { useJob } from "@/lib/hooks";
import { displayEscrowAmountWei, hasConfirmedEvaluation, settlementPresentation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";
import { addressUrl, relativeTime, shortAddress, txUrl } from "@/lib/utils";
import { sameAddress } from "@/lib/wallet-client";

export default function JobOverviewPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const wallet = useWalletMode();
  const { data, error, loading, refresh } = useJob(id);
  if (loading && !data) return <div className="page-container"><JobNavigation id={id}/><LoadingState label="Opening the escrow control room…"/></div>;
  if (error && !data) return <div className="page-container"><JobNavigation id={id}/><ErrorState message={error.message} retry={refresh}/></div>;
  if (!data) return null;
  const job: JobRecord = { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status };
  const view = settlementPresentation(job, data.result);
  const scoreConfirmed = hasConfirmedEvaluation(job, data.result);
  const deploymentLink = txUrl(data.meta.deployment_tx);
  const escrowLink = data.addresses.explorer_escrow || addressUrl(job.address);
  const clientAddress = job.client_address || job.client || data.demo.client_address;
  const workerAddress = job.worker_address || job.worker || data.demo.worker_address;
  const isClient = wallet.mode === "wallet" && sameAddress(wallet.address, clientAddress);
  const isWorker = wallet.mode === "wallet" && sameAddress(wallet.address, workerAddress);
  const viewerRole = wallet.mode === "demo" ? "demo" : isClient ? "client" : isWorker ? "worker" : "visitor";
  const nextHref = viewerRole === "visitor" ? `/jobs/${encodeURIComponent(id)}` : job.status === "SUBMITTED" && viewerRole !== "worker" ? `/jobs/${encodeURIComponent(id)}/evaluation` : `/jobs/${encodeURIComponent(id)}/manage`;
  const nextLabel = viewerRole === "client" ? "Open client workspace" : viewerRole === "worker" ? "Open worker workspace" : viewerRole === "visitor" ? "Public view only" : "Open next action";
  return <div className="page-container">
    <JobNavigation id={id}/>
    <PageHeader eyebrow={viewerRole === "client" ? "Your client job" : viewerRole === "worker" ? "Your assigned work" : "Public protected job"} title={data.meta.title || "Protected job"} description={viewerRole === "worker" ? "Track the requirements you accepted, your public submission, evaluation result, and verified payout." : viewerRole === "client" ? "Track protected funding, worker delivery, evaluation, and final settlement." : data.meta.spec || job.spec || "Job requirements unavailable."} actions={<button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh state</button>}/>
    {job.legacy_contract && <div className="legacy-banner" role="alert"><ShieldIcon/><div><b>Legacy settlement contract — do not fund</b><p>This immutable deployment predates the safe EOA external-message patch. It remains read-only and is not silently migrated.</p></div></div>}
    <section className="overview-grid">
      <article className="panel overview-summary"><div className="panel-heading"><div><p className="card-kicker">Current state</p><h2>{view.label}</h2></div><StatusPill tone={view.isPending ? "warning" : view.isFinalized ? "success" : job.legacy_contract ? "danger" : "info"}>{view.status}</StatusPill></div><div className="amount-display"><span>{view.isFinalized ? "Settled value" : "Protected payment"}</span><strong>{formatWei(displayEscrowAmountWei(job))}</strong><small>{view.isPending ? "Payment transaction submitted · awaiting confirmation" : view.isFinalized ? "Original escrow value distributed through the confirmed settlement" : "Held according to the current job step"}</small></div><div className="summary-grid"><div><span>AI evaluation</span><strong>{scoreConfirmed ? `${data.result.score ?? job.score}/100` : "Not evaluated yet"}</strong></div><div><span>Full payment starts at</span><strong>{job.min_score ?? 70}/100</strong></div><div><span>Refund below</span><strong>{job.partial_floor ?? 40}/100</strong></div><div><span>Merit fee</span><strong>{((job.fee_bps ?? 0) / 100).toFixed(2).replace(/\.00$/, "")}%</strong></div></div></article>
      <article className="panel lifecycle-panel"><div className="panel-heading"><div><p className="card-kicker">Job progress</p><h2>From requirements to payment</h2></div></div><Lifecycle job={job} result={data.result}/></article>
    </section>
    <section className="role-action-strip" aria-label="Role-aware next actions"><article className={isClient ? "active" : ""}><span><UserIcon/></span><div><small>{isClient ? "You are the client" : "Client wallet"}</small><b>{shortAddress(clientAddress)}</b><p>{isClient ? ["UNFUNDED", "EVALUATED"].includes(job.status) ? "Your action is available" : "Waiting for the worker or contract" : "Funds, evaluates, and settles"}</p></div></article><article className={isWorker ? "active" : ""}><span><UserIcon/></span><div><small>{isWorker ? "You are the worker" : "Worker wallet"}</small><b>{shortAddress(workerAddress)}</b><p>{isWorker ? ["OPEN", "AGREED"].includes(job.status) ? "Your action is available" : "No worker action required now" : "Accepts and submits public work"}</p></div></article>{viewerRole === "visitor" ? <span className="button secondary" aria-disabled="true">Connect assigned wallet</span> : <Link className="button primary" href={nextHref}>{nextLabel} <ArrowIcon/></Link>}</section>
    <SettlementProof job={job} result={data.result}/>
    <section className="overview-detail-grid"><article className="panel parties-panel"><div className="panel-heading"><div><p className="card-kicker">People and work</p><h2>Client and worker record</h2></div></div><div className="party-list"><div><UserIcon/><span>Client</span><MonoValue>{job.client_address || job.client || data.demo.client_address || "Unavailable"}</MonoValue></div><div><UserIcon/><span>Worker</span><MonoValue>{job.worker_address || job.worker || data.demo.worker_address || "Unavailable"}</MonoValue></div><div><FileIcon/><span>Finished work</span>{job.submission_url ? <a href={job.submission_url} target="_blank" rel="noreferrer">Open public work <ExternalIcon size={14}/></a> : <strong>Not submitted yet</strong>}</div></div></article><article className="panel activity-panel"><div className="panel-heading"><div><p className="card-kicker">Job activity</p><h2>History</h2></div></div><ol><li><ClockIcon/><div><b>Job published</b><small>{relativeTime(job.created_at) || "Timestamp unavailable"}</small></div></li>{job.deployment_tx && <li><ShieldIcon/><div><b>Contract transaction recorded</b><MonoValue>{shortAddress(job.deployment_tx, 10, 7)}</MonoValue></div></li>}{job.submission_url && <li><FileIcon/><div><b>Work submitted</b><small>Available for inspection</small></div></li>}<li><ClockIcon/><div><b>Last update</b><small>{relativeTime(job.updated_at) || "Timestamp unavailable"}</small></div></li></ol></article></section>
    <section className="panel agreement-panel"><div className="panel-heading"><div><p className="card-kicker">Job agreement</p><h2>Job requirements</h2></div><StatusPill>Public work required</StatusPill></div><blockquote>{data.meta.spec || job.spec}</blockquote><details className="technical-details"><summary>Technical contract details</summary><div className="agreement-meta"><div><span>Escrow contract</span><MonoValue title={job.address}>{job.address}</MonoValue>{escrowLink && <a href={escrowLink} target="_blank" rel="noreferrer">Explorer <ExternalIcon size={14}/></a>}</div><div><span>Deployment transaction</span><MonoValue title={data.meta.deployment_tx}>{shortAddress(data.meta.deployment_tx, 12, 8)}</MonoValue>{deploymentLink && <a href={deploymentLink} target="_blank" rel="noreferrer">Explorer <ExternalIcon size={14}/></a>}</div></div></details></section>
  </div>;
}
