"use client";

import { FormEvent, useEffect, useState } from "react";
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
import { explorerRedirectPath } from "@/lib/explorer";
import { useJob } from "@/lib/hooks";
import { settlementPresentation } from "@/lib/settlement";
import type { JobRecord } from "@/lib/types";
import { shortAddress } from "@/lib/utils";
import { sameAddress, writeWalletContract, type WalletWriteStage } from "@/lib/wallet-client";

interface PendingWalletAction { label: string; hash: string; startingStatus: string; }

export default function ManageJobPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { demo } = useDemoMode();
  const wallet = useWalletMode();
  const { data, error, loading, refresh } = useJob(id);
  const [amount, setAmount] = useState("0.001");
  const [confirmHighValue, setConfirmHighValue] = useState(false);
  const [submissionUrl, setSubmissionUrl] = useState("");
  const settlementRecoveryKey = `merit-pending-settlement:${id}`;
  const pendingActionKey = `merit-pending-action:${id}`;
  const [recoveryTx, setRecoveryTx] = useState(() => {
    if (typeof window === "undefined") return "";
    const savedSettlement = localStorage.getItem(settlementRecoveryKey);
    if (savedSettlement) return savedSettlement;
    try {
      const pending = JSON.parse(localStorage.getItem(pendingActionKey) || "null") as PendingWalletAction | null;
      return pending?.label === "Submitting payment" ? pending.hash : "";
    } catch { return ""; }
  });
  const [pendingAction, setPendingAction] = useState<PendingWalletAction | null>(() => {
    if (typeof window === "undefined") return null;
    try { return JSON.parse(localStorage.getItem(pendingActionKey) || "null") as PendingWalletAction | null; } catch { return null; }
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "error" | "success" | "info"; text: string } | null>(null);
  const automaticRecoveryJob: JobRecord | null = data ? { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status } : null;
  const automaticRecoveryView = automaticRecoveryJob ? settlementPresentation(automaticRecoveryJob, data?.result) : null;
  useEffect(() => {
    if (!automaticRecoveryView?.isPending || automaticRecoveryView.hasTransactionReference || !/^0x[0-9a-fA-F]{64}$/.test(recoveryTx)) return;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const registerSavedSettlement = async () => {
      try {
        await meritApi.registerWalletSettlement(id, recoveryTx);
        if (cancelled) return;
        localStorage.removeItem(settlementRecoveryKey);
        setRecoveryTx("");
        setMessage({ tone: "success", text: "Merit recovered the refund transaction automatically. Refreshing confirmation evidence…" });
        await refresh();
      } catch {
        // Keep the hash locally. Bradbury may still be indexing it, and the
        // assigned client can retry without signing or sending another refund.
        if (!cancelled) retryTimer = setTimeout(registerSavedSettlement, 10_000);
      }
    };
    void registerSavedSettlement();
    return () => { cancelled = true; if (retryTimer) clearTimeout(retryTimer); };
  }, [automaticRecoveryView?.hasTransactionReference, automaticRecoveryView?.isPending, id, recoveryTx, refresh, settlementRecoveryKey]);
  if (loading && !data) return <div className="page-container"><JobNavigation id={id}/><LoadingState label="Reading the live job lifecycle…"/></div>;
  if (error && !data) return <div className="page-container"><JobNavigation id={id}/><ErrorState message={error.message} retry={refresh}/></div>;
  if (!data) return null;
  const job: JobRecord = { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status };
  const view = settlementPresentation(job, data.result);
  const settlementNetworkStatus = String(job.settlement?.parent_status || "UNKNOWN").toUpperCase();
  const settlementFailed = ["CANCELED", "UNDETERMINED", "VALIDATORS_TIMEOUT", "LEADER_TIMEOUT"].includes(settlementNetworkStatus);
  const demoLive = Boolean(demo?.live_actions_enabled) && !job.legacy_contract;
  const walletReady = wallet.mode === "wallet" && Boolean(wallet.address) && wallet.onBradbury && !job.legacy_contract;
  const live = wallet.mode === "wallet" ? walletReady : demoLive;
  const clientAddress = job.client || job.client_address || data.meta.client_address;
  const workerAddress = job.worker || job.worker_address || data.meta.worker_address;
  const isBounty = job.job_type === "BOUNTY" || data.meta.job_type === "BOUNTY";
  const isClient = sameAddress(wallet.address, clientAddress);
  const isWorker = sameAddress(wallet.address, workerAddress);
  const submissions = job.submissions || [];
  const hasSubmitted = submissions.some((entry) => sameAddress(entry.submitter, wallet.address));
  const viewerRole = wallet.mode === "demo" ? "demo" : isClient ? "client" : isWorker ? "worker" : isBounty && wallet.address ? "entrant" : "visitor";
  const clientLaneActive = ["UNFUNDED", "CLOSED", "EVALUATED"].includes(job.status) || (isBounty && job.status === "OPEN" && submissions.length > 0);
  const workerLaneActive = isBounty ? job.status === "OPEN" : ["OPEN", "AGREED"].includes(job.status);
  const clientCanSign = wallet.mode === "wallet" ? clientLaneActive && isClient : clientLaneActive;
  const workerCanSign = wallet.mode === "wallet" ? workerLaneActive && isWorker : workerLaneActive;
  const actionOutcomeClass = view.isPending ? "outcome-pending" : view.isFinalized ? view.decision === "REFUNDED" ? "outcome-refund" : "outcome-success" : "workflow-active";
  const visiblePendingAction = pendingAction?.startingStatus === job.status ? pendingAction : null;
  const highValueFunding = Number.isFinite(Number(amount)) && Number(amount) >= 1;

  const runAction = async (label: string, demoAction: () => Promise<unknown>, walletAction: (onStage: (stage: WalletWriteStage, transactionHash?: string) => void) => Promise<unknown>, walletRoleAllowed = true) => {
    if (busy || visiblePendingAction) return;
    if (!live) return setMessage({ tone: "error", text: job.legacy_contract ? "Legacy settlement contract — read only and unsafe to fund." : wallet.mode === "wallet" ? "Connect a wallet on Bradbury before submitting this action." : "Live multi-role actions are disabled. No on-chain transaction was submitted." });
    if (wallet.mode === "wallet" && !walletRoleAllowed) return setMessage({ tone: "error", text: "The connected wallet does not own the required role for this contract action." });
    let submittedHash = "";
    const onStage = (stage: WalletWriteStage, transactionHash?: string) => {
      if (transactionHash) {
        submittedHash = transactionHash;
        const pending = { label, hash: transactionHash, startingStatus: job.status };
        localStorage.setItem(pendingActionKey, JSON.stringify(pending));
        setPendingAction(pending);
      }
      const stageMessages: Record<WalletWriteStage, string> = {
        preparing: `${label}. Preparing the Bradbury transaction…`,
        awaiting_wallet: `${label}. Confirm the transaction in your wallet…`,
        submitted: `${label} submitted to Bradbury. Do not submit again.`,
        confirming: `${label} is awaiting Bradbury consensus. You may leave and return later.`,
      };
      setMessage({ tone: "info", text: stageMessages[stage] });
    };
    setBusy(true); setMessage({ tone: "info", text: wallet.mode === "wallet" ? `${label}. Preparing the Bradbury transaction…` : `${label} with the correct Bradbury demo role…` });
    try { await (wallet.mode === "wallet" ? walletAction(onStage) : demoAction()); localStorage.removeItem(pendingActionKey); setPendingAction(null); setMessage({ tone: "success", text: `${label} accepted by Bradbury. Refreshing shared state…` }); await refresh(); }
    catch (nextError) { setMessage({ tone: submittedHash ? "info" : "error", text: submittedHash ? `${label} was submitted but confirmation is still pending. Do not submit again; refresh the job status later.` : friendlyApiError(nextError) }); }
    finally { setBusy(false); }
  };

  const fund = async (event: FormEvent) => {
    event.preventDefault();
    let amountWei: string;
    try { amountWei = genToWei(amount); } catch (nextError) { return setMessage({ tone: "error", text: nextError instanceof Error ? nextError.message : "Invalid GEN amount." }); }
    if (BigInt(amountWei) < MIN_DEMO_AMOUNT_WEI) return setMessage({ tone: "error", text: "Minimum demo deposit is 0.001 GEN." });
    if (highValueFunding && !confirmHighValue) return setMessage({ tone: "error", text: `Confirm that you intend to lock ${amount} GEN before opening the wallet request.` });
    await runAction("Funding escrow", () => meritApi.fund(id, amountWei), (onStage) => writeWalletContract({ account: wallet.address!, address: id, functionName: "fund", value: BigInt(amountWei), onStage }), isClient);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^https:\/\//i.test(submissionUrl.trim())) return setMessage({ tone: "error", text: "Enter a public HTTPS deliverable URL." });
    await runAction("Submitting public work", () => meritApi.submit(id, submissionUrl.trim()), (onStage) => writeWalletContract({ account: wallet.address!, address: id, functionName: "submit_work", args: [submissionUrl.trim()], onStage }), isBounty ? !isClient : isWorker);
  };

  const finalizeWithWallet = async (onStage: (stage: WalletWriteStage, transactionHash?: string) => void) => {
    const rememberSettlement = (stage: WalletWriteStage, transactionHash?: string) => {
      if (transactionHash) {
        localStorage.setItem(settlementRecoveryKey, transactionHash);
        setRecoveryTx(transactionHash);
      }
      onStage(stage, transactionHash);
    };
    const result = await writeWalletContract({ account: wallet.address!, address: id, functionName: "finalize", onStage: rememberSettlement });
    await meritApi.registerWalletSettlement(id, result.hash);
    localStorage.removeItem(settlementRecoveryKey);
    setRecoveryTx("");
    return result;
  };

  const recoverSettlement = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^0x[0-9a-fA-F]{64}$/.test(recoveryTx.trim())) return setMessage({ tone: "error", text: "Paste the 0x transaction hash from your client wallet." });
    setBusy(true); setMessage({ tone: "info", text: "Verifying the wallet transaction on Bradbury…" });
    try { await meritApi.registerWalletSettlement(id, recoveryTx.trim()); localStorage.removeItem(settlementRecoveryKey); setRecoveryTx(""); setMessage({ tone: "success", text: "Settlement transaction recovered. Refreshing payment evidence…" }); await refresh(); }
    catch (nextError) { setMessage({ tone: "error", text: friendlyApiError(nextError) }); }
    finally { setBusy(false); }
  };

  const actionPanel = () => {
    if (job.legacy_contract) return <div className="action-copy"><StatusPill tone="danger">Read only</StatusPill><h2>Legacy contract actions disabled</h2><p>Create a new escrow to use safe outbound EOA transfers.</p><Link className="button primary" href="/jobs/new">Create safe escrow <ArrowIcon/></Link></div>;
    if (isBounty && job.status === "UNFUNDED") return <form onSubmit={fund}><p className="step-label">Bounty step 1 · Client</p><h2>Fund and open the Bounty</h2><p>Lock the reward before independent contributors begin work.</p><label><span>Reward amount (GEN)</span><input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal"/><small>Minimum 0.001 GEN · held by the Bounty contract</small></label><button className="button primary large" disabled={busy || !live || (wallet.mode === "wallet" && !isClient)}>{busy ? "Awaiting Bradbury…" : isClient || wallet.mode === "demo" ? `Open ${amount} GEN Bounty` : "Client wallet required"}<ArrowIcon/></button></form>;
    if (isBounty && job.status === "OPEN" && viewerRole === "client") return <div className="action-copy"><StatusPill tone="info">{submissions.length}/{job.max_submissions || 5} entries</StatusPill><h2>Submissions are open</h2><p>Close the round when enough work has arrived. Closing is permanent and prevents new entries.</p><div className="bounty-entry-list">{submissions.map((entry) => <a key={entry.position} href={entry.url} target="_blank" rel="noreferrer"><b>Entry {entry.position}</b><span>{shortAddress(entry.submitter)} · Inspect public work</span></a>)}</div><button className="button primary large" disabled={busy || submissions.length === 0} onClick={() => runAction("Closing Bounty submissions", () => meritApi.closeSubmissions(id), (onStage) => writeWalletContract({ account: wallet.address!, address: id, functionName: "close_submissions", onStage }), isClient)}>Close submissions <ArrowIcon/></button></div>;
    if (isBounty && job.status === "OPEN" && hasSubmitted) return <div className="action-copy"><StatusPill tone="success"><CheckIcon/> Entry recorded</StatusPill><h2>Your Bounty entry is on-chain</h2><p>One entry is allowed per wallet. The client will close the round before GenLayer evaluates every candidate.</p><a className="button secondary large" href={submissions.find((entry) => sameAddress(entry.submitter, wallet.address))?.url} target="_blank" rel="noreferrer">Inspect your entry <ArrowIcon/></a></div>;
    if (isBounty && job.status === "OPEN") return <form onSubmit={submit}><p className="step-label">Open Bounty · one entry per wallet</p><h2>Submit your finished work</h2><p>Your public HTTPS deliverable will be evaluated against the same requirements as every other entry.</p><label><span>Public link to finished work</span><input type="url" value={submissionUrl} onChange={(event) => setSubmissionUrl(event.target.value)} placeholder="https://example.com/deliverable"/></label><button className="button primary large" disabled={busy || !live || (wallet.mode === "wallet" && isClient)}>{busy ? "Awaiting Bradbury…" : wallet.mode === "wallet" ? wallet.address && !isClient ? "Enter Bounty with connected wallet" : "Contributor wallet required" : "Submit with demo contributor"}<ArrowIcon/></button>{wallet.mode === "demo" && submissions.length > 0 && <button type="button" className="button secondary large" onClick={() => runAction("Closing Bounty submissions", () => meritApi.closeSubmissions(id), async () => ({}), true)}>Close round with demo client</button>}</form>;
    if (isBounty && job.status === "CLOSED") return <div className="action-copy"><StatusPill tone="warning">Entries closed</StatusPill><h2>Evaluate every Bounty entry</h2><p>GenLayer validators will inspect {submissions.length} public submission{submissions.length === 1 ? "" : "s"}. The highest qualifying score wins; exact ties favor the earlier on-chain entry.</p><button className="button primary large" disabled={busy || !live || (wallet.mode === "wallet" && !isClient)} onClick={() => runAction("Evaluating Bounty entries", () => meritApi.evaluate(id), (onStage) => writeWalletContract({ account: wallet.address!, address: id, functionName: "evaluate", onStage }), isClient)}>Evaluate all entries <ArrowIcon/></button></div>;
    if (isBounty && (viewerRole === "entrant" || viewerRole === "worker") && job.status === "EVALUATED") return <div className="action-copy"><StatusPill tone={isWorker ? "success" : "info"}>{isWorker ? "Winning entry" : "Evaluation completed"}</StatusPill><h2>{isWorker ? "Your entry won the Bounty" : "Another entry ranked highest"}</h2><p>{isWorker ? `Your score is ${data.result.score ?? 0}/100. The client must finalize the winner payout.` : "The winning result is recorded on-chain and settlement is awaiting the client."}</p></div>;
    if (viewerRole === "visitor") return <div className="action-copy"><StatusPill>Public observer</StatusPill><h2>Public job status</h2><p>You can inspect the agreement, submitted work, evaluation, and verified settlement evidence. Connect the assigned client or worker wallet to perform an action.</p><Link className="button secondary large" href={`/jobs/${encodeURIComponent(id)}`}>View public overview <ArrowIcon/></Link></div>;
    if (viewerRole === "client" && ["OPEN", "AGREED"].includes(job.status)) return <div className="action-copy"><StatusPill tone="info">Client workspace</StatusPill><h2>{job.status === "OPEN" ? "Waiting for the worker to accept" : "Work is in progress"}</h2><p>{job.status === "OPEN" ? "The payment is protected. The assigned worker must accept the requirements with their wallet." : "The worker accepted the requirements. You will be notified when public work is submitted."}</p><small className="technical-status">No client action is required right now.</small></div>;
    if (viewerRole === "worker" && job.status === "UNFUNDED") return <div className="action-copy"><StatusPill tone="warning">Worker workspace</StatusPill><h2>Waiting for protected payment</h2><p>The client must fund the escrow before you can accept the requirements. Do not begin work until funding is confirmed.</p></div>;
    if (viewerRole === "worker" && job.status === "SUBMITTED") return <div className="action-copy"><StatusPill tone="info">Submission recorded</StatusPill><h2>Your work is awaiting evaluation</h2><p>Your public deliverable is recorded. The client must request GenLayer evaluation; no worker action is required.</p><Link className="button secondary large" href={job.submission_url || `/jobs/${encodeURIComponent(id)}`} target={job.submission_url ? "_blank" : undefined} rel={job.submission_url ? "noreferrer" : undefined}>Inspect submitted work <ArrowIcon/></Link></div>;
    if (viewerRole === "worker" && job.status === "EVALUATED") return <div className="action-copy"><StatusPill tone="success">Evaluation completed</StatusPill><h2>Your result is ready</h2><p>The client must now submit the settlement transaction. You cannot finalize payment from the worker wallet.</p><Link className="button secondary large" href={`/jobs/${encodeURIComponent(id)}/evaluation`}>Review your evaluation <ArrowIcon/></Link></div>;
    if (viewerRole === "worker" && view.isPending) return <div className="action-copy"><StatusPill tone={settlementFailed ? "danger" : "warning"}>{!settlementFailed && <ClockIcon size={14}/>} {settlementFailed ? "Settlement failed" : "Worker payout pending"}</StatusPill><h2>{settlementFailed ? "The payment transaction did not finalize" : "Your payment is awaiting Bradbury finality"}</h2><p>{settlementFailed ? "No worker payout is confirmed. The client must inspect the failed settlement transaction." : "No action is required from you. Merit automatically checks Bradbury every 12 seconds and will show your confirmed payout only after transfer evidence finalizes."}</p><small className="technical-status">Bradbury transaction · {settlementNetworkStatus}</small><button className="button secondary large" disabled={loading} onClick={refresh}><RefreshIcon/> Check payout status</button></div>;
    if (job.status === "UNFUNDED") return <form onSubmit={fund}><p className="step-label">Step 1 · {wallet.mode === "wallet" ? "Connected client wallet" : "Demo client signer"}</p><h2>Fund the escrow</h2><p>{wallet.mode === "wallet" ? "Your connected client wallet sends testnet GEN directly to this escrow contract." : "The server-side Bradbury demo client deposits testnet GEN. You do not personally control these funds."}</p><div className="funding-review"><div><span>Available balance</span><strong>{wallet.mode === "wallet" ? wallet.balance || "Checking…" : "Demo funds"}</strong></div><div><span>Escrow contract</span><strong title={id}>{shortAddress(id, 8, 6)}</strong></div><div><span>Assigned worker</span><strong title={workerAddress}>{shortAddress(workerAddress, 8, 6)}</strong></div></div><label><span>Amount to lock (GEN)</span><input value={amount} onChange={(event) => { setAmount(event.target.value); setConfirmHighValue(false); }} inputMode="decimal" aria-describedby="amount-help"/><small id="amount-help">Minimum: 0.001 GEN · returned or paid only through the escrow rules</small></label>{highValueFunding && <label className="high-value-confirm"><input type="checkbox" checked={confirmHighValue} onChange={(event) => setConfirmHighValue(event.target.checked)}/><span>I understand that this will lock <b>{amount} GEN</b> in the escrow contract.</span></label>}<button className="button primary large" disabled={busy || Boolean(visiblePendingAction) || !live || (wallet.mode === "wallet" && !isClient)}>{busy || visiblePendingAction ? "Awaiting Bradbury…" : wallet.mode === "wallet" ? isClient ? `Lock ${amount || "0"} GEN` : "Client wallet required" : "Fund with demo client"}<ArrowIcon/></button></form>;
    if (job.status === "OPEN") return <div className="action-copy"><p className="step-label">Step 2 · {wallet.mode === "wallet" ? "Connected worker wallet" : "Demo worker"}</p><h2>Accept the job requirements</h2><p>{wallet.mode === "wallet" ? "Only the worker address assigned to this contract can accept the requirements." : "The separate demo worker confirms the public requirements before starting work."}</p><button className="button primary large" disabled={busy || Boolean(visiblePendingAction) || !live || (wallet.mode === "wallet" && !isWorker)} onClick={() => runAction("Accepting requirements", () => meritApi.acceptTerms(id), (onStage) => writeWalletContract({ account: wallet.address!, address: id, functionName: "accept_terms", onStage }), isWorker)}>{busy || visiblePendingAction ? "Awaiting Bradbury…" : wallet.mode === "wallet" ? isWorker ? "Accept with connected wallet" : "Worker wallet required" : "Accept with demo worker"}<ArrowIcon/></button></div>;
    if (job.status === "AGREED") return <form onSubmit={submit}><p className="step-label">Step 3 · {wallet.mode === "wallet" ? "Connected worker wallet" : "Demo worker"}</p><h2>Submit the finished work</h2><p>Provide the public URL that AI validators should compare with the job requirements.</p><label><span>Public link to the finished work</span><input type="url" value={submissionUrl} onChange={(event) => setSubmissionUrl(event.target.value)} placeholder="https://example.com/deliverable"/></label><button className="button primary large" disabled={busy || Boolean(visiblePendingAction) || !live || (wallet.mode === "wallet" && !isWorker)}>{busy || visiblePendingAction ? "Awaiting Bradbury…" : wallet.mode === "wallet" ? isWorker ? "Submit with connected wallet" : "Worker wallet required" : "Submit with demo worker"}<ArrowIcon/></button></form>;
    if (job.status === "SUBMITTED") return <div className="action-copy"><p className="step-label">Step 4 · Evaluation ready</p><h2>Public work submitted</h2><p>No score is claimed yet. Open AI Evaluation to submit the evaluation transaction with the required client signer.</p><Link className="button primary large" href={`/jobs/${encodeURIComponent(id)}/evaluation`}>Open AI Evaluation <ArrowIcon/></Link></div>;
    if (job.status === "EVALUATED") return <div className="action-copy"><p className="step-label">Step 5 · {wallet.mode === "wallet" ? "Connected client wallet" : "Demo client"}</p><h2>Submit the payment transaction</h2><p>The evaluation result is ready. Payment will remain “processing” until the on-chain transfer is confirmed.</p><details className="score-help"><summary>Technical details</summary><p>The contract decision is recorded first, then an outbound transfer is queued for on-chain finalization.</p></details><button className="button primary large" disabled={busy || Boolean(visiblePendingAction) || !live || (wallet.mode === "wallet" && !isClient)} onClick={() => runAction("Submitting payment", () => meritApi.finalize(id), finalizeWithWallet, isClient)}>{busy || visiblePendingAction ? "Awaiting Bradbury…" : wallet.mode === "wallet" ? isClient ? "Submit with connected wallet" : "Client wallet required" : "Submit payment with demo client"}<ArrowIcon/></button></div>;
    if (view.isPending) return <div className="action-copy"><StatusPill tone={settlementFailed ? "danger" : "warning"}>{!settlementFailed && <ClockIcon size={14}/>} {view.hasTransactionReference ? settlementNetworkStatus === "ACCEPTED" ? "Accepted · not finalized" : settlementFailed ? "Transaction failed" : "Awaiting finality" : "Transaction unverified"}</StatusPill><h2>{view.label}</h2><p>{view.hasTransactionReference ? settlementNetworkStatus === "ACCEPTED" ? "Bradbury accepted the settlement transaction, but has not finalized it. The split payment cannot be claimed as sent until finality and transfer evidence are available." : settlementFailed ? "Bradbury did not finalize this settlement transaction. No payment confirmation will be shown for a failed transaction." : "The transaction is saved and Merit automatically checks Bradbury every 12 seconds. You may safely leave and return later." : "The contract reports a pending settlement, but no transaction reference is available. Recover it using the transaction hash from the client wallet."}</p><small className="technical-status">Technical status · {view.hasTransactionReference ? `Bradbury ${settlementNetworkStatus}` : "Missing transaction reference"}</small>{!view.hasTransactionReference && wallet.mode === "wallet" && isClient && <form onSubmit={recoverSettlement}><label><span>Settlement transaction hash</span><input value={recoveryTx} onChange={(event) => setRecoveryTx(event.target.value)} placeholder="0x…" autoComplete="off" spellCheck={false}/></label><button className="button primary large" disabled={busy}>Verify and recover payment</button></form>}<button className="button secondary large" disabled={loading} onClick={refresh}><RefreshIcon/> Check Bradbury now</button></div>;
    return <div className="action-copy"><StatusPill tone="success"><CheckIcon size={14}/> Payment confirmed</StatusPill><h2>{view.label}</h2><p>The payment transaction is confirmed. Recipient, amount, and technical evidence are available below.</p></div>;
  };

  return <div className="page-container manage-page">
    <JobNavigation id={id}/><PageHeader eyebrow={viewerRole === "client" ? "Client workspace" : viewerRole === "worker" ? "Worker workspace" : viewerRole === "visitor" ? "Public job viewer" : "Manage protected job"} title={data.meta.title || "Protected job"} description={viewerRole === "worker" ? "Accept assigned requirements, submit public work, and track only your evaluation and payout." : viewerRole === "client" ? "Fund the agreement, request evaluation, and finalize settlement from the assigned client wallet." : viewerRole === "visitor" ? "Inspect public agreement and settlement facts. Private role actions require the assigned wallet." : "Complete only the action assigned to the correct demo signer."} actions={<StatusPill tone={visiblePendingAction || view.isPending ? "warning" : view.isFinalized ? "success" : "info"}>{visiblePendingAction ? "Transaction processing" : view.label}</StatusPill>}/>
    {isBounty ? <section className="role-lanes bounty-lanes" aria-label="Bounty client and contributor roles"><article className={viewerRole === "client" || clientLaneActive ? "active" : ""}><span><UserIcon/></span><div><small>Bounty client</small><b>Fund · close · evaluate · finalize</b><p title={clientAddress}>{clientAddress}</p></div>{viewerRole === "client" ? <StatusPill tone="info">You</StatusPill> : <StatusPill>Client</StatusPill>}</article><div className="role-divider"><LockIcon/><span>Open, contract-enforced competition</span></div><article className={viewerRole === "entrant" || viewerRole === "worker" || workerLaneActive ? "active" : ""}><span><UserIcon/></span><div><small>Independent contributors</small><b>Submit one public entry per wallet</b><p>{submissions.length}/{job.max_submissions || 5} entries recorded</p></div>{isWorker ? <StatusPill tone="success">Winner</StatusPill> : hasSubmitted ? <StatusPill tone="success">Entered</StatusPill> : <StatusPill>Open pool</StatusPill>}</article></section> : <section className="role-lanes" aria-label="Contract-separated client and worker roles"><article className={viewerRole === "client" || clientLaneActive ? "active" : ""}><span><UserIcon/></span><div><small>{wallet.mode === "wallet" ? "Client wallet" : "Demo client lane"}</small><b>Deploy · fund · evaluate · finalize</b><p title={clientAddress}>{clientAddress || "Client address unavailable"}</p></div>{viewerRole === "client" ? <StatusPill tone="info">You</StatusPill> : clientLaneActive ? <StatusPill tone={clientCanSign ? "info" : "warning"}>{clientCanSign ? "Active" : "Client action"}</StatusPill> : <StatusPill>Client</StatusPill>}</article><div className="role-divider"><LockIcon/><span>Contract-enforced separation</span></div><article className={viewerRole === "worker" || workerLaneActive ? "active" : ""}><span><UserIcon/></span><div><small>{wallet.mode === "wallet" ? "Worker wallet" : "Demo worker lane"}</small><b>Accept · submit public work</b><p title={workerAddress}>{workerAddress || "Worker address unavailable"}</p></div>{viewerRole === "worker" ? <StatusPill tone="success">You</StatusPill> : workerLaneActive ? <StatusPill tone={workerCanSign ? "success" : "warning"}>{workerCanSign ? "Active" : "Worker action"}</StatusPill> : <StatusPill>Worker</StatusPill>}</article></section>}
    {visiblePendingAction && <div className="inline-alert info" role="status"><div><b>{visiblePendingAction.label} already submitted</b><span>Bradbury is processing this transaction. Do not submit it again.</span></div><div><a className="button secondary" href={explorerRedirectPath("tx", visiblePendingAction.hash) || "#"} target="_blank" rel="noreferrer">View transaction</a><button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh job</button></div></div>}
    <section className="manage-grid"><article className={`panel action-panel ${actionOutcomeClass}`}>{actionPanel()}{message && <div className={`action-message ${message.tone}`} role={message.tone === "error" ? "alert" : "status"}>{message.text}</div>}</article><article className="panel lifecycle-panel"><div className="panel-heading"><div><p className="card-kicker">Verified progress</p><h2>Escrow lifecycle</h2></div></div><Lifecycle job={job} result={data.result} transactionPending={Boolean(visiblePendingAction)}/></article></section>
    {(view.isPending || view.isFinalized) && <SettlementProof job={job} result={data.result}/>}
  </div>;
}
