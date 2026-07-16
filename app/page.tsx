"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowIcon, CheckIcon, ClockIcon, ContractIcon, JobsIcon, ShieldIcon, SparkIcon } from "@/components/icons";
import { StatusPill } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { useJobs } from "@/lib/hooks";
import { settlementPresentation } from "@/lib/settlement";
import { shortAddress } from "@/lib/utils";

export default function HomePage() {
  const { data, error, loading, refresh } = useJobs();
  const [labScore, setLabScore] = useState(82);
  const [storyRun, setStoryRun] = useState(0);
  const result = useMemo(() => labScore >= 70 ? { label: "Worker payout", detail: "98% worker · 2% declared fee", tone: "success" as const } : labScore >= 40 ? { label: "Proportional split", detail: `${Math.round((labScore / 70) * 98)}% worker · remainder client`, tone: "warning" as const } : { label: "Client refund", detail: "100% returned to the demo client", tone: "danger" as const }, [labScore]);
  const latest = data?.jobs.slice(0, 3) || [];

  return <div className="home-page">
    <section className="hero-section">
      <div className="hero-orb one"/><div className="hero-orb two"/>
      <div className="hero-copy">
        <p className="eyebrow hero-eyebrow"><span/>Intelligent escrow on GenLayer</p>
        <h1>Work that can<br/><em>prove itself.</em></h1>
        <p className="hero-lede">Merit turns a public agreement into inspectable evidence, validator judgment, and a settlement path no participant can quietly rewrite.</p>
        <div className="hero-actions"><Link className="button primary large" href="/jobs">Explore live escrows <ArrowIcon/></Link><Link className="button secondary large" href="/jobs/new">Post a demo job</Link></div>
        <div className="trust-line"><span><CheckIcon/> Separate demo roles</span><span><CheckIcon/> Durable shared registry</span><span><CheckIcon/> Inspectable transfers</span></div>
      </div>

      <div className="workspace-frame" aria-label="Live Merit escrow workspace">
        <div className="workspace-bar"><span className="window-dots"><i/><i/><i/></span><span>merit / live escrow workspace</span><StatusPill tone="success"><i className="live-dot"/> Bradbury live</StatusPill></div>
        <div className="workspace-body">
          <aside className="workspace-rail"><span className="mini-brand">m</span><i className="active"><JobsIcon/></i><i><SparkIcon/></i><i><ContractIcon/></i></aside>
          <div className="workspace-content">
            <div className="workspace-heading"><div><small>Shared marketplace</small><strong>Intelligent escrows</strong></div><span>{data?.stats.total_jobs ?? "—"} registry records</span></div>
            {loading && !data ? <div className="workspace-loading"><span className="loader"/> Waking the Render registry…</div> : error && !data ? <div className="workspace-error"><span>Live registry unavailable</span><button onClick={refresh}>Retry</button></div> : <>
              <div className="workspace-stats"><div><small>Locked</small><b>{formatWei(data?.stats.locked_wei)}</b></div><div><small>Pending outbound</small><b>{formatWei(data?.stats.pending_settlement_wei)}</b></div><div><small>Finalized</small><b>{data?.stats.finalized_settlements ?? 0}</b></div></div>
              <div className="workspace-jobs">{latest.map((job) => { const view = settlementPresentation(job); return <Link key={job.address} href={`/jobs/${encodeURIComponent(job.address)}`}><span className={`workspace-status ${view.isPending ? "pending" : view.isFinalized ? "final" : "active"}`}/><div><b>{job.title || "Untitled escrow"}</b><small>{shortAddress(job.address, 7, 4)}</small></div><strong>{formatWei(job.amount)}</strong><StatusPill tone={view.isPending ? "warning" : view.isFinalized ? "success" : "info"}>{view.label}</StatusPill></Link>; })}{!latest.length && <p>No live records yet. Create the first safe demo escrow.</p>}</div>
            </>}
          </div>
        </div>
      </div>
    </section>

    <section className="story-section" key={storyRun}>
      <div className="section-heading"><div><p className="eyebrow">The 30-second escrow story</p><h2>From agreement to evidence-backed settlement.</h2></div><button className="button secondary" onClick={() => setStoryRun((value) => value + 1)}>Replay the flow <ArrowIcon/></button></div>
      <div className="story-path"><div className="story-line"><i/></div>{[
        ["01", "Client funds escrow", "A separate server-side demo client signs and deposits Bradbury testnet GEN."],
        ["02", "Worker submits public work", "The worker role accepts immutable terms and provides a URL validators can inspect."],
        ["03", "Validators inspect evidence", "The contract records a score and decision only after evaluation is returned."],
        ["04", "Contract queues settlement", "Payout, split, or refund stays pending until its outbound transfer is verifiable."],
      ].map(([number, title, copy], index) => <article key={number} style={{ "--delay": `${index * 180}ms` } as React.CSSProperties}><span>{number}</span><div><h3>{title}</h3><p>{copy}</p></div></article>)}</div>
    </section>

    <section className="architecture-section">
      <div className="section-heading"><div><p className="eyebrow">Trust architecture</p><h2>Honest about who signs—and what is final.</h2></div><p>Demo mode is useful because its boundaries stay visible. Wallet custody is a separate future architecture, not a marketing claim.</p></div>
      <div className="architecture-grid"><article><span><ShieldIcon/></span><h3>Role-separated signers</h3><p>The Render server owns different Bradbury demo client and worker keys. A visitor wallet is never implied.</p><small>SERVER-SIGNED DEMO</small></article><article><span><JobsIcon/></span><h3>Shared durable state</h3><p>Every browser reads one SQLite-backed marketplace registry on Render’s persistent disk.</p><small>PERSISTED REGISTRY</small></article><article><span><ClockIcon/></span><h3>Finality-aware receipts</h3><p>A recorded decision remains “Settlement pending” until external-message evidence is confirmed.</p><small>NO PREMATURE SUCCESS</small></article></div>
    </section>

    <section className="lab-section">
      <div className="lab-copy"><p className="eyebrow">Interactive settlement lab</p><h2>One score. Three deterministic outcomes.</h2><p>Explore the configured thresholds without submitting a transaction. This simulation mirrors the agreement bands but is clearly not an on-chain result.</p><div className="lab-thresholds"><span>Refund below 40</span><span>Split 40–69</span><span>Full payout 70+</span></div></div>
      <div className="lab-card"><div className="lab-card-head"><span>Simulated validator score</span><b>{labScore}<small>/100</small></b></div><input aria-label="Simulated validator score" type="range" min="0" max="100" value={labScore} onChange={(event) => setLabScore(Number(event.target.value))}/><div className="range-labels"><span>0</span><span>40</span><span>70</span><span>100</span></div><div className={`lab-result ${result.tone === "success" ? "outcome-success" : result.tone === "warning" ? "outcome-pending" : "outcome-refund"}`}><StatusPill tone={result.tone}>{result.label}</StatusPill><strong>{result.detail}</strong><small>Simulation only · no on-chain transaction</small></div></div>
    </section>

    <section className="home-cta"><div><p className="eyebrow">Ready to inspect the system?</p><h2>Follow the proof, not the promise.</h2></div><div><Link className="button primary large" href="/jobs">Browse live jobs <ArrowIcon/></Link><Link className="button secondary large" href="/contracts">View infrastructure</Link></div></section>
  </div>;
}
