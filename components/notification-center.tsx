"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BellIcon, CheckIcon, CloseIcon, RefreshIcon } from "@/components/icons";
import { useWalletMode } from "@/components/providers";
import { meritApi } from "@/lib/api";
import { jobRelevantToWallet, notificationForStatus, type MeritNotification } from "@/lib/notifications";
import type { JobRecord, JobStatus } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

const identityKey = (prefix: string, address: string) => `${prefix}:${address.toLowerCase()}`;
function readItems(key: string): MeritNotification[] { try { return JSON.parse(localStorage.getItem(key) || "[]") as MeritNotification[]; } catch { return []; } }
function readSnapshot(key: string): Record<string, JobStatus> { try { return JSON.parse(localStorage.getItem(key) || "{}") as Record<string, JobStatus>; } catch { return {}; } }

export function NotificationCenter() {
  const wallet = useWalletMode();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<MeritNotification[]>([]);
  const [registryError, setRegistryError] = useState(false);
  const viewer = wallet.mode === "wallet" ? wallet.address : null;
  const itemsKey = viewer ? identityKey("merit-notifications-v2", viewer) : null;
  const snapshotKey = viewer ? identityKey("merit-notification-snapshot-v2", viewer) : null;
  useEffect(() => { const timer = window.setTimeout(() => { setOpen(false); setRegistryError(false); setItems(itemsKey ? readItems(itemsKey) : []); }, 0); return () => window.clearTimeout(timer); }, [itemsKey]);
  const save = useCallback((next: MeritNotification[]) => { if (!itemsKey) return; const limited = next.slice(0, 30); setItems(limited); localStorage.setItem(itemsKey, JSON.stringify(limited)); }, [itemsKey]);
  const check = useCallback(async () => {
    if (!viewer || !snapshotKey || !itemsKey) return;
    try {
      const response = await meritApi.jobs(); const hasBaseline = localStorage.getItem(snapshotKey) !== null; const previous = readSnapshot(snapshotKey); const nextSnapshot: Record<string, JobStatus> = {}; const additions: MeritNotification[] = [];
      for (const job of response.jobs as JobRecord[]) { if (!jobRelevantToWallet(job, viewer)) continue; nextSnapshot[job.address] = job.status; if (!hasBaseline || previous[job.address] === job.status) continue; const item = notificationForStatus(job, job.status, new Date().toISOString(), viewer); if (item) additions.push(item); }
      localStorage.setItem(snapshotKey, JSON.stringify(nextSnapshot));
      if (additions.length) { const existing = readItems(itemsKey); const known = new Set(existing.map((item) => item.id)); save([...additions.filter((item) => !known.has(item.id)), ...existing]); }
      setRegistryError(false);
    } catch { setRegistryError(true); }
  }, [itemsKey, save, snapshotKey, viewer]);
  useEffect(() => { const initial = window.setTimeout(() => void check(), 0); const timer = window.setInterval(() => void check(), 30_000); const onVisibility = () => { if (document.visibilityState === "visible") void check(); }; document.addEventListener("visibilitychange", onVisibility); return () => { window.clearTimeout(initial); window.clearInterval(timer); document.removeEventListener("visibilitychange", onVisibility); }; }, [check]);
  const unread = useMemo(() => items.filter((item) => !item.read).length + (registryError ? 1 : 0), [items, registryError]);
  const markAllRead = () => save(items.map((item) => ({ ...item, read: true })));
  const toggle = () => { const next = !open; setOpen(next); if (next) markAllRead(); };
  if (!viewer) return null;
  return <div className="notification-center"><button className="icon-button notification-trigger" onClick={toggle} aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} aria-expanded={open}><BellIcon/>{unread > 0 && <span>{unread > 9 ? "9+" : unread}</span>}</button>{open && <section className="notification-popover" aria-label="Notifications"><header><div><b>Notifications</b><small>Job and payment activity</small></div><button className="notification-close" onClick={() => setOpen(false)} aria-label="Close notifications"><CloseIcon size={15}/></button></header>{registryError && <article className="notification-item danger"><span><RefreshIcon/></span><div><b>Marketplace connection lost</b><p>Live job updates are temporarily unavailable. Merit will retry automatically.</p><small>Connection status</small></div></article>}<div className="notification-list">{items.length ? items.map((item) => <Link key={item.id} href={item.jobAddress ? `/jobs/${encodeURIComponent(item.jobAddress)}` : "/jobs"} className={`notification-item ${item.tone} ${item.read ? "read" : ""}`} onClick={() => setOpen(false)}><span><CheckIcon/></span><div><b>{item.title}</b><p>{item.message}</p><small>{relativeTime(item.createdAt)}</small></div></Link>) : !registryError && <div className="notification-empty"><BellIcon/><b>You’re all caught up</b><p>Job acceptance, submissions, evaluations and payments will appear here.</p></div>}</div>{items.length > 0 && <footer><button onClick={() => save([])}>Clear notifications</button><button onClick={markAllRead}>Mark all read</button></footer>}</section>}</div>;
}
