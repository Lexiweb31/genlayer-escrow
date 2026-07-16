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

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    const feeNumber = Number(fee);
    const minNumber = Number(minScore);
    const floorNumber = Number(partialFloor);
    if (spec.trim().length < 20) return setError("Describe a specific, testable deliverable in at least 20 characters.");
    if (!Number.isFinite(feeNumber) || feeNumber < 0 || feeNumber > 10) return setError("The declared fee must be between 0% and 10%.");
    if (!Number.isInteger(minNumber) || minNumber < 0 || minNumber > 100) return setError("The full-payment threshold must be an integer from 0 to 100.");
    if (!Number.isInteger(floorNumber) || floorNumber < 0 || floorNumber > minNumber) return setError("The partial floor must be an integer from 0 to the full-payment threshold.");
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
      if (!Number.isFinite(feeNumber) || feeNumber < 0 || feeNumber > 10) return setError("The declared fee must be between 0% and 10%.");
      if (!Number.isInteger(minNumber) || minNumber < 0 || minNumber > 100) return setError("The full-payment threshold must be an integer from 0 to 100.");
      if (!Number.isInteger(floorNumber) || floorNumber < 0 || floorNumber > minNumber) return setError("The partial floor must be an integer from 0 to the full-payment threshold.");
    }
    setStep((current) => Math.min(3, current + 1));
  };

  return <div className="page-container wide-form-page">
    <PageHeader eyebrow="Guided job creation" title="Create a contract-ready agreement" description="Define observable work and deterministic settlement thresholds. The server-side Bradbury demo client deploys; no visitor wallet is connected."/>
    <nav className="builder-progress" aria-label="Agreement builder progress">{["Agreement", "Settlement", "Review"].map((label, index) => <button type="button" key={label} className={step === index + 1 ? "active" : step > index + 1 ? "complete" : ""} onClick={() => { if (index + 1 < step) setStep(index + 1); }} disabled={index + 1 > step}><span>{step > index + 1 ? <CheckIcon size={14}/> : index + 1}</span><b>{label}</b></button>)}</nav>
    <div className="post-layout">
      <form className="panel post-form workflow-active" onSubmit={submit}>
        {step === 1 && <div className="form-section builder-stage"><div className="form-section-head"><span>01</span><div><h2>Describe the outcome</h2><p>Give validators observable evidence to inspect.</p></div></div><label><span>Job title</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Responsive product landing page" maxLength={80}/></label><label><span>Acceptance specification</span><textarea value={spec} onChange={(event) => setSpec(event.target.value)} placeholder="Describe required sections, observable behavior, counts, formats, and the public delivery URL…" rows={9}/><small>{spec.length} characters · specificity score {specQuality}/100</small></label><div className="spec-meter" aria-label={`Specification quality ${specQuality} out of 100`}><i style={{ width: `${specQuality}%` }}/></div><div className="template-row" aria-label="Specification templates">{templates.map((template) => <button type="button" key={template.title} onClick={() => { setTitle(template.title); setSpec(template.spec); }}>{template.title}</button>)}</div></div>}
        {step === 2 && <div className="form-section builder-stage"><div className="form-section-head"><span>02</span><div><h2>Set deterministic thresholds</h2><p>The contract uses these immutable bands after deployment.</p></div></div><div className="field-grid"><label><span>Declared fee (%)</span><input type="number" inputMode="decimal" min="0" max="10" step="0.1" value={fee} onChange={(event) => setFee(event.target.value)}/></label><label><span>Full-payment score</span><input type="number" inputMode="numeric" min="0" max="100" value={minScore} onChange={(event) => setMinScore(event.target.value)}/></label><label><span>Partial floor</span><input type="number" inputMode="numeric" min="0" max="100" value={partialFloor} onChange={(event) => setPartialFloor(event.target.value)}/></label></div><div className="threshold-preview"><span><i className="refund"/>Below {partialFloor || "—"}: client refund</span><span><i className="split"/>{partialFloor || "—"}–{Number(minScore || 0) - 1}: proportional split</span><span><i className="pay"/>{minScore || "—"}+: worker payout</span></div><div className="funding-handoff"><b>Funding follows deployment</b><p>After the contract is created, Manage Job accepts a precision-safe GEN amount. The default and minimum are 0.001 GEN.</p></div></div>}
        {step === 3 && <div className="form-section builder-stage review-stage"><div className="form-section-head"><span>03</span><div><h2>Review before signing</h2><p>This becomes the demo client’s contract deployment transaction.</p></div></div><div className="review-grid"><div><span>Title</span><strong>{title.trim() || "Untitled intelligent escrow"}</strong></div><div className="review-spec"><span>Acceptance specification</span><p>{spec}</p></div><div><span>Full payout</span><strong>{minScore}/100 or higher</strong></div><div><span>Partial settlement</span><strong>{partialFloor}–{Number(minScore) - 1}</strong></div><div><span>Client refund</span><strong>Below {partialFloor}/100</strong></div><div><span>Declared fee</span><strong>{fee}%</strong></div></div><div className="inline-alert info"><b>Server-signed Bradbury demo</b><span>The Render-held demo client deploys this contract. No browser wallet or visitor funds are used.</span></div></div>}
        {error && <div className="form-error" role="alert">{error}</div>}{status && <div className="form-status" aria-live="polite"><span className="loader"/>{status}</div>}
        <div className="form-submit"><div>{step > 1 && <button type="button" className="button secondary" onClick={() => setStep((current) => current - 1)} disabled={busy}>Back</button>}<StatusPill tone={live ? "success" : "warning"}>{live ? "Separate demo roles ready" : "Live actions disabled"}</StatusPill><small>Server-signed Bradbury testnet transaction</small></div>{step < 3 ? <button type="button" className="button primary large" onClick={continueBuilder}>Continue <ArrowIcon/></button> : <button className="button primary large" disabled={busy || !live}>{busy ? "Deploying…" : "Confirm and deploy"}<ArrowIcon/></button>}</div>
      </form>
      <aside className="post-aside"><section className="panel"><span className="feature-icon"><ShieldIcon/></span><h3>What gets signed</h3><p>The Render-held demo client signs contract deployment. The worker address is a separate Render-held demo identity.</p><ul className="check-list"><li><CheckIcon/> No browser private key</li><li><CheckIcon/> No wallet custody claim</li><li><CheckIcon/> Durable registry entry</li></ul></section><section className="panel"><p className="card-kicker">Live agreement coaching</p><h3>{specQuality >= 75 ? "Ready for observable evaluation." : specQuality >= 45 ? "Add measurable proof." : "Make the outcome specific."}</h3><p>Strong specifications name a deliverable, list required parts, define observable behavior, and require a public URL.</p><div className="quality-score"><span>Current specificity</span><strong>{specQuality}<small>/100</small></strong></div></section></aside>
    </div>
  </div>;
}
