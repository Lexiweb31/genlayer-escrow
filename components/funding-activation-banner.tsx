import Link from "next/link";
import type { FundingActivationView } from "@/lib/funding-activation";
import type { JobRecord } from "@/lib/types";
import { sameAddress } from "@/lib/wallet-client";

export type FundingViewerRole = "client" | "worker" | "visitor" | "entrant" | "demo";

export function fundingManageHref(address: string) {
  return `/jobs/${encodeURIComponent(address)}/manage#funding`;
}

export function shouldShowFundingBanner(job: Pick<JobRecord, "status" | "client" | "client_address">, viewerAddress?: string | null, isDemoClient = false) {
  return job.status === "UNFUNDED" && (isDemoClient || sameAddress(viewerAddress, job.client_address || job.client));
}

export function FundingActivationBanner({
  job,
  viewerAddress,
  role,
  state,
  onFund,
  href,
  isDemoClient = false,
}: {
  job: Pick<JobRecord, "address" | "status" | "client" | "client_address">;
  viewerAddress?: string | null;
  role: FundingViewerRole;
  state: FundingActivationView;
  onFund?: () => void | Promise<void>;
  href?: string;
  isDemoClient?: boolean;
}) {
  if ((role !== "client" && !isDemoClient) || !shouldShowFundingBanner(job, viewerAddress, isDemoClient)) return null;

  const action = state.canFund && (onFund || href)
    ? onFund
      ? <button type="button" className="button primary" onClick={() => void onFund()}>Fund and activate job</button>
      : <Link className="button primary" href={href!}>Fund and activate job</Link>
    : null;

  return <section className={`funding-activation-banner ${state.kind.toLowerCase()}`} aria-label="Funding activation" role="status">
    <div>
      <p className="card-kicker">Funding activation</p>
      <h2>Your job is created but not active yet</h2>
      <p>{state.detail}</p>
    </div>
    {action}
  </section>;
}
