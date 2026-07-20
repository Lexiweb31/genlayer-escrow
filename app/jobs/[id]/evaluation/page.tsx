"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowIcon, CheckIcon, ExternalIcon, RefreshIcon } from "@/components/icons";
import { EscrowCoreMark, ValidatorQuorum } from "@/components/escrow-core";
import { JobNavigation } from "@/components/job-navigation";
import { useDemoMode, useWalletMode } from "@/components/providers";
import { ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/ui";
import { friendlyApiError, meritApi } from "@/lib/api";
import { useJob } from "@/lib/hooks";
import { hasConfirmedEvaluation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";
import { sameAddress, writeWalletContract } from "@/lib/wallet-client";

export default function EvaluationPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { demo } = useDemoMode();
  const wallet = useWalletMode();
  const { data, error, loading, refresh } = useJob(id);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  if (loading && !data) return <div className="page-container"><JobNavigation id={id}/><LoadingState label="Opening the evaluation evidence room…"/></div>;
  if (error && !data) return <div className="page-container"><JobNavigation id={id}/><ErrorState message={error.message} retry={refresh}/></div>;
  if (!data) return null;
  const job: JobRecord = { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status };
  const evaluated = hasConfirmedEvaluation(job, data.result);
  const clientAddress = job.client || job.client_address || data.meta.client_address;
  const workerAddress = job.worker || job.worker_address || data.meta.worker_address;
  const isClient = sameAddress(wallet.address, clientAddress);
  const isParty = isClient || sameAddress(wallet.address, workerAddress);
  const demoLive = Boolean(demo?.live_actions_enabled) && !job.legacy_contract;
  const walletReady = wallet.mode === "wallet" && Boolean(wallet.address) && wallet.onBradbury && !job.legacy_contract;
  const live = wallet.mode === "wallet" ? walletReady : demoLive;
  const score = data.result?.score ?? job.score ?? 0;
  const evaluationOutcomeClass = score >= (job.min_score ?? 70) ? "outcome-success" : score >= (job.partial_floor ?? 40) ? "outcome-pending" : "outcome-refund";
  const evaluationStageMessage = (stage: "preparing" | "awaiting_wallet" | "submitted" | "confirming", transactionHash?: string) => {
    const messages = {
      preparing: "Preparing the Bradbury transaction… Your wallet has not been asked to sign yet.",
      awaiting_wallet: "Your wallet has received the request. Open the wallet extension and confirm the evaluation transaction.",
      submitted: "Evaluation submitted to Bradbury. GenLayer will continue processing it even if you leave this page.",
      confirming: "Validators are evaluating the public work. You may safely leave and return later; Merit will read the confirmed result from the contract.",
    };
    if (transactionHash) localStorage.setItem(`merit-pending-evaluation:${id}`, transactionHash);
    setMessage(messages[stage]);
  };
  const runEvaluation = async () => {
    if (busy) return;
    if (!live) return setMessage(wallet.mode === "wallet" ? "Connect a wallet on Bradbury before requesting evaluation." : "Live evaluation is disabled. No on-chain result was simulated.");
    if (wallet.mode === "wallet" && !isClient) return setMessage("The connected wallet is not the client assigned to this job.");
    setBusy(true); setMessage(wallet.mode === "wallet" ? "Preparing the Bradbury transaction… Your wallet has not been asked to sign yet." : "Submitting a server-signed demo evaluation transaction to Bradbury…");
    try { await (wallet.mode === "wallet" ? writeWalletContract({ account: wallet.address!, address: id, functionName: "evaluate", onStage: evaluationStageMessage }) : meritApi.evaluate(id)); localStorage.removeItem(`merit-pending-evaluation:${id}`); setMessage("Evaluation confirmed on Bradbury. Reading the result…"); await refresh(); }
    catch (nextError) { setMessage(friendlyApiError(nextError)); }
    finally { setBusy(false); }
  };
  const appeal = async () => {
    if (busy || !live) return;
    if (wallet.mode === "wallet" && !isParty) return setMessage("Only the connected client or worker wallet can appeal this evaluation.");
    setBusy(true); setMessage(wallet.mode === "wallet" ? "Confirm the appeal transaction in your wallet…" : "Submitting one server-signed demo appeal…");
    try { await (wallet.mode === "wallet" ? writeWalletContract({ account: wallet.address!, address: id, functionName: "appeal" }) : meritApi.appeal(id)); setMessage("Appeal accepted. Refreshing the result…"); await refresh(); }
    catch (nextError) { setMessage(friendlyApiError(nextError)); }
    finally { setBusy(false); }
  };
  return <div className="page-container">
    <JobNavigation id={id}/><PageHeader eyebrow="AI Evaluation" title="Check the work against the requirements" description="Merit shows a score only after the backend confirms the evaluation and reasoning." actions={<button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh</button>}/>
    {!evaluated ? <section className="evaluation-empty panel"><span className="evaluation-orb"><EscrowCoreMark/></span><p className="eyebrow">Awaiting confirmed result</p><h2>{job.status === "SUBMITTED" ? "Public work is ready for evaluation." : "No evaluation is available yet."}</h2><p>{job.status === "SUBMITTED" ? "The client can ask GenLayer to inspect the submitted URL against the immutable job requirements. The UI will show no score until the backend confirms one." : "Complete funding, acceptance, and public submission before starting evaluation."}</p><ValidatorQuorum/>{job.submission_url && <a className="submission-link" href={job.submission_url} target="_blank" rel="noreferrer">Inspect submitted work <ExternalIcon/></a>}{job.status === "SUBMITTED" ? <button className="button primary large" onClick={runEvaluation} disabled={busy || !live || (wallet.mode === "wallet" && !isClient)}>{busy ? "Evaluating…" : wallet.mode === "wallet" ? isClient ? "Evaluate with connected wallet" : "Client wallet required" : "Evaluate with demo client"}<ArrowIcon/></button> : <Link className="button secondary" href={`/jobs/${encodeURIComponent(id)}/manage`}>Return to Manage Job</Link>}{message && <div className="action-message info" role="status">{message}</div>}</section> : <>
      <section className="evaluation-stage">
        <div className={`score-panel panel ${evaluationOutcomeClass}`}><p className="card-kicker">Backend-confirmed score</p><div className="score-orbit" style={{ "--score": `${score}%` } as React.CSSProperties}><strong>{score}<small>/100</small></strong></div><StatusPill tone={score >= (job.min_score ?? 70) ? "success" : score >= (job.partial_floor ?? 40) ? "warning" : "danger"}>{data.result.settlement_outcome || data.result.status || "Evaluated"}</StatusPill><small>Confirmed result returned by the Render API</small></div>
        <article className="panel reasoning-panel"><div className="panel-heading"><div><p className="card-kicker">Why it received this score</p><h2>Evaluation reasoning</h2></div><StatusPill tone="success"><CheckIcon size={14}/> Evaluation completed</StatusPill></div><ValidatorQuorum confirmed score={score}/><blockquote>{data.result.reasoning || "The backend confirmed a score but did not return explanatory reasoning."}</blockquote><div className="evidence-checks"><span><CheckIcon/> Job requirements loaded</span><span><CheckIcon/> Public work inspected</span><span><CheckIcon/> Payment rule applied</span><span><CheckIcon/> Evaluation result saved</span></div>{job.submission_url && <a className="submission-link" href={job.submission_url} target="_blank" rel="noreferrer">Open evaluated work <ExternalIcon/></a>}<div className={`evaluation-consequence ${evaluationOutcomeClass}`}><span>Payment result</span><strong>{score >= (job.min_score ?? 70) ? "Worker receives full payment" : score >= (job.partial_floor ?? 40) ? "Payment is split based on the score" : "Client receives a refund"}</strong><small>The payment remains processing until the on-chain transfer is confirmed.</small></div><details className="technical-details"><summary>Technical evaluation details</summary><p>AI validator consensus returned <strong>{data.result.settlement_outcome || data.result.status || "EVALUATED"}</strong>. On-chain finalization is tracked separately from this contract decision.</p></details></article>
      </section>
      <section className="panel evidence-room"><div className="panel-heading"><div><p className="card-kicker">Work and requirements</p><h2>What the evaluation checked</h2></div></div><div className="evidence-grid"><article><span>01</span><b>Job requirements</b><p>{data.meta.spec || job.spec}</p></article><article><span>02</span><b>Finished work</b><p>{job.submission_url || "Public work URL not returned."}</p></article><article><span>03</span><b>Payment rules</b><p>Full payment starts at {job.min_score ?? 70}; refunds apply below {job.partial_floor ?? 40}.</p></article></div><div className="evaluation-actions"><Link className="button primary" href={`/jobs/${encodeURIComponent(id)}/manage`}>Continue to payment <ArrowIcon/></Link>{!job.appeal_used && job.status === "EVALUATED" && <button className="button secondary" onClick={appeal} disabled={busy || !live || (wallet.mode === "wallet" && !isParty)}>{busy ? "Submitting…" : wallet.mode === "wallet" && !isParty ? "Client or worker wallet required" : "Use one appeal"}</button>}</div>{message && <div className="action-message info" role="status">{message}</div>}</section>
    </>}
  </div>;
}
