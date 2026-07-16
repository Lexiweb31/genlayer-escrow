"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowIcon, CheckIcon, ExternalIcon, RefreshIcon } from "@/components/icons";
import { EscrowCoreMark, ValidatorQuorum } from "@/components/escrow-core";
import { JobNavigation } from "@/components/job-navigation";
import { useDemoMode } from "@/components/providers";
import { ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/ui";
import { friendlyApiError, meritApi } from "@/lib/api";
import { useJob } from "@/lib/hooks";
import { hasConfirmedEvaluation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";

export default function EvaluationPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { demo } = useDemoMode();
  const { data, error, loading, refresh } = useJob(id);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  if (loading && !data) return <div className="page-container"><JobNavigation id={id}/><LoadingState label="Opening the evaluation evidence room…"/></div>;
  if (error && !data) return <div className="page-container"><JobNavigation id={id}/><ErrorState message={error.message} retry={refresh}/></div>;
  if (!data) return null;
  const job: JobRecord = { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status };
  const evaluated = hasConfirmedEvaluation(job, data.result);
  const live = Boolean(demo?.live_actions_enabled) && !job.legacy_contract;
  const score = data.result?.score ?? job.score ?? 0;
  const evaluationOutcomeClass = score >= (job.min_score ?? 70) ? "outcome-success" : score >= (job.partial_floor ?? 40) ? "outcome-pending" : "outcome-refund";
  const runEvaluation = async () => {
    if (busy) return;
    if (!live) return setMessage("Live evaluation is disabled. No on-chain result was simulated.");
    setBusy(true); setMessage("Submitting a server-signed demo evaluation transaction to Bradbury…");
    try { await meritApi.evaluate(id); setMessage("Evaluation transaction accepted. Reading the confirmed result…"); await refresh(); }
    catch (nextError) { setMessage(friendlyApiError(nextError)); }
    finally { setBusy(false); }
  };
  const appeal = async () => {
    if (busy || !live) return;
    setBusy(true); setMessage("Submitting one server-signed demo appeal…");
    try { await meritApi.appeal(id); setMessage("Appeal accepted. Refreshing the result…"); await refresh(); }
    catch (nextError) { setMessage(friendlyApiError(nextError)); }
    finally { setBusy(false); }
  };
  return <div className="page-container">
    <JobNavigation id={id}/><PageHeader eyebrow="AI Evaluation" title="Check the work against the requirements" description="Merit shows a score only after the backend confirms the evaluation and reasoning." actions={<button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh</button>}/>
    {!evaluated ? <section className="evaluation-empty panel"><span className="evaluation-orb"><EscrowCoreMark/></span><p className="eyebrow">Awaiting confirmed result</p><h2>{job.status === "SUBMITTED" ? "Public work is ready for evaluation." : "No evaluation is available yet."}</h2><p>{job.status === "SUBMITTED" ? "The demo client can ask GenLayer to inspect the submitted URL against the immutable acceptance specification. The UI will show no score until the backend confirms one." : "Complete funding, acceptance, and public submission before starting evaluation."}</p><ValidatorQuorum/>{job.submission_url && <a className="submission-link" href={job.submission_url} target="_blank" rel="noreferrer">Inspect submitted work <ExternalIcon/></a>}{job.status === "SUBMITTED" ? <button className="button primary large" onClick={runEvaluation} disabled={busy || !live}>{busy ? "Evaluating…" : "Evaluate with demo client"}<ArrowIcon/></button> : <Link className="button secondary" href={`/jobs/${encodeURIComponent(id)}/manage`}>Return to Manage Job</Link>}{message && <div className="action-message info" role="status">{message}</div>}</section> : <>
      <section className="evaluation-stage">
        <div className={`score-panel panel ${evaluationOutcomeClass}`}><p className="card-kicker">Backend-confirmed score</p><div className="score-orbit" style={{ "--score": `${score}%` } as React.CSSProperties}><strong>{score}<small>/100</small></strong></div><StatusPill tone={score >= (job.min_score ?? 70) ? "success" : score >= (job.partial_floor ?? 40) ? "warning" : "danger"}>{data.result.settlement_outcome || data.result.status || "Evaluated"}</StatusPill><small>Confirmed result returned by the Render API</small></div>
        <article className="panel reasoning-panel"><div className="panel-heading"><div><p className="card-kicker">Why it received this score</p><h2>Evaluation reasoning</h2></div><StatusPill tone="success"><CheckIcon size={14}/> Evaluation completed</StatusPill></div><ValidatorQuorum confirmed score={score}/><blockquote>{data.result.reasoning || "The backend confirmed a score but did not return explanatory reasoning."}</blockquote><div className="evidence-checks"><span><CheckIcon/> Job requirements loaded</span><span><CheckIcon/> Public work inspected</span><span><CheckIcon/> Payment rule applied</span><span><CheckIcon/> Evaluation result saved</span></div>{job.submission_url && <a className="submission-link" href={job.submission_url} target="_blank" rel="noreferrer">Open evaluated work <ExternalIcon/></a>}<div className={`evaluation-consequence ${evaluationOutcomeClass}`}><span>Payment result</span><strong>{score >= (job.min_score ?? 70) ? "Worker receives full payment" : score >= (job.partial_floor ?? 40) ? "Payment is split based on the score" : "Client receives a refund"}</strong><small>The payment remains processing until the on-chain transfer is confirmed.</small></div><details className="technical-details"><summary>Technical evaluation details</summary><p>AI validator consensus returned <strong>{data.result.settlement_outcome || data.result.status || "EVALUATED"}</strong>. On-chain finalization is tracked separately from this contract decision.</p></details></article>
      </section>
      <section className="panel evidence-room"><div className="panel-heading"><div><p className="card-kicker">Work and requirements</p><h2>What the evaluation checked</h2></div></div><div className="evidence-grid"><article><span>01</span><b>Job requirements</b><p>{data.meta.spec || job.spec}</p></article><article><span>02</span><b>Finished work</b><p>{job.submission_url || "Public work URL not returned."}</p></article><article><span>03</span><b>Payment rules</b><p>Full payment starts at {job.min_score ?? 70}; refunds apply below {job.partial_floor ?? 40}.</p></article></div><div className="evaluation-actions"><Link className="button primary" href={`/jobs/${encodeURIComponent(id)}/manage`}>Continue to payment <ArrowIcon/></Link>{!job.appeal_used && job.status === "EVALUATED" && <button className="button secondary" onClick={appeal} disabled={busy || !live}>{busy ? "Submitting…" : "Use one appeal"}</button>}</div>{message && <div className="action-message info" role="status">{message}</div>}</section>
    </>}
  </div>;
}
