"use client";

import { RefreshIcon } from "@/components/icons";
import { ContractsDashboard } from "@/components/contracts-dashboard";
import { ErrorState, LoadingState, PageHeader } from "@/components/ui";
import { useJobs } from "@/lib/hooks";

export default function ContractsPage() {
  const { data, error, loading, refresh } = useJobs();
  return <div className="page-container"><PageHeader eyebrow="Contract infrastructure" title="Transparent by construction" description="Inspect the frontend, trusted demo server boundary, shared registry, and every deployed escrow address." actions={<button className="button secondary" onClick={refresh} disabled={loading}><RefreshIcon/> Refresh registry</button>}/>{loading && !data ? <LoadingState label="Loading contract infrastructure…"/> : error && !data ? <ErrorState message={error.message} retry={refresh}/> : data ? <ContractsDashboard jobs={data.jobs}/> : null}</div>;
}
