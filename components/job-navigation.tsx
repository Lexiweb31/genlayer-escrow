"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function JobNavigation({ id }: { id: string }) {
  const pathname = usePathname();
  const encoded = encodeURIComponent(id);
  const items = [
    { href: `/jobs/${encoded}`, label: "Overview" },
    { href: `/jobs/${encoded}/manage`, label: "Manage job" },
    { href: `/jobs/${encoded}/evaluation`, label: "AI Evaluation" },
    { href: `/jobs/${encoded}/contracts`, label: "Contracts" },
  ];
  return <nav className="job-tabs" aria-label="Job navigation">{items.map((item) => <Link key={item.href} className={pathname === item.href ? "active" : ""} href={item.href}>{item.label}</Link>)}</nav>;
}
