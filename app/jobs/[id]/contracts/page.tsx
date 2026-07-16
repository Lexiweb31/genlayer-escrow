"use client";

import { useParams } from "next/navigation";
import { ContractsDashboard } from "@/components/contracts-dashboard";
import { JobNavigation } from "@/components/job-navigation";
import { ErrorState, LoadingState, PageHeader } from "@/components/ui";
import { useJob } from "@/lib/hooks";
import type { JobRecord } from "@/lib/types";

export default function JobContractsPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const { data, error, loading, refresh } = useJob(id);
  if (loading && !data) return <div className="page-container"><JobNavigation id={id}/><LoadingState label="Loading deployed contract addresses…"/></div>;
  if (error && !data) return <div className="page-container"><JobNavigation id={id}/><ErrorState message={error.message} retry={refresh}/></div>;
  if (!data) return null;
  const job: JobRecord = { ...data.meta, ...data.job, address: data.meta.address || data.job.address, status: data.job.status };
  return <div className="page-container"><JobNavigation id={id}/><PageHeader eyebrow="Job infrastructure" title="Contract dashboard" description="Every address is public. Demo signing remains on Render; no private signer configuration is sent to this page."/><ContractsDashboard jobs={[job]} addresses={data.addresses}/></div>;
}
