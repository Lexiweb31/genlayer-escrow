"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowIcon, CheckIcon, ClockIcon, RefreshIcon } from "@/components/icons";
import { JobNavigation } from "@/components/job-navigation";
import { Lifecycle } from "@/components/lifecycle";
import { SettlementProof } from "@/components/settlement-proof";
import { useDemoMode } from "@/components/providers";
import { ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/ui";
import { friendlyApiError, meritApi } from "@/lib/api";
import { genToWei, MIN_DEMO_AMOUNT_WEI } from "@/lib/amount";
import { useJob } from "@/lib/hooks";
import { settlementPresentation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";

export default function ManageJobPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { demo } = useDemoMode();
  const { data, error, loading, refresh } = useJob(id);
  const [amount, setAmount] = useState("0.001");
  const [submissionUrl, setSubmissionUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "error" | "success" | "info"; text: string } | null>(null);
  if (loading && !data) return <div className="page-container"><JobNavigation id={id}/><LoadingState label="Reading the live job lifecycle…"/></div>;
  if (error && !data) return <div className="page-container"><JobNavigation id={id}/><ErrorState message={error.message} retry={refresh}/></div>;
  if (!data) return null;
  const job: JobRecord = { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status };
  const view = settlementPresentation(job, data.result);
  const live = Boolean(demo?.live_actions_enabled) && !job.legacy_contract;

  const runAction = async (label: string, action: () => Promise<unknown>) => {
    if (busy) return;
    if (!live) return setMessage({ tone: "error", text: job.legacy_contract ? "Legacy settlement contract — read only and unsafe to fund." : "Live multi-role actions are disabled. No on-chain transaction was submitted." });
    setBusy(true); setMessage({ tone: "info", text: `${label} with the correct Bradbury demo role…` });
    try { await action(); setMessage({ tone: "success", text: `${label} accepted by Bradbury. Refreshing shared state…` }); await refresh(); }
    catch (nextError) { setMessage({ tone: "error", text: friendlyApiError(nextError) }); }
    finally { setBusy(false); }
  };

  const fund = async (event: FormEvent) => {
    event.preventDefault();
    let amountWei: string;
    try { amountWei = genToWei(amount); } catch (nextError) { return setMessage({ tone: "error", text: nextError instanceof Error ? nextError.message : "Invalid GEN amount." }); }
    if (BigInt(amountWei) < MIN_DEMO_AMOUNT_WEI) return setMessage({ tone: "error", text: "Minimum demo deposit is 0.001 GEN." });
    await runAction("Funding escrow", () => meritApi.fund(id, amountWei));
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^https:\/\//i.test(submissionUrl.trim())) return setMessage({ tone: "error", text: "Enter a public HTTPS deliverable URL." });
    await runAction("Submitting public work", () => meritApi.submit(id, submissionUrl.trim()));
  };

  const actionPanel = () => {
    if (job.legacy_contract) return <div className="action-copy"><StatusPill tone="danger">Read only</StatusPill><h2>Legacy contract actions disabled</h2><p>Create a new escrow to use safe outbound EOA transfers.</p><Link className="button primary" href="/jobs/new">Create safe escrow <ArrowIcon/></Link></div>;
    if (job.status === "UNFUNDED") return <form onSubmit={fund}><p className="step-label">Step 1 · Demo client signer</p><h2>Fund the escrow</h2><p>The server-side Bradbury demo client deposits testnet GEN. You do not personally control these funds.</p><label><span>Amount (GEN)</span><input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" aria-describedby="amount-help"/><small id="amount-help">Default and minimum: 0.001 GEN</small></label><button className="button primary large" disabled={busy || !live}>{busy ? "Submitting…" : "Fund with demo client"}<ArrowIcon/></button></form>;
    if (job.status === "OPEN") return <div className="action-copy"><p className="step-label">Step 2 · Demo worker signer</p><h2>Accept the immutable terms</h2><p>The separate Bradbury demo worker confirms the public acceptance specification.</p><button className="button primary large" disabled={busy || !live} onClick={() => runAction("Accepting terms", () => meritApi.acceptTerms(id))}>{busy ? "Submitting…" : "Accept with demo worker"}<ArrowIcon/></button></div>;
    if (job.status === "AGREED") return <form onSubmit={submit}><p className="step-label">Step 3 · Demo worker signer</p><h2>Submit public work</h2><p>Provide the evidence URL validators should inspect against the agreement.</p><label><span>Public HTTPS deliverable URL</span><input type="url" value={submissionUrl} onChange={(event) => setSubmissionUrl(event.target.value)} placeholder="https://example.com/deliverable"/></label><button className="button primary large" disabled={busy || !live}>{busy ? "Submitting…" : "Submit with demo worker"}<ArrowIcon/></button></form>;
    if (job.status === "SUBMITTED") return <div className="action-copy"><p className="step-label">Step 4 · Evaluation ready</p><h2>Public work submitted</h2><p>No score is claimed yet. Open AI Evaluation to submit the server-signed demo client evaluation transaction.</p><Link className="button primary large" href={`/jobs/${encodeURIComponent(id)}/evaluation`}>Open AI Evaluation <ArrowIcon/></Link></div>;
    if (job.status === "EVALUATED") return <div className="action-copy"><p className="step-label">Step 5 · Demo client signer</p><h2>Queue deterministic settlement</h2><p>The contract decision exists, but payout/refund language will remain pending until the external message finalizes.</p><button className="button primary large" disabled={busy || !live} onClick={() => runAction("Queuing settlement", () => meritApi.finalize(id))}>{busy ? "Submitting…" : "Finalize with demo client"}<ArrowIcon/></button></div>;
    if (view.isPending) return <div className="action-copy"><StatusPill tone="warning"><ClockIcon size={14}/> Settlement pending</StatusPill><h2>Outbound transfer awaiting finality</h2><p>Refreshing is retry-safe. Do not submit finalize again while the parent transaction is accepted but not finalized.</p><button className="button secondary large" disabled={loading} onClick={refresh}><RefreshIcon/> Refresh transfer evidence</button></div>;
    return <div className="action-copy"><StatusPill tone="success"><CheckIcon size={14}/> Finalized</StatusPill><h2>{view.label}</h2><p>The outbound transfer evidence is confirmed and inspectable below.</p></div>;
  };

  return <div className="page-container">
    <JobNavigation id={id}/><PageHeader eyebrow="Guided lifecycle" title="Manage job" description="Each action is role-gated, server-signed, and disabled while its Bradbury transaction is in progress."/>
    <section className="manage-grid"><article className="panel action-panel">{actionPanel()}{message && <div className={`action-message ${message.tone}`} role={message.tone === "error" ? "alert" : "status"}>{message.text}</div>}</article><article className="panel lifecycle-panel"><div className="panel-heading"><div><p className="card-kicker">Accurate sequence</p><h2>Lifecycle state</h2></div></div><Lifecycle job={job} result={data.result}/></article></section>
    {(view.isPending || view.isFinalized) && <SettlementProof job={job} result={data.result}/>}
  </div>;
}
