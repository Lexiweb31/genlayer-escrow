"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { CloseIcon, ContractIcon, HomeIcon, JobsIcon, MenuIcon, MoonIcon, PlusIcon, ShieldIcon, SparkIcon, SunIcon, WalletIcon } from "@/components/icons";
import { DemoModeNotice } from "@/components/demo-mode-notice";

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
  const [marketingMenuOpen, setMarketingMenuOpen] = useState(false);

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

  if (pathname === "/") return <div className="marketing-shell">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <header className="marketing-header">
      <Link className="brand" href="/" aria-label="Merit home"><span className="brand-mark"><span/></span><span>merit</span></Link>
      <nav className="marketing-nav" aria-label="Marketing navigation"><a href="#product">Product</a><a href="#how-it-works">How it works</a><a href="#security">Security</a><Link href="/jobs">Explorer</Link><a href="https://github.com/Lexiweb31/genlayer-escrow" target="_blank" rel="noreferrer">GitHub</a></nav>
      <div className="marketing-actions"><div className="network-chip"><i/><span>Bradbury</span></div><button className="icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}>{theme === "light" ? <MoonIcon/> : <SunIcon/>}</button><Link className="button primary" href="/jobs">Launch App</Link><button className="marketing-menu-button" onClick={() => setMarketingMenuOpen((open) => !open)} aria-label={marketingMenuOpen ? "Close navigation" : "Open navigation"} aria-expanded={marketingMenuOpen}>{marketingMenuOpen ? <CloseIcon/> : <MenuIcon/>}</button></div>
      {marketingMenuOpen && <nav className="marketing-mobile-nav" aria-label="Mobile marketing navigation"><a href="#product" onClick={() => setMarketingMenuOpen(false)}>Product</a><a href="#how-it-works" onClick={() => setMarketingMenuOpen(false)}>How it works</a><a href="#security" onClick={() => setMarketingMenuOpen(false)}>Security</a><Link href="/jobs" onClick={() => setMarketingMenuOpen(false)}>Explorer</Link><a href="https://github.com/Lexiweb31/genlayer-escrow" target="_blank" rel="noreferrer">GitHub</a></nav>}
    </header>
    <main id="main-content" tabIndex={-1}>{children}</main>
  </div>;

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
      <div className="account-card"><ShieldIcon/><div><b>Demo account</b><span>Bradbury testnet</span></div><i/></div>
    </aside>

    <div className="app-column">
      <header className="topbar">
        <Link className="mobile-brand" href="/"><span className="brand-mark"><span/></span>merit</Link>
        <div className="mode-switch" aria-label="Account mode"><span className="active"><ShieldIcon size={13}/> Demo mode</span><button disabled title="Coming soon — connect a Bradbury wallet"><WalletIcon size={13}/> Wallet mode</button></div>
        <div className="network-chip"><i/><span>Bradbury</span></div>
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
