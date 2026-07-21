"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowIcon, CheckIcon, ShieldIcon } from "@/components/icons";
import { useDemoMode, useWalletMode } from "@/components/providers";
import { PageHeader, StatusPill } from "@/components/ui";
import { friendlyApiError, meritApi } from "@/lib/api";
import { deployWalletBounty, deployWalletEscrow, sameAddress } from "@/lib/wallet-client";
import type { RegisterWalletJobInput } from "@/lib/types";

const templates = [
  { title: "Responsive product landing page", spec: "Build a responsive product landing page with a clear hero, at least three measurable benefit sections, accessible mobile navigation, a working primary call-to-action, a security section, and a complete footer. Publish it at a public HTTPS URL." },
  { title: "Evidence-backed UX audit", spec: "Audit the public onboarding flow and deliver a written report with at least ten annotated findings, severity labels, reproducible steps, and prioritized recommendations. Publish the complete report at a public HTTPS URL." },
  { title: "Protocol research brief", spec: "Compare five decentralized arbitration protocols using linked primary sources, a consistent evaluation framework, a decision matrix, and a concise recommendation. Publish the brief at a public HTTPS URL." },
];

export default function PostJobPage() {
  const router = useRouter();
  const { demo } = useDemoMode();
  const wallet = useWalletMode();
  const [title, setTitle] = useState("");
  const [spec, setSpec] = useState("");
  const [fee, setFee] = useState("2");
  const [minScore, setMinScore] = useState("70");
  const [partialFloor, setPartialFloor] = useState("40");
  const [jobType, setJobType] = useState<"DIRECT_HIRE" | "BOUNTY">("DIRECT_HIRE");
  const [maxSubmissions, setMaxSubmissions] = useState("5");
  const [workerAddress, setWorkerAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [step, setStep] = useState(1);
  const [pendingRegistration, setPendingRegistration] = useState<RegisterWalletJobInput | null>(null);
  const demoLive = Boolean(demo?.live_actions_enabled) && wallet.mode === "demo";
  const walletLive = wallet.mode === "wallet" && Boolean(wallet.address) && wallet.onBradbury;
  const live = demoLive || walletLive;
  const specQuality = useMemo(() => {
    const words = spec.trim().split(/\s+/).filter(Boolean).length;
    const testable = /\b(at least|exactly|must|include|working|responsive|public|https|\d+)\b/i.test(spec);
    const bounded = /[.;,]/.test(spec) && words >= 20;
    return Math.min(100, Math.round(words * 1.4) + (testable ? 30 : 0) + (bounded ? 20 : 0));
  }, [spec]);
  const paymentBands = useMemo(() => {
    const full = Math.min(100, Math.max(0, Number(minScore) || 0));
    const refund = Math.min(full, Math.max(0, Number(partialFloor) || 0));
    return { full, refund, refundEnd: Math.max(0, refund - 1), splitEnd: Math.max(refund, full - 1) };
  }, [minScore, partialFloor]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = localStorage.getItem("merit-pending-wallet-job");
        if (saved) setPendingRegistration(JSON.parse(saved) as RegisterWalletJobInput);
      } catch {
        localStorage.removeItem("merit-pending-wallet-job");
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const resumeRegistration = async () => {
    if (!pendingRegistration || busy) return;
    setBusy(true); setError(""); setStatus("Verifying the confirmed deployment and restoring it to the marketplace…");
    try {
      const response = await meritApi.registerWalletJob(pendingRegistration);
      localStorage.removeItem("merit-pending-wallet-job");
      setPendingRegistration(null);
      router.push(`/jobs/${encodeURIComponent(response.job.address)}`);
    } catch (nextError) {
      setError(friendlyApiError(nextError)); setStatus("");
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const feeNumber = Number(fee);
    const minNumber = Number(minScore);
    const floorNumber = Number(partialFloor);
    if (spec.trim().length < 20) return setError("Describe a specific, testable deliverable in at least 20 characters.");
    if (!Number.isFinite(feeNumber) || feeNumber < 0 || feeNumber > 10) return setError("The Merit fee must be between 0% and 10%.");
    if (!Number.isInteger(minNumber) || minNumber < 0 || minNumber > 100) return setError("Full payment must start at a whole-number score from 0 to 100.");
    if (jobType === "DIRECT_HIRE" && (!Number.isInteger(floorNumber) || floorNumber < 0 || floorNumber > minNumber)) return setError("Refund below must be a whole-number score from 0 up to the full-payment score.");
    if (jobType === "DIRECT_HIRE" && wallet.mode === "wallet" && !/^0x[0-9a-fA-F]{40}$/.test(workerAddress.trim())) return setError("Enter the worker’s valid Bradbury wallet address.");
    if (jobType === "DIRECT_HIRE" && wallet.mode === "wallet" && sameAddress(wallet.address, workerAddress.trim())) return setError("The client and worker must use different wallet addresses.");
    if (wallet.mode === "wallet" && !demo?.platform_address) return setError("The public Merit fee recipient is not configured. Deployment was not started.");
    if (!live) return setError(wallet.mode === "wallet"
      ? !wallet.address
        ? "Connect a wallet before deploying. No transaction was submitted."
        : !wallet.onBradbury
          ? "Switch the connected wallet to Bradbury before deploying. No transaction was submitted."
          : "Wallet deployment is temporarily unavailable. No transaction was submitted."
      : "Live deployment is disabled until Render has two different Bradbury demo signers. No transaction was submitted.");
    setBusy(true);
    setStatus(wallet.mode === "wallet" ? "Confirm deployment in your wallet. Bradbury consensus can take up to 90 seconds…" : "Deploying the intelligent escrow with the Bradbury demo client. This can take up to 90 seconds…");
    try {
      const common = { title: title.trim() || null, spec: spec.trim(), fee_bps: Math.round(feeNumber * 100), min_score: minNumber, partial_floor: jobType === "BOUNTY" ? minNumber : floorNumber, job_type: jobType, max_submissions: Number(maxSubmissions) };
      let response;
      if (wallet.mode === "wallet") {
        const sourceResponse = await fetch(`/api/contract-source${jobType === "BOUNTY" ? "?type=bounty" : ""}`, { cache: "no-store" });
        if (!sourceResponse.ok) throw new Error("The verified escrow contract source could not be loaded.");
        const code = await sourceResponse.text();
        const deployment = jobType === "BOUNTY"
          ? await deployWalletBounty({ account: wallet.address!, code, spec: common.spec, platform: demo!.platform_address!, feeBps: common.fee_bps, minScore: common.min_score, maxSubmissions: common.max_submissions })
          : await deployWalletEscrow({ account: wallet.address!, code, spec: common.spec, worker: workerAddress.trim(), platform: demo!.platform_address!, feeBps: common.fee_bps, minScore: common.min_score, partialFloor: common.partial_floor });
        const pending = { ...common, address: deployment.address, client_address: wallet.address!, worker_address: jobType === "DIRECT_HIRE" ? workerAddress.trim() : null, deployment_tx: deployment.hash };
        localStorage.setItem("merit-pending-wallet-job", JSON.stringify(pending));
        setPendingRegistration(pending);
        setStatus("Deployment accepted. Verifying and adding it to the shared marketplace…");
        response = await meritApi.registerWalletJob(pending);
        localStorage.removeItem("merit-pending-wallet-job");
        setPendingRegistration(null);
      } else {
        response = await meritApi.createJob(common);
      }
      router.push(`/jobs/${encodeURIComponent(response.job.address)}`);
    } catch (nextError) {
      setError(friendlyApiError(nextError));
      setStatus("");
    } finally {
      setBusy(false);
    }
  };

  const continueBuilder = () => {
    setError("");
    if (step === 1 && spec.trim().length < 20) return setError("Describe a specific, testable deliverable in at least 20 characters before continuing.");
    if (step === 1 && jobType === "DIRECT_HIRE" && wallet.mode === "wallet" && !/^0x[0-9a-fA-F]{40}$/.test(workerAddress.trim())) return setError("Enter the worker’s valid Bradbury wallet address before continuing.");
    if (step === 1 && jobType === "DIRECT_HIRE" && wallet.mode === "wallet" && sameAddress(wallet.address, workerAddress.trim())) return setError("The client and worker must use different wallet addresses.");
    if (step === 2) {
      const feeNumber = Number(fee); const minNumber = Number(minScore); const floorNumber = Number(partialFloor);
      if (!Number.isFinite(feeNumber) || feeNumber < 0 || feeNumber > 10) return setError("The Merit fee must be between 0% and 10%.");
      if (!Number.isInteger(minNumber) || minNumber < 0 || minNumber > 100) return setError("Full payment must start at a whole-number score from 0 to 100.");
      if (jobType === "DIRECT_HIRE" && (!Number.isInteger(floorNumber) || floorNumber < 0 || floorNumber > minNumber)) return setError("Refund below must be a whole-number score from 0 up to the full-payment score.");
    }
    setStep((current) => Math.min(3, current + 1));
  };

  return <div className="page-container wide-form-page">
    <PageHeader eyebrow="Guided job creation" title="Create a protected job" description="Describe the work, decide how payment should be handled, and review everything before publishing."/>
    {pendingRegistration && <div className="inline-alert warning" role="status"><div><b>Confirmed deployment awaiting registration</b><span>Your wallet transaction succeeded. Restore this escrow to the shared marketplace without deploying again.</span></div><button type="button" className="button secondary" onClick={() => void resumeRegistration()} disabled={busy}>Restore deployed job</button></div>}
    <nav className="builder-progress" aria-label="Protected job builder progress">{["Job requirements", "Payment rules", "Review and publish"].map((label, index) => <button type="button" key={label} aria-label={`Step ${index + 1}: ${label}`} aria-current={step === index + 1 ? "step" : undefined} className={step === index + 1 ? "active" : step > index + 1 ? "complete" : ""} onClick={() => { if (index + 1 < step) setStep(index + 1); }} disabled={index + 1 > step}><span>{step > index + 1 ? <CheckIcon size={14}/> : index + 1}</span><b>{label}</b></button>)}</nav>
    <div className="post-layout">
      <form className="panel post-form workflow-active" onSubmit={submit}>
        {step === 1 && <div className="form-section builder-stage"><div className="form-section-head"><span>01</span><div><h2>What work do you need?</h2><p>Write clear requirements that the completed work can be checked against.</p></div></div><fieldset className="job-type-picker"><legend>Choose how workers participate</legend><button type="button" className={jobType === "DIRECT_HIRE" ? "active" : ""} onClick={() => setJobType("DIRECT_HIRE")}><b>Direct Hire</b><span>Assign one worker before publishing.</span></button><button type="button" className={jobType === "BOUNTY" ? "active" : ""} onClick={() => setJobType("BOUNTY")}><b>Bounty mode</b><span>Open the job to multiple independent submissions; AI selects the strongest qualifying entry.</span></button></fieldset><label><span>Job title</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Responsive product landing page" maxLength={80}/></label>{jobType === "DIRECT_HIRE" && wallet.mode === "wallet" && <label><span>Worker wallet address</span><input value={workerAddress} onChange={(event) => setWorkerAddress(event.target.value)} placeholder="0x…" autoComplete="off" spellCheck={false}/><small>The assigned worker will use this separate Bradbury wallet to accept and submit the work.</small></label>}{jobType === "BOUNTY" && <label><span>Maximum submissions</span><select value={maxSubmissions} onChange={(event) => setMaxSubmissions(event.target.value)}><option value="2">2 submissions</option><option value="3">3 submissions</option><option value="4">4 submissions</option><option value="5">5 submissions</option></select><small>One entry per wallet. The client closes the round before evaluation.</small></label>}<label><span>What must the finished work include?</span><textarea value={spec} onChange={(event) => setSpec(event.target.value)} placeholder="List the required sections, features, formats, working links, and anything else the completed work must contain." rows={9}/><small>{spec.length} characters · Requirement quality {specQuality}/100</small></label><div className="spec-meter" aria-label={`Requirement quality ${specQuality} out of 100`}><i style={{ width: `${specQuality}%` }}/></div><div className="template-row" aria-label="Job requirement templates">{templates.map((template) => <button type="button" key={template.title} onClick={() => { setTitle(template.title); setSpec(template.spec); }}>{template.title}</button>)}</div></div>}
        {step === 2 && <div className="form-section builder-stage"><div className="form-section-head"><span>02</span><div><h2>Decide how payment works</h2><p>{jobType === "BOUNTY" ? "Set the minimum score a winning entry must reach." : "Choose the score ranges that control refunds, split payments, and full payment."}</p></div></div><div className="field-grid"><label><span>Merit fee (%)</span><small>The percentage deducted when payment goes to the winner.</small><input type="number" inputMode="decimal" min="0" max="10" step="0.1" value={fee} onChange={(event) => setFee(event.target.value)}/></label><label><span>{jobType === "BOUNTY" ? "Qualifying score" : "Full payment starts at"}</span><small>{jobType === "BOUNTY" ? "The strongest entry must reach this score to win the bounty." : "The minimum evaluation score required for the worker to receive full payment."}</small><input type="number" inputMode="numeric" min="0" max="100" value={minScore} onChange={(event) => setMinScore(event.target.value)}/></label>{jobType === "DIRECT_HIRE" && <label><span>Refund below</span><small>Scores below this number return the payment to the client.</small><input type="number" inputMode="numeric" min="0" max="100" value={partialFloor} onChange={(event) => setPartialFloor(event.target.value)}/></label>}</div><div className="payment-preview" aria-live="polite"><p className="card-kicker">Live payment preview</p>{jobType === "BOUNTY" ? <div className="threshold-preview"><span><i className="refund"/><b>Best score below {minScore}:</b> Client receives a refund</span><span><i className="pay"/><b>Best score {minScore}–100:</b> Highest-scoring entrant wins</span></div> : <div className="threshold-preview">{paymentBands.refund > 0 && <span><i className="refund"/><b>Score 0–{paymentBands.refundEnd}:</b> Client receives a refund</span>}{paymentBands.full > paymentBands.refund && <span><i className="split"/><b>Score {paymentBands.refund}–{paymentBands.splitEnd}:</b> Payment is split based on the score</span>}<span><i className="pay"/><b>Score {paymentBands.full}–100:</b> Worker receives full payment</span></div>}<strong>{fee || "0"}% is deducted from the worker’s payment</strong></div><details className="score-help"><summary>Learn how scoring works</summary><p>{jobType === "BOUNTY" ? "GenLayer validators inspect every submitted public URL against the same requirements. The highest qualifying score wins; an exact tie goes to the earlier on-chain submission." : "AI validators compare the submitted work with your requirements. Their consensus produces an evaluation score and the thresholds control settlement."}</p></details><div className="funding-handoff"><b>Funding follows publishing</b><p>After the job is created, Manage Job accepts a precision-safe GEN amount. The default and minimum are 0.001 GEN.</p></div></div>}
        {step === 3 && <div className="form-section builder-stage review-stage"><div className="form-section-head"><span>03</span><div><h2>Review and publish</h2><p>Check the requirements, roles, and payment rules before deploying the job.</p></div></div><div className="review-grid"><div><span>Job type</span><strong>{jobType === "BOUNTY" ? "Bounty mode" : "Direct Hire"}</strong></div><div><span>Job title</span><strong>{title.trim() || "Untitled protected job"}</strong></div>{jobType === "DIRECT_HIRE" && wallet.mode === "wallet" && <div><span>Assigned worker</span><strong>{workerAddress || "Not provided"}</strong></div>}{jobType === "BOUNTY" && <div><span>Entry limit</span><strong>{maxSubmissions} wallets · one entry each</strong></div>}<div className="review-spec"><span>Job requirements</span><p>{spec}</p></div><div><span>{jobType === "BOUNTY" ? "Winner must score" : "Full payment starts at"}</span><strong>{minScore}/100</strong></div>{jobType === "DIRECT_HIRE" && <><div><span>Payment is split</span><strong>{partialFloor}–{paymentBands.splitEnd}/100</strong></div><div><span>Refund below</span><strong>{partialFloor}/100</strong></div></>}<div><span>Merit fee</span><strong>{fee}%</strong></div></div><div className="inline-alert info"><b>{jobType === "BOUNTY" ? "Bounty mode" : wallet.mode === "wallet" ? "Wallet mode" : "Demo mode"}</b><span>{jobType === "BOUNTY" ? "Multiple wallets can submit. The client closes entries, GenLayer scores every candidate, and the strongest qualifying entry receives settlement." : wallet.mode === "wallet" ? "Your connected client wallet deploys and owns this escrow. The assigned worker uses a different wallet." : "Two test accounts show the client and worker flow. No personal wallet or visitor funds are used."}</span></div></div>}
        {error && <div className="form-error" role="alert">{error}</div>}{status && <div className="form-status" aria-live="polite"><span className="loader"/>{status}</div>}
        <div className="form-submit"><div>{step > 1 && <button type="button" className="button secondary" onClick={() => setStep((current) => current - 1)} disabled={busy}>Back</button>}<StatusPill tone={live ? "success" : "warning"}>{live ? wallet.mode === "wallet" ? "Wallet ready" : "Separate demo roles ready" : "Live actions disabled"}</StatusPill><small>{wallet.mode === "wallet" ? "Connected wallet · Bradbury transaction" : "Server-signed Bradbury testnet transaction"}</small></div>{step < 3 ? <button type="button" className="button primary large" onClick={continueBuilder}>Continue <ArrowIcon/></button> : <button className="button primary large" disabled={busy || !live}>{busy ? "Deploying…" : wallet.mode === "wallet" ? "Deploy with connected wallet" : "Confirm and deploy"}<ArrowIcon/></button>}</div>
      </form>
      <aside className="post-aside"><section className="panel"><span className="feature-icon"><ShieldIcon/></span><h3>{jobType === "BOUNTY" ? "One reward, open competition" : wallet.mode === "wallet" ? "Your wallet controls the escrow" : "Demo mode protects the boundary"}</h3><p>{jobType === "BOUNTY" ? `Up to ${maxSubmissions} independent wallets can submit one entry each. The client cannot enter and only the highest qualifying result is paid.` : wallet.mode === "wallet" ? "Your connected wallet becomes the client. A separate worker wallet must accept and submit the job." : "Two separate test accounts act as client and worker. No personal wallet is connected."}</p><details className="score-help"><summary>Technical details</summary><p>{jobType === "BOUNTY" ? "The Bounty contract records entries on-chain, closes submissions permanently, evaluates all public URLs under one shared rubric, and settles only the recorded winner or refunds the client." : wallet.mode === "wallet" ? "GenLayerJS submits the deployment through your injected wallet. After Bradbury confirms it, the backend verifies its on-chain roles and requirements before registering it." : "The Render-held demo client signs deployment. A separate Render-held demo worker accepts and submits. Registry records persist on the backend."}</p></details></section><section className="panel"><p className="card-kicker">Live requirement coaching</p><h3>{specQuality >= 75 ? "Ready to be checked." : specQuality >= 45 ? "Add measurable details." : "Make the requirements clear."}</h3><p>Strong requirements name the deliverable, list required parts, define observable behavior, and require a public URL.</p><div className="quality-score"><span>Requirement quality</span><strong>{specQuality}<small>/100</small></strong></div></section></aside>
    </div>
  </div>;
}
