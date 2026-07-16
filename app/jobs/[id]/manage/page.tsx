"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowIcon, CheckIcon, ClockIcon, LockIcon, RefreshIcon, UserIcon } from "@/components/icons";
import { JobNavigation } from "@/components/job-navigation";
import { Lifecycle } from "@/components/lifecycle";
import { SettlementProof } from "@/components/settlement-proof";
import { useDemoMode, useWalletMode } from "@/components/providers";
import { ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/ui";
import { friendlyApiError, meritApi } from "@/lib/api";
import { genToWei, MIN_DEMO_AMOUNT_WEI } from "@/lib/amount";
import { useJob } from "@/lib/hooks";
import { settlementPresentation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";
import { sameAddress, writeWalletContract } from "@/lib/wallet-client";

export default function ManageJobPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { demo } = useDemoMode();
  const wallet = useWalletMode();
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
  const demoLive = Boolean(demo?.live_actions_enabled) && !job.legacy_contract;
  const walletReady = wallet.mode === "wallet" && Boolean(wallet.address) && wallet.onBradbury && !job.legacy_contract;
  const live = wallet.mode === "wallet" ? walletReady : demoLive;
  const clientAddress = job.client || job.client_address || data.meta.client_address;
  const workerAddress = job.worker || job.worker_address || data.meta.worker_address;
  const isClient = sameAddress(wallet.address, clientAddress);
  const isWorker = sameAddress(wallet.address, workerAddress);
  const clientLaneActive = ["UNFUNDED", "EVALUATED"].includes(job.status);
  const workerLaneActive = ["OPEN", "AGREED"].includes(job.status);
  const clientCanSign = wallet.mode === "wallet" ? clientLaneActive && isClient : clientLaneActive;
  const workerCanSign = wallet.mode === "wallet" ? workerLaneActive && isWorker : workerLaneActive;
  const actionOutcomeClass = view.isPending ? "outcome-pending" : view.isFinalized ? view.decision === "REFUNDED" ? "outcome-refund" : "outcome-success" : "workflow-active";

  const runAction = async (label: string, demoAction: () => Promise<unknown>, walletAction: () => Promise<unknown>, walletRoleAllowed = true) => {
    if (busy) return;
    if (!live) return setMessage({ tone: "error", text: job.legacy_contract ? "Legacy settlement contract — read only and unsafe to fund." : wallet.mode === "wallet" ? "Connect a wallet on Bradbury before submitting this action." : "Live multi-role actions are disabled. No on-chain transaction was submitted." });
    if (wallet.mode === "wallet" && !walletRoleAllowed) return setMessage({ tone: "error", text: "The connected wallet does not own the required role for this contract action." });
    setBusy(true); setMessage({ tone: "info", text: wallet.mode === "wallet" ? `${label}. Confirm the transaction in your wallet…` : `${label} with the correct Bradbury demo role…` });
    try { await (wallet.mode === "wallet" ? walletAction() : demoAction()); setMessage({ tone: "success", text: `${label} accepted by Bradbury. Refreshing shared state…` }); await refresh(); }
    catch (nextError) { setMessage({ tone: "error", text: friendlyApiError(nextError) }); }
    finally { setBusy(false); }
  };

  const fund = async (event: FormEvent) => {
    event.preventDefault();
    let amountWei: string;
    try { amountWei = genToWei(amount); } catch (nextError) { return setMessage({ tone: "error", text: nextError instanceof Error ? nextError.message : "Invalid GEN amount." }); }
    if (BigInt(amountWei) < MIN_DEMO_AMOUNT_WEI) return setMessage({ tone: "error", text: "Minimum demo deposit is 0.001 GEN." });
    await runAction("Funding escrow", () => meritApi.fund(id, amountWei), () => writeWalletContract({ account: wallet.address!, address: id, functionName: "fund", value: BigInt(amountWei) }), isClient);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^https:\/\//i.test(submissionUrl.trim())) return setMessage({ tone: "error", text: "Enter a public HTTPS deliverable URL." });
    await runAction("Submitting public work", () => meritApi.submit(id, submissionUrl.trim()), () => writeWalletContract({ account: wallet.address!, address: id, functionName: "submit_work", args: [submissionUrl.trim()] }), isWorker);
  };

  const actionPanel = () => {
    if (job.legacy_contract) return <div className="action-copy"><StatusPill tone="danger">Read only</StatusPill><h2>Legacy contract actions disabled</h2><p>Create a new escrow to use safe outbound EOA transfers.</p><Link className="button primary" href="/jobs/new">Create safe escrow <ArrowIcon/></Link></div>;
    if (job.status === "UNFUNDED") return <form onSubmit={fund}><p className="step-label">Step 1 · {wallet.mode === "wallet" ? "Connected client wallet" : "Demo client signer"}</p><h2>Fund the escrow</h2><p>{wallet.mode === "wallet" ? "Your connected client wallet sends testnet GEN directly to this escrow contract." : "The server-side Bradbury demo client deposits testnet GEN. You do not personally control these funds."}</p><label><span>Amount (GEN)</span><input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" aria-describedby="amount-help"/><small id="amount-help">Default and minimum: 0.001 GEN</small></label><button className="button primary large" disabled={busy || !live || (wallet.mode === "wallet" && !isClient)}>{busy ? "Submitting…" : wallet.mode === "wallet" ? isClient ? "Fund with connected wallet" : "Client wallet required" : "Fund with demo client"}<ArrowIcon/></button></form>;
    if (job.status === "OPEN") return <div className="action-copy"><p className="step-label">Step 2 · {wallet.mode === "wallet" ? "Connected worker wallet" : "Demo worker"}</p><h2>Accept the job requirements</h2><p>{wallet.mode === "wallet" ? "Only the worker address assigned to this contract can accept the requirements." : "The separate demo worker confirms the public requirements before starting work."}</p><button className="button primary large" disabled={busy || !live || (wallet.mode === "wallet" && !isWorker)} onClick={() => runAction("Accepting requirements", () => meritApi.acceptTerms(id), () => writeWalletContract({ account: wallet.address!, address: id, functionName: "accept_terms" }), isWorker)}>{busy ? "Submitting…" : wallet.mode === "wallet" ? isWorker ? "Accept with connected wallet" : "Worker wallet required" : "Accept with demo worker"}<ArrowIcon/></button></div>;
    if (job.status === "AGREED") return <form onSubmit={submit}><p className="step-label">Step 3 · {wallet.mode === "wallet" ? "Connected worker wallet" : "Demo worker"}</p><h2>Submit the finished work</h2><p>Provide the public URL that AI validators should compare with the job requirements.</p><label><span>Public link to the finished work</span><input type="url" value={submissionUrl} onChange={(event) => setSubmissionUrl(event.target.value)} placeholder="https://example.com/deliverable"/></label><button className="button primary large" disabled={busy || !live || (wallet.mode === "wallet" && !isWorker)}>{busy ? "Submitting…" : wallet.mode === "wallet" ? isWorker ? "Submit with connected wallet" : "Worker wallet required" : "Submit with demo worker"}<ArrowIcon/></button></form>;
    if (job.status === "SUBMITTED") return <div className="action-copy"><p className="step-label">Step 4 · Evaluation ready</p><h2>Public work submitted</h2><p>No score is claimed yet. Open AI Evaluation to submit the server-signed demo client evaluation transaction.</p><Link className="button primary large" href={`/jobs/${encodeURIComponent(id)}/evaluation`}>Open AI Evaluation <ArrowIcon/></Link></div>;
    if (job.status === "EVALUATED") return <div className="action-copy"><p className="step-label">Step 5 · {wallet.mode === "wallet" ? "Connected client wallet" : "Demo client"}</p><h2>Submit the payment transaction</h2><p>The evaluation result is ready. Payment will remain “processing” until the on-chain transfer is confirmed.</p><details className="score-help"><summary>Technical details</summary><p>The contract decision is recorded first, then an outbound transfer is queued for on-chain finalization.</p></details><button className="button primary large" disabled={busy || !live || (wallet.mode === "wallet" && !isClient)} onClick={() => runAction("Submitting payment", () => meritApi.finalize(id), () => writeWalletContract({ account: wallet.address!, address: id, functionName: "finalize" }), isClient)}>{busy ? "Submitting…" : wallet.mode === "wallet" ? isClient ? "Submit with connected wallet" : "Client wallet required" : "Submit payment with demo client"}<ArrowIcon/></button></div>;
    if (view.isPending) return <div className="action-copy"><StatusPill tone="warning"><ClockIcon size={14}/> {view.hasTransactionReference ? "Payment processing" : "Transaction unverified"}</StatusPill><h2>{view.hasTransactionReference ? "Payment transaction submitted" : view.label}</h2><p>{view.hasTransactionReference ? "Refresh safely to check whether the transfer has been confirmed. Do not submit it again while it is processing." : "The contract reports a pending settlement, but no transaction reference is available. Payment is not confirmed. Check the connected client wallet and Bradbury before attempting another action."}</p><small className="technical-status">Technical status · {view.hasTransactionReference ? "Settlement pending" : "Missing transaction reference"}</small><button className="button secondary large" disabled={loading} onClick={refresh}><RefreshIcon/> Refresh payment status</button></div>;
    return <div className="action-copy"><StatusPill tone="success"><CheckIcon size={14}/> Payment confirmed</StatusPill><h2>{view.label}</h2><p>The payment transaction is confirmed. Recipient, amount, and technical evidence are available below.</p></div>;
  };

  return <div className="page-container">
    <JobNavigation id={id}/><PageHeader eyebrow="Guided job flow" title="Manage job" description="Follow the next step from funding through work submission, evaluation, and confirmed payment."/>
    <section className="role-lanes" aria-label="Contract-separated client and worker roles"><article className={clientLaneActive ? "active" : ""}><span><UserIcon/></span><div><small>{wallet.mode === "wallet" ? "Client wallet" : "Demo client lane"}</small><b>Deploy · fund · evaluate · finalize</b><p>{clientAddress || "Client address unavailable"}</p></div>{clientLaneActive ? <StatusPill tone={clientCanSign ? "info" : "warning"}>{clientCanSign ? wallet.mode === "wallet" ? "Connected wallet" : "Current signer" : "Client wallet required"}</StatusPill> : <StatusPill>Waiting</StatusPill>}</article><div className="role-divider"><LockIcon/><span>Contract-enforced separation</span></div><article className={workerLaneActive ? "active" : ""}><span><UserIcon/></span><div><small>{wallet.mode === "wallet" ? "Worker wallet" : "Demo worker lane"}</small><b>Accept · submit public work</b><p>{workerAddress || "Worker address unavailable"}</p></div>{workerLaneActive ? <StatusPill tone={workerCanSign ? "success" : "warning"}>{workerCanSign ? wallet.mode === "wallet" ? "Connected wallet" : "Current signer" : "Worker wallet required"}</StatusPill> : <StatusPill>Waiting</StatusPill>}</article></section>
    <section className="manage-grid"><article className={`panel action-panel ${actionOutcomeClass}`}>{actionPanel()}{message && <div className={`action-message ${message.tone}`} role={message.tone === "error" ? "alert" : "status"}>{message.text}</div>}</article><article className="panel lifecycle-panel"><div className="panel-heading"><div><p className="card-kicker">Job progress</p><h2>What happens next</h2></div></div><Lifecycle job={job} result={data.result}/></article></section>
    {(view.isPending || view.isFinalized) && <SettlementProof job={job} result={data.result}/>}
  </div>;
}
