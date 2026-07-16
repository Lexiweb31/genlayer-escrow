"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { PlusIcon, RefreshIcon } from "@/components/icons";
import { JobCard } from "@/components/job-card";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/ui";
import { formatWei } from "@/lib/amount";
import { useJobs } from "@/lib/hooks";

export default function BrowseJobsPage() {
  const { data, error, loading, refresh } = useJobs();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const filtered = useMemo(() => (data?.jobs || []).filter((job) => {
    const matchesQuery = `${job.title || ""} ${job.spec || ""} ${job.address}`.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === "ALL" || (status === "ACTIVE" ? ["UNFUNDED", "OPEN", "AGREED", "SUBMITTED", "EVALUATED"].includes(job.status) : status === "FINALIZED" ? ["ACCEPTED", "PARTIAL", "REFUNDED"].includes(job.status) : job.status === status);
    return matchesQuery && matchesStatus;
  }), [data, query, status]);

  return <div className="page-container">
    <PageHeader eyebrow="Shared marketplace" title="Browse intelligent escrows" description="Every browser sees the same durable registry, exact GEN values, evaluation state, and settlement evidence." actions={<><button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh</button><Link className="button primary" href="/jobs/new"><PlusIcon/> Post a job</Link></>}/>
    {data && <section className="stat-grid marketplace-stats" aria-label="Marketplace totals">
      <article><span>GEN locked in active escrow</span><strong>{formatWei(data.stats.locked_wei)}</strong><small>Still held by active contracts</small></article>
      <article className="pending"><span>Outbound settlement pending</span><strong>{formatWei(data.stats.pending_settlement_wei)}</strong><small>{data.stats.settlement_pending} settlement{data.stats.settlement_pending === 1 ? "" : "s"} pending</small></article>
      <article><span>Finalized settlement value</span><strong>{formatWei(data.stats.finalized_settlement_wei)}</strong><small>{data.stats.finalized_settlements} verified settlement{data.stats.finalized_settlements === 1 ? "" : "s"}</small></article>
      <article><span>Shared registry</span><strong>{data.stats.total_jobs}</strong><small>{data.stats.legacy_jobs} legacy · {data.stats.degraded_jobs} degraded</small></article>
    </section>}
    <section className="market-toolbar" aria-label="Marketplace filters"><label className="search-field"><span>Search</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, specification, or address"/></label><label><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">All jobs</option><option value="ACTIVE">Active lifecycle</option><option value="SETTLEMENT_PENDING">Settlement pending</option><option value="FINALIZED">Finalized</option><option value="LEGACY_UNSAFE">Legacy read-only</option></select></label></section>
    {loading && !data
      ? <LoadingState label="Loading the durable marketplace…"/>
      : error && !data
        ? <ErrorState message={error.message} retry={refresh}/>
        : filtered.length
          ? <section className="job-grid">{filtered.map((job) => <JobCard key={job.address} job={job}/>)}</section>
          : <EmptyState title="No escrows match these filters" description="Clear the search or choose a different lifecycle status." action={<button className="button secondary" onClick={() => { setQuery(""); setStatus("ALL"); }}>Clear filters</button>}/>}
  </div>;
}
