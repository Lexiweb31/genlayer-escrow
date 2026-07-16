"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ActivityIcon, ArrowIcon, CheckIcon, ClockIcon, CodeIcon, ContractIcon, ExternalIcon, LinkIcon, LockIcon, ShieldIcon, SparkIcon, UserIcon } from "@/components/icons";
import { EscrowCoreMark, EscrowProductVisual, StoryEscrowCore } from "@/components/escrow-core";
import { JobCard } from "@/components/job-card";
import { MonoValue, StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { useJobs } from "@/lib/hooks";
import { hasConfirmedEvaluation, settlementPresentation } from "@/lib/settlement";
import { relativeTime, shortAddress } from "@/lib/utils";

const storySteps = [
  ["Acceptance specification", "The client defines observable work and deterministic score bands."],
  ["GEN enters the core", "Bradbury demo GEN is locked by the escrow contract."],
  ["Worker accepts", "A separate demo worker signs the immutable public terms."],
  ["Evidence is submitted", "A public HTTPS deliverable becomes the validator input."],
  ["Validators inspect", "Consensus participants evaluate evidence against the agreement."],
  ["Consensus completes", "The confirmed score selects payout, split, or refund."],
  ["Settlement is queued", "The contract emits an outbound transfer to the recipient."],
  ["Explorer proof appears", "Merit shows final success only after transfer evidence is verified."],
];

const objections = [
  ["Is this a user-controlled wallet?", "Not yet. Demo mode is server-signed on Bradbury and clearly separated from the disabled wallet-mode roadmap."],
  ["Can a client silently change the agreement?", "No. The acceptance specification and settlement thresholds are deployed with the escrow contract."],
  ["Does an evaluation decision mean funds moved?", "No. Merit keeps the decision and transfer status separate until outbound evidence finalizes."],
  ["What happens when the network is slow?", "Actions disable while pending, state can be refreshed safely, and the parent transaction remains inspectable."],
];

export default function HomePage() {
  const { data, error, loading, refresh } = useJobs();
  const [labScore, setLabScore] = useState(82);
  const [storyRun, setStoryRun] = useState(1);
  const [activeStory, setActiveStory] = useState(0);
  const result = useMemo(() => labScore >= 70 ? { label: "Worker payout", detail: "98% worker · 2% declared fee", tone: "success" as const } : labScore >= 40 ? { label: "Proportional split", detail: `${Math.round((labScore / 70) * 98)}% worker · remainder client`, tone: "warning" as const } : { label: "Client refund", detail: "100% returned to the demo client", tone: "danger" as const }, [labScore]);
  const latest = data?.jobs.slice(0, 3) || [];
  const featured = latest[0];
  const featuredView = featured ? settlementPresentation(featured) : null;

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { queueMicrotask(() => setActiveStory(storySteps.length)); return; }
    let step = 0;
    const timer = window.setInterval(() => { step += 1; setActiveStory(step); if (step >= storySteps.length) window.clearInterval(timer); }, 520);
    return () => window.clearInterval(timer);
  }, [storyRun]);
  const replayStory = () => { setActiveStory(0); setStoryRun((run) => run + 1); };

  return <div className="marketing-page">
    <section className="cinematic-hero" id="product">
      <div className="hero-light hero-light-blue"/><div className="hero-light hero-light-violet"/>
      <div className="cinematic-copy">
        <div className="hero-network"><span><i/> Bradbury testnet</span><b>Server-signed demo</b></div>
        <h1>Work that can<br/><em>prove itself.</em></h1>
        <p>Merit turns public agreements into evidence-backed outcomes—with validator consensus, deterministic settlement, and proof you can inspect.</p>
        <div className="cinematic-actions"><Link className="button primary hero-primary" href="/jobs">Launch Merit <ArrowIcon/></Link><a className="button secondary" href="#how-it-works">Watch how it settles <span className="play-mark">▶</span></a></div>
        <div className="hero-assurances"><span><CheckIcon/> Separate client and worker roles</span><span><CheckIcon/> Finality-aware receipts</span><span><CheckIcon/> Same-origin API boundary</span></div>
      </div>
      <EscrowProductVisual amount={featured?.amount || "1000000000000000"} score={hasConfirmedEvaluation(featured || { address: "", status: "UNKNOWN" }) ? featured?.score || 82 : 82} address={featured?.address} transaction={featured?.settlement?.parent_transaction || featured?.deployment_tx}/>
    </section>

    <section className="protocol-strip" aria-label="Live Merit protocol status">
      <div><span className="protocol-live"><i/> Network</span><strong>{data?.stats.network || "Bradbury"}</strong></div>
      <div><span>Active locked</span><strong>{formatWei(data?.stats.locked_wei)}</strong></div>
      <div><span>Pending outbound</span><strong>{formatWei(data?.stats.pending_settlement_wei)}</strong></div>
      <div><span>Finalized value</span><strong>{formatWei(data?.stats.finalized_settlement_wei)}</strong></div>
      <div><span>Registry sync</span><strong>{data?.stats.generated_at ? relativeTime(data.stats.generated_at) : loading ? "Connecting…" : "Unavailable"}</strong></div>
    </section>

    <section className="marketing-section settlement-story-section" id="how-it-works">
      <header className="marketing-section-heading"><div><p className="section-index">01 / Product story</p><h2>See the agreement become a settlement.</h2></div><div><p>One replayable sequence. Every state means something.</p><button className="button secondary" onClick={replayStory}>Replay sequence <ArrowIcon/></button></div></header>
      <div className="settlement-story" key={storyRun}>
        <StoryEscrowCore activeStep={activeStory}/>
        <ol className="story-step-list">{storySteps.map(([title, copy], index) => <li key={title} className={index < activeStory ? "complete" : index === activeStory ? "active" : "future"}><span>{index < activeStory ? <CheckIcon/> : String(index + 1).padStart(2, "0")}</span><div><b>{title}</b><p>{copy}</p></div></li>)}</ol>
      </div>
    </section>

    <section className="product-showcase marketing-section" id="product-showcase">
      <header className="showcase-copy"><p className="section-index">02 / One control room</p><h2>Agreement, evidence, consensus, and transfer—in one place.</h2><p>Merit keeps the contract decision separate from outbound transfer finality. That distinction is the product.</p><Link className="text-link" href={featured ? `/jobs/${encodeURIComponent(featured.address)}` : "/jobs"}>Open a live control room <ArrowIcon/></Link></header>
      <div className="showcase-window">
        <div className="showcase-window-bar"><span className="window-dots"><i/><i/><i/></span><MonoValue>merit / escrow-control-room</MonoValue><StatusPill tone={featuredView?.isPending ? "warning" : featuredView?.isFinalized ? "success" : "info"}>{featuredView?.label || "Live registry"}</StatusPill></div>
        <div className="showcase-window-body"><div className="showcase-balance"><span>Escrow value</span><strong>{formatWei(featured?.amount)}</strong><small>{featuredView?.isPending ? "Outbound transfer pending finalization" : featuredView?.isFinalized ? "Transfer evidence finalized" : "Contract lifecycle active"}</small></div><div className="showcase-facts"><div><span>Contract</span><MonoValue>{shortAddress(featured?.address, 10, 7)}</MonoValue></div><div><span>Evidence</span><strong>{featured?.submission_url ? "Public URL submitted" : "Awaiting submission"}</strong></div><div><span>Evaluation</span><strong>{featured && hasConfirmedEvaluation(featured) ? `${featured.score}/100 confirmed` : "Not evaluated yet"}</strong></div><div><span>Settlement</span><strong>{featuredView?.label || "Awaiting registry"}</strong></div></div><div className="showcase-timeline"><span className="done"><i/><b>Agreement</b></span><span className={featured?.submission_url ? "done" : "active"}><i/><b>Evidence</b></span><span className={featured && hasConfirmedEvaluation(featured) ? "done" : "future"}><i/><b>Consensus</b></span><span className={featuredView?.isFinalized ? "done" : featuredView?.isPending ? "active" : "future"}><i/><b>Transfer</b></span></div></div>
      </div>
    </section>

    <section className="genlayer-section marketing-section">
      <div className="genlayer-core"><EscrowCoreMark size="large"/><div className="orbit orbit-one"/><div className="orbit orbit-two"/></div>
      <div className="genlayer-copy"><p className="section-index">03 / Why GenLayer</p><h2>A normal contract can move value. An intelligent contract can judge evidence.</h2><p>Merit needs verifiable web inspection and agreement-based reasoning before deterministic payout bands can run.</p><div className="genlayer-points"><article><SparkIcon/><div><b>Evidence-aware consensus</b><p>Validators inspect public work against the deployed acceptance specification.</p></div></article><article><ContractIcon/><div><b>Deterministic consequence</b><p>The confirmed score selects the contract’s predefined payout, split, or refund path.</p></div></article><article><LinkIcon/><div><b>Inspectable finality</b><p>Parent transactions and outbound transfer evidence remain visible after the decision.</p></div></article></div></div>
    </section>

    <section className="marketing-section live-proof-section" id="product-proof">
      <header className="marketing-section-heading"><div><p className="section-index">04 / Live product proof</p><h2>Real registry records. No invented finality.</h2></div><div><p>{error ? "The live registry is temporarily unavailable; no confirmed data is being simulated." : "Values below come from Merit’s same-origin API boundary."}</p><button className="button secondary" onClick={refresh} disabled={loading}>Refresh proof <ActivityIcon/></button></div></header>
      {latest.length ? <div className="proof-job-grid">{latest.map((job) => <JobCard job={job} key={job.address}/>)}</div> : <div className="proof-empty"><EscrowCoreMark/><strong>{loading ? "Reading Bradbury registry…" : "No live records available"}</strong><p>{error?.message || "Create the first safe demo escrow from the application."}</p></div>}
    </section>

    <section className="security-section marketing-section" id="security">
      <div className="security-copy"><p className="section-index">05 / Security boundary</p><h2>Trust comes from naming the boundary.</h2><p>The browser never receives signer keys or Render configuration. It calls only same-origin Next.js routes, which proxy a narrow, sanitized API surface.</p><Link className="button secondary" href="/contracts">Inspect infrastructure <ArrowIcon/></Link></div>
      <div className="boundary-diagram" aria-label="Merit request and secret boundary"><div><span><UserIcon/></span><b>Browser</b><small>No secrets · no signer custody</small></div><i><ArrowIcon/></i><div><span><ShieldIcon/></span><b>Next.js boundary</b><small>Same-origin route allowlist</small></div><i><ArrowIcon/></i><div className="protected"><span><LockIcon/></span><b>Render trust zone</b><small>Separate signers · durable store</small></div></div>
      <div className="security-grid"><article><CodeIcon/><b>Prompt-injection boundary</b><p>Only public deliverable evidence is inspected. Secret configuration is never part of validator input.</p></article><article><ShieldIcon/><b>Role-separated actions</b><p>Client deploys and funds. A different demo worker accepts and submits.</p></article><article><ClockIcon/><b>Finality-aware language</b><p>“Payment released” appears only after confirmed outbound transfer evidence.</p></article></div>
    </section>

    <section className="use-case-section marketing-section"><header><p className="section-index">06 / Built for both sides</p><h2>Proof changes the working relationship.</h2></header><div className="use-case-grid"><article className="client-case"><span><UserIcon/></span><p>For clients</p><h3>Define success before funds move.</h3><ul><li><CheckIcon/> Observable acceptance criteria</li><li><CheckIcon/> GEN locked by contract state</li><li><CheckIcon/> Refund path when evidence fails</li></ul><Link href="/jobs/new">Create an agreement <ArrowIcon/></Link></article><article className="worker-case"><span><UserIcon/></span><p>For workers</p><h3>Turn public work into payment evidence.</h3><ul><li><CheckIcon/> Immutable agreement terms</li><li><CheckIcon/> Inspectable evaluation reasoning</li><li><CheckIcon/> Verifiable recipient and amount</li></ul><Link href="/jobs">Browse escrows <ArrowIcon/></Link></article></div></section>

    <section className="lab-section competition-lab marketing-section">
      <div className="lab-copy"><p className="section-index">07 / Settlement simulator</p><h2>Move the score. See the contract consequence.</h2><p>This is an explicitly simulated threshold preview—never an on-chain result.</p><div className="lab-thresholds"><span>Refund below 40</span><span>Split 40–69</span><span>Full payout 70+</span></div></div>
      <div className="lab-card"><div className="lab-card-head"><span>Illustrative consensus score</span><b>{labScore}<small>/100</small></b></div><input aria-label="Illustrative consensus score" type="range" min="0" max="100" value={labScore} onChange={(event) => setLabScore(Number(event.target.value))}/><div className="range-labels"><span>0</span><span>40</span><span>70</span><span>100</span></div><div className={`lab-result ${result.tone === "success" ? "outcome-success" : result.tone === "warning" ? "outcome-pending" : "outcome-refund"}`}><StatusPill tone={result.tone}>{result.label}</StatusPill><strong>{result.detail}</strong><small>Simulation only · no transaction submitted</small></div></div>
    </section>

    <section className="questions-section marketing-section"><header><p className="section-index">08 / Questions and objections</p><h2>Understand the trust model before using the demo.</h2></header><div className="question-list">{objections.map(([question, answer]) => <details key={question}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}</div></section>

    <section className="final-marketing-cta"><div className="final-core"><EscrowCoreMark size="large" tone="success"/></div><p className="section-index">Agreement → evidence → settlement</p><h2>Make the proof part of the work.</h2><p>Launch the Bradbury demo and inspect every state for yourself.</p><div><Link className="button primary hero-primary" href="/jobs">Launch Merit <ArrowIcon/></Link><a className="button secondary" href="https://github.com/Lexiweb31/genlayer-escrow" target="_blank" rel="noreferrer">View source <ExternalIcon/></a></div></section>

    <footer className="marketing-footer"><Link className="brand" href="/"><span className="brand-mark"><span/></span><span>merit</span></Link><p>Intelligent escrow for work that can prove itself.</p><nav><a href="#product">Product</a><a href="#how-it-works">How it works</a><a href="#security">Security</a><Link href="/jobs">Explorer</Link><Link href="/contracts">Contracts</Link><a href="https://github.com/Lexiweb31/genlayer-escrow" target="_blank" rel="noreferrer">GitHub</a></nav><div><StatusPill tone="success"><i className="live-dot"/> Bradbury testnet</StatusPill><small>Server-signed demo · no browser wallet custody</small></div></footer>
  </div>;
}
