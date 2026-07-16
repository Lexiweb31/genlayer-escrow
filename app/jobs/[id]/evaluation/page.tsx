"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowIcon, CheckIcon, ExternalIcon, RefreshIcon, SparkIcon } from "@/components/icons";
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
    <JobNavigation id={id}/><PageHeader eyebrow="AI Evaluation" title="Evidence before outcome" description="Merit does not claim an evaluation—or a validator count—until the backend returns a confirmed score and reasoning." actions={<button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh</button>}/>
    {!evaluated ? <section className="evaluation-empty panel"><span className="evaluation-orb"><SparkIcon size={32}/></span><p className="eyebrow">Awaiting confirmed result</p><h2>{job.status === "SUBMITTED" ? "Public work is ready for evaluation." : "No evaluation is available yet."}</h2><p>{job.status === "SUBMITTED" ? "The demo client can ask GenLayer to inspect the submitted URL against the immutable acceptance specification. The UI will show no score until the backend confirms one." : "Complete funding, acceptance, and public submission before starting evaluation."}</p>{job.submission_url && <a className="submission-link" href={job.submission_url} target="_blank" rel="noreferrer">Inspect submitted work <ExternalIcon/></a>}{job.status === "SUBMITTED" ? <button className="button primary large" onClick={runEvaluation} disabled={busy || !live}>{busy ? "Evaluating…" : "Evaluate with demo client"}<ArrowIcon/></button> : <Link className="button secondary" href={`/jobs/${encodeURIComponent(id)}/manage`}>Return to Manage Job</Link>}{message && <div className="action-message info" role="status">{message}</div>}</section> : <>
      <section className="evaluation-stage">
        <div className="score-panel panel"><p className="card-kicker">Backend-confirmed score</p><div className="score-orbit" style={{ "--score": `${data.result.score ?? job.score}%` } as React.CSSProperties}><strong>{data.result.score ?? job.score}<small>/100</small></strong></div><StatusPill tone={(data.result.score ?? job.score ?? 0) >= (job.min_score ?? 70) ? "success" : (data.result.score ?? job.score ?? 0) >= (job.partial_floor ?? 40) ? "warning" : "danger"}>{data.result.settlement_outcome || data.result.status || "Evaluated"}</StatusPill><small>Confirmed result returned by the Render API</small></div>
        <article className="panel reasoning-panel"><div className="panel-heading"><div><p className="card-kicker">Validator reasoning</p><h2>Agreement-based judgment</h2></div><StatusPill tone="success"><CheckIcon size={14}/> Result confirmed</StatusPill></div><blockquote>{data.result.reasoning || "The backend confirmed a score but did not return explanatory reasoning."}</blockquote><div className="evidence-checks"><span><CheckIcon/> Acceptance specification loaded</span><span><CheckIcon/> Public submission inspected</span><span><CheckIcon/> Contract threshold applied</span></div>{job.submission_url && <a className="submission-link" href={job.submission_url} target="_blank" rel="noreferrer">Open evaluated deliverable <ExternalIcon/></a>}</article>
      </section>
      <section className="panel evidence-room"><div className="panel-heading"><div><p className="card-kicker">Evidence room</p><h2>Inspectable inputs</h2></div></div><div className="evidence-grid"><article><span>01</span><b>Agreement</b><p>{data.meta.spec || job.spec}</p></article><article><span>02</span><b>Submission</b><p>{job.submission_url || "Public submission URL not returned."}</p></article><article><span>03</span><b>Threshold</b><p>Full payout at {job.min_score ?? 70}; proportional settlement from {job.partial_floor ?? 40}.</p></article></div><div className="evaluation-actions"><Link className="button primary" href={`/jobs/${encodeURIComponent(id)}/manage`}>Continue to settlement <ArrowIcon/></Link>{!job.appeal_used && job.status === "EVALUATED" && <button className="button secondary" onClick={appeal} disabled={busy || !live}>{busy ? "Submitting…" : "Use one appeal"}</button>}</div>{message && <div className="action-message info" role="status">{message}</div>}</section>
    </>}
  </div>;
}
