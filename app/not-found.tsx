import Link from "next/link";
import { EmptyState } from "@/components/ui";

export default function NotFound() {
  return <div className="page-container"><EmptyState title="This Merit route does not exist" description="Return to the shared marketplace to choose a live escrow." action={<Link className="button primary" href="/jobs">Browse jobs</Link>}/></div>;
}
