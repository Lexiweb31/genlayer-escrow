"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowIcon, CheckIcon, ShieldIcon } from "@/components/icons";
import { useDemoMode } from "@/components/providers";
import { PageHeader, StatusPill } from "@/components/ui";
import { friendlyApiError, meritApi } from "@/lib/api";

const templates = [
  { title: "Responsive product landing page", spec: "Build a responsive product landing page with a clear hero, at least three measurable benefit sections, accessible mobile navigation, a working primary call-to-action, a security section, and a complete footer. Publish it at a public HTTPS URL." },
  { title: "Evidence-backed UX audit", spec: "Audit the public onboarding flow and deliver a written report with at least ten annotated findings, severity labels, reproducible steps, and prioritized recommendations. Publish the complete report at a public HTTPS URL." },
  { title: "Protocol research brief", spec: "Compare five decentralized arbitration protocols using linked primary sources, a consistent evaluation framework, a decision matrix, and a concise recommendation. Publish the brief at a public HTTPS URL." },
];

export default function PostJobPage() {
  const router = useRouter();
  const { demo } = useDemoMode();
  const [title, setTitle] = useState("");
  const [spec, setSpec] = useState("");
  const [fee, setFee] = useState("2");
  const [minScore, setMinScore] = useState("70");
  const [partialFloor, setPartialFloor] = useState("40");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [step, setStep] = useState(1);
  const live = Boolean(demo?.live_actions_enabled);
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

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const feeNumber = Number(fee);
    const minNumber = Number(minScore);
    const floorNumber = Number(partialFloor);
    if (spec.trim().length < 20) return setError("Describe a specific, testable deliverable in at least 20 characters.");
    if (!Number.isFinite(feeNumber) || feeNumber < 0 || feeNumber > 10) return setError("The Merit fee must be between 0% and 10%.");
    if (!Number.isInteger(minNumber) || minNumber < 0 || minNumber > 100) return setError("Full payment must start at a whole-number score from 0 to 100.");
    if (!Number.isInteger(floorNumber) || floorNumber < 0 || floorNumber > minNumber) return setError("Refund below must be a whole-number score from 0 up to the full-payment score.");
    if (!live) return setError("Live deployment is disabled until Render has two different Bradbury demo signers. No transaction was submitted.");
    setBusy(true);
    setStatus("Deploying the intelligent escrow with the Bradbury demo client. This can take up to 90 seconds…");
    try {
      const response = await meritApi.createJob({ title: title.trim() || null, spec: spec.trim(), fee_bps: Math.round(feeNumber * 100), min_score: minNumber, partial_floor: floorNumber });
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
    if (step === 2) {
      const feeNumber = Number(fee); const minNumber = Number(minScore); const floorNumber = Number(partialFloor);
      if (!Number.isFinite(feeNumber) || feeNumber < 0 || feeNumber > 10) return setError("The Merit fee must be between 0% and 10%.");
      if (!Number.isInteger(minNumber) || minNumber < 0 || minNumber > 100) return setError("Full payment must start at a whole-number score from 0 to 100.");
      if (!Number.isInteger(floorNumber) || floorNumber < 0 || floorNumber > minNumber) return setError("Refund below must be a whole-number score from 0 up to the full-payment score.");
    }
    setStep((current) => Math.min(3, current + 1));
  };

  return <div className="page-container wide-form-page">
    <PageHeader eyebrow="Guided job creation" title="Create a protected job" description="Describe the work, decide how payment should be handled, and review everything before publishing."/>
    <nav className="builder-progress" aria-label="Protected job builder progress">{["Job requirements", "Payment rules", "Review and publish"].map((label, index) => <button type="button" key={label} className={step === index + 1 ? "active" : step > index + 1 ? "complete" : ""} onClick={() => { if (index + 1 < step) setStep(index + 1); }} disabled={index + 1 > step}><span>{step > index + 1 ? <CheckIcon size={14}/> : index + 1}</span><b>{label}</b></button>)}</nav>
    <div className="post-layout">
      <form className="panel post-form workflow-active" onSubmit={submit}>
        {step === 1 && <div className="form-section builder-stage"><div className="form-section-head"><span>01</span><div><h2>What work do you need?</h2><p>Write clear requirements that the completed work can be checked against.</p></div></div><label><span>Job title</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Responsive product landing page" maxLength={80}/></label><label><span>What must the finished work include?</span><textarea value={spec} onChange={(event) => setSpec(event.target.value)} placeholder="List the required sections, features, formats, working links, and anything else the completed work must contain." rows={9}/><small>{spec.length} characters · Requirement quality {specQuality}/100</small></label><div className="spec-meter" aria-label={`Requirement quality ${specQuality} out of 100`}><i style={{ width: `${specQuality}%` }}/></div><div className="template-row" aria-label="Job requirement templates">{templates.map((template) => <button type="button" key={template.title} onClick={() => { setTitle(template.title); setSpec(template.spec); }}>{template.title}</button>)}</div></div>}
        {step === 2 && <div className="form-section builder-stage"><div className="form-section-head"><span>02</span><div><h2>Decide how payment works</h2><p>Choose the score ranges that control refunds, split payments, and full payment.</p></div></div><div className="field-grid"><label><span>Merit fee (%)</span><small>The percentage deducted when payment goes to the worker.</small><input type="number" inputMode="decimal" min="0" max="10" step="0.1" value={fee} onChange={(event) => setFee(event.target.value)}/></label><label><span>Full payment starts at</span><small>The minimum evaluation score required for the worker to receive full payment.</small><input type="number" inputMode="numeric" min="0" max="100" value={minScore} onChange={(event) => setMinScore(event.target.value)}/></label><label><span>Refund below</span><small>Scores below this number return the payment to the client.</small><input type="number" inputMode="numeric" min="0" max="100" value={partialFloor} onChange={(event) => setPartialFloor(event.target.value)}/></label></div><div className="payment-preview" aria-live="polite"><p className="card-kicker">Live payment preview</p><div className="threshold-preview"><span><i className="refund"/><b>Score 0–{paymentBands.refundEnd}:</b> Client receives a refund</span><span><i className="split"/><b>Score {paymentBands.refund}–{paymentBands.splitEnd}:</b> Payment is split based on the score</span><span><i className="pay"/><b>Score {paymentBands.full}–100:</b> Worker receives full payment</span></div><strong>{fee || "0"}% is deducted from the worker’s payment</strong></div><details className="score-help"><summary>Learn how scoring works</summary><p>AI validators compare the submitted work with your requirements. Their consensus produces an evaluation score. The payment thresholds choose a full payment, partial payout, or refund; the result is complete only after on-chain finalization.</p></details><div className="funding-handoff"><b>Funding follows publishing</b><p>After the job is created, Manage Job accepts a precision-safe GEN amount. The default and minimum are 0.001 GEN.</p></div></div>}
        {step === 3 && <div className="form-section builder-stage review-stage"><div className="form-section-head"><span>03</span><div><h2>Review and publish</h2><p>Check the requirements and payment rules before the demo client publishes the job.</p></div></div><div className="review-grid"><div><span>Job title</span><strong>{title.trim() || "Untitled protected job"}</strong></div><div className="review-spec"><span>Job requirements</span><p>{spec}</p></div><div><span>Full payment starts at</span><strong>{minScore}/100</strong></div><div><span>Payment is split</span><strong>{partialFloor}–{paymentBands.splitEnd}/100</strong></div><div><span>Refund below</span><strong>{partialFloor}/100</strong></div><div><span>Merit fee</span><strong>{fee}%</strong></div></div><div className="inline-alert info"><b>Demo mode</b><span>Two test accounts show the client and worker flow. No personal wallet or visitor funds are used.</span></div></div>}
        {error && <div className="form-error" role="alert">{error}</div>}{status && <div className="form-status" aria-live="polite"><span className="loader"/>{status}</div>}
        <div className="form-submit"><div>{step > 1 && <button type="button" className="button secondary" onClick={() => setStep((current) => current - 1)} disabled={busy}>Back</button>}<StatusPill tone={live ? "success" : "warning"}>{live ? "Separate demo roles ready" : "Live actions disabled"}</StatusPill><small>Server-signed Bradbury testnet transaction</small></div>{step < 3 ? <button type="button" className="button primary large" onClick={continueBuilder}>Continue <ArrowIcon/></button> : <button className="button primary large" disabled={busy || !live}>{busy ? "Deploying…" : "Confirm and deploy"}<ArrowIcon/></button>}</div>
      </form>
      <aside className="post-aside"><section className="panel"><span className="feature-icon"><ShieldIcon/></span><h3>Demo mode protects the boundary</h3><p>Two separate test accounts act as client and worker. No personal wallet is connected.</p><details className="score-help"><summary>Technical details</summary><p>The Render-held demo client signs deployment. A separate Render-held demo worker accepts and submits. Registry records persist on the backend.</p></details></section><section className="panel"><p className="card-kicker">Live requirement coaching</p><h3>{specQuality >= 75 ? "Ready to be checked." : specQuality >= 45 ? "Add measurable details." : "Make the requirements clear."}</h3><p>Strong requirements name the deliverable, list required parts, define observable behavior, and require a public URL.</p><div className="quality-score"><span>Requirement quality</span><strong>{specQuality}<small>/100</small></strong></div></section></aside>
    </div>
  </div>;
}
