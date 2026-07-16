import Link from "next/link";
import { ContractIcon, ExternalIcon, ShieldIcon } from "@/components/icons";
import { MonoValue, StatusPill } from "@/components/ui";
import type { ContractAddresses, JobRecord } from "@/lib/types";
import { addressUrl, shortAddress, txUrl } from "@/lib/utils";

export function ContractsDashboard({ jobs, addresses }: { jobs: JobRecord[]; addresses?: ContractAddresses }) {
  return <div className="contracts-stack">
    <section className="infrastructure-grid">
      <article className="panel infrastructure-card"><span className="feature-icon"><ContractIcon/></span><div><p className="card-kicker">Contract layer</p><h2>Freelance escrow</h2><p>Immutable roles, thresholds, evaluator calls, and safe external-message settlement.</p></div><StatusPill tone="success">Safe EOA transfer v2</StatusPill></article>
      <article className="panel infrastructure-card"><span className="feature-icon"><ShieldIcon/></span><div><p className="card-kicker">Trusted demo server</p><h2>Render API</h2><p>Owns separate testnet-only signers, preflight role checks, and the durable marketplace registry.</p></div><StatusPill tone="warning">Server-signed demo</StatusPill></article>
      <article className="panel infrastructure-card"><span className="feature-icon"><ContractIcon/></span><div><p className="card-kicker">Persistence</p><h2>SQLite registry</h2><p>Shared job metadata and settlement evidence survive restarts on a configured Render disk.</p></div><StatusPill tone="success">Durable store</StatusPill></article>
    </section>
    {addresses && <section className="panel address-panel"><div className="panel-heading"><div><p className="card-kicker">Selected escrow infrastructure</p><h2>Deployed addresses</h2></div></div><div className="address-list">{[
      ["Escrow contract", addresses.escrow, addresses.explorer_escrow || addressUrl(addresses.escrow)],
      ["AI evaluator", addresses.evaluator, addresses.explorer_evaluator || addressUrl(addresses.evaluator)],
      ["Bradbury demo client", addresses.demo_client, addressUrl(addresses.demo_client)],
      ["Bradbury demo worker", addresses.demo_worker, addressUrl(addresses.demo_worker)],
    ].map(([label, value, url]) => value && <div key={label}><span>{label}</span><MonoValue title={value}>{value}</MonoValue>{url && <a href={url} target="_blank" rel="noreferrer" aria-label={`Open ${label} in explorer`}><ExternalIcon/></a>}</div>)}</div></section>}
    <section className="panel registry-table"><div className="panel-heading"><div><p className="card-kicker">Deployment registry</p><h2>Escrow contracts</h2></div><StatusPill>{jobs.length} records</StatusPill></div>{jobs.length ? <div className="table-scroll"><table><thead><tr><th>Contract</th><th>Title</th><th>State</th><th>Deployment</th><th/></tr></thead><tbody>{jobs.map((job) => <tr key={job.address}><td><MonoValue title={job.address}>{shortAddress(job.address, 9, 6)}</MonoValue></td><td>{job.title || "Untitled escrow"}</td><td><StatusPill tone={job.legacy_contract ? "danger" : job.status === "SETTLEMENT_PENDING" ? "warning" : "neutral"}>{job.status}</StatusPill></td><td>{job.deployment_tx ? <a href={txUrl(job.deployment_tx) || "#"} target="_blank" rel="noreferrer"><MonoValue>{shortAddress(job.deployment_tx, 8, 6)}</MonoValue> <ExternalIcon size={13}/></a> : "—"}</td><td><Link className="text-link" href={`/jobs/${encodeURIComponent(job.address)}/contracts`}>Inspect →</Link></td></tr>)}</tbody></table></div> : <p className="muted">No contract records are available.</p>}</section>
  </div>;
}
