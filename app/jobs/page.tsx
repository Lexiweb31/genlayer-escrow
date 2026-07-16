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
  const [sort, setSort] = useState("NEWEST");
  const [page, setPage] = useState(1);
  const pageSize = 6;
  const filtered = useMemo(() => (data?.jobs || []).filter((job) => {
    const matchesQuery = `${job.title || ""} ${job.spec || ""} ${job.address}`.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === "ALL" || (status === "ACTIVE" ? ["UNFUNDED", "OPEN", "AGREED", "SUBMITTED", "EVALUATED"].includes(job.status) : status === "FINALIZED" ? ["ACCEPTED", "PARTIAL", "REFUNDED"].includes(job.status) : job.status === status);
    return matchesQuery && matchesStatus;
  }).sort((a, b) => {
    if (sort === "VALUE_HIGH" || sort === "VALUE_LOW") {
      const first = BigInt(a.amount || "0"); const second = BigInt(b.amount || "0");
      const order = first === second ? 0 : first > second ? 1 : -1;
      return sort === "VALUE_HIGH" ? -order : order;
    }
    return sort === "OLDEST" ? new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime() : new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
  }), [data, query, status, sort]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visible = filtered.slice((Math.min(page, pageCount) - 1) * pageSize, Math.min(page, pageCount) * pageSize);

  return <div className="page-container">
    <PageHeader eyebrow="Shared marketplace" title="Browse protected jobs" description="See the same shared job records, exact GEN values, evaluation results, and payment status in every browser." actions={<><button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh</button><Link className="button primary" href="/jobs/new"><PlusIcon/> Post a job</Link></>}/>
    {data && <section className="stat-grid marketplace-stats" aria-label="Marketplace totals">
      <article><span>GEN locked in active escrow</span><strong>{formatWei(data.stats.locked_wei)}</strong><small>Still held by active contracts</small></article>
      <article className="pending"><span>Payments processing</span><strong>{formatWei(data.stats.pending_settlement_wei)}</strong><small>{data.stats.settlement_pending} payment{data.stats.settlement_pending === 1 ? "" : "s"} awaiting confirmation</small></article>
      <article><span>Payments confirmed</span><strong>{formatWei(data.stats.finalized_settlement_wei)}</strong><small>{data.stats.finalized_settlements} verified payment{data.stats.finalized_settlements === 1 ? "" : "s"}</small></article>
      <article><span>Shared registry</span><strong>{data.stats.total_jobs}</strong><small>{data.stats.legacy_jobs} legacy · {data.stats.degraded_jobs} degraded</small></article>
    </section>}
    <section className="market-toolbar" aria-label="Marketplace filters"><label className="search-field"><span>Search</span><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Title, requirements, or address"/></label><label><span>Status</span><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="ALL">All jobs</option><option value="ACTIVE">In progress</option><option value="SETTLEMENT_PENDING">Payment processing</option><option value="FINALIZED">Payment confirmed</option><option value="LEGACY_UNSAFE">Legacy read-only</option></select></label><label><span>Sort</span><select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}><option value="NEWEST">Newest first</option><option value="OLDEST">Oldest first</option><option value="VALUE_HIGH">Highest GEN value</option><option value="VALUE_LOW">Lowest GEN value</option></select></label></section>
    {loading && !data
      ? <LoadingState label="Loading the durable marketplace…"/>
      : error && !data
        ? <ErrorState message={error.message} retry={refresh}/>
        : filtered.length
          ? <><section className="job-grid">{visible.map((job) => <JobCard key={job.address} job={job}/>)}</section><nav className="pagination" aria-label="Marketplace pages"><button className="button secondary" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</button><span>Page {Math.min(page, pageCount)} of {pageCount} · {filtered.length} results</span><button className="button secondary" disabled={page >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>Next</button></nav></>
          : <EmptyState
              title="No escrows match these filters"
              description="Clear the search or choose a different lifecycle status."
              action={<button className="button secondary" onClick={() => { setQuery(""); setStatus("ALL"); setPage(1); }}>Clear filters</button>}
            />}
  </div>;
}
