"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ContractIcon, HomeIcon, JobsIcon, MoonIcon, PlusIcon, ShieldIcon, SparkIcon, SunIcon } from "@/components/icons";
import { DemoModeNotice } from "@/components/demo-mode-notice";
import { config } from "@/lib/config";

const navigation = [
  { href: "/", label: "Home", icon: HomeIcon, exact: true },
  { href: "/jobs", label: "Browse jobs", icon: JobsIcon },
  { href: "/jobs/new", label: "Post a job", icon: PlusIcon },
  { href: "/contracts", label: "Contracts", icon: ContractIcon },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [judgeOpen, setJudgeOpen] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("merit-theme");
    const next = saved === "light" || saved === "dark"
      ? saved
      : window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    queueMicrotask(() => setTheme(next));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        setJudgeOpen(true);
      }
      if (event.key === "Escape") setJudgeOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    localStorage.setItem("merit-theme", next);
  };

  const active = (href: string, exact?: boolean) => exact ? pathname === href : pathname.startsWith(href);

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <aside className="sidebar">
      <Link className="brand" href="/" aria-label="Merit home"><span className="brand-mark"><span/></span><span>merit</span></Link>
      <p className="sidebar-kicker">Intelligent escrow</p>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        {navigation.map((item) => <Link key={item.href} href={item.href} className={active(item.href, item.exact) ? "active" : ""}><item.icon/><span>{item.label}</span></Link>)}
      </nav>
      <div className="sidebar-spacer"/>
      <button className="judge-button" onClick={() => setJudgeOpen(true)}><SparkIcon/><span><b>Judge mode</b><small>Presentation overview</small></span><kbd>⌘J</kbd></button>
      <div className="account-card"><ShieldIcon/><div><b>Demo account</b><span>{config.network}</span></div><i/></div>
    </aside>

    <div className="app-column">
      <header className="topbar">
        <Link className="mobile-brand" href="/"><span className="brand-mark"><span/></span>merit</Link>
        <div className="network-chip"><i/><span>{config.network.replace("testnet_", "")}</span></div>
        <button className="icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`} title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}>
          {theme === "light" ? <MoonIcon/> : <SunIcon/>}
        </button>
      </header>
      <div className="notice-wrap"><DemoModeNotice compact={pathname === "/"}/></div>
      <main id="main-content" tabIndex={-1}>{children}</main>
    </div>

    <nav className="bottom-nav" aria-label="Mobile navigation">
      {navigation.map((item) => <Link key={item.href} href={item.href} className={active(item.href, item.exact) ? "active" : ""}><item.icon/><span>{item.label.replace(" jobs", "")}</span></Link>)}
    </nav>

    {judgeOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setJudgeOpen(false); }}>
      <section className="judge-modal" role="dialog" aria-modal="true" aria-labelledby="judge-title">
        <button className="modal-close" onClick={() => setJudgeOpen(false)} aria-label="Close judge mode">×</button>
        <p className="eyebrow">Competition walkthrough</p>
        <h2 id="judge-title">Merit proves every settlement step.</h2>
        <p>Follow a public agreement from server-signed demo funding through validator evaluation to an inspectable outbound transfer.</p>
        <div className="judge-grid">
          <article><span>01</span><b>Agreement</b><p>Plain-English work is bound to an immutable escrow specification.</p></article>
          <article><span>02</span><b>Evidence</b><p>A public submission gives validators observable work to inspect.</p></article>
          <article><span>03</span><b>Decision</b><p>The contract records accepted, partial, or refunded without overstating transfer completion.</p></article>
          <article><span>04</span><b>Settlement proof</b><p>Recipient, exact GEN amount, status, and explorer reference remain visible.</p></article>
        </div>
        <div className="judge-actions"><Link className="button primary" href="/jobs" onClick={() => setJudgeOpen(false)}>Open live marketplace</Link><Link className="button secondary" href="/jobs/new" onClick={() => setJudgeOpen(false)}>Create demo escrow</Link></div>
      </section>
    </div>}
  </div>;
}
