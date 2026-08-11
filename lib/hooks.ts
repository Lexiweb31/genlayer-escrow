"use client";

import { useCallback, useEffect, useState } from "react";
import { useWalletMode } from "@/components/providers";
import { meritApi } from "@/lib/api";
import type { JobDetailResponse, JobRecord, JobsResponse, OwnedJobsResponse } from "@/lib/types";
import { signOwnedJobsAccess } from "@/lib/wallet-ownership";

export interface ResourceState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

interface OwnedJobsEventDetail {
  address: string;
  jobs: JobRecord[];
}

export const OWNED_UNFUNDED_JOBS_EVENT = "merit:owned-unfunded-jobs";

export function useOwnedUnfundedJobs(): ResourceState<OwnedJobsResponse> & { load(): Promise<void> } {
  const wallet = useWalletMode();
  const [data, setData] = useState<OwnedJobsResponse | null>(null);
  const [dataScope, setDataScope] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [errorScope, setErrorScope] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const scope = wallet.mode === "demo" ? "demo" : wallet.address ? `wallet:${wallet.address.toLowerCase()}` : null;

  const load = useCallback(async () => {
    if (!scope) {
      setError(new Error("Connect the client wallet to load jobs that still need funding."));
      setErrorScope(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = wallet.mode === "demo"
        ? await meritApi.ownedJobs({ address: "", message: "", signature: "", demo_mode: true })
        : await meritApi.ownedJobs(await signOwnedJobsAccess(wallet.address!));
      const owned = { jobs: response.jobs.filter((job) => job.status === "UNFUNDED") };
      setData(owned);
      setDataScope(scope);
      if (wallet.mode === "wallet" && wallet.address) {
        window.dispatchEvent(new CustomEvent<OwnedJobsEventDetail>(OWNED_UNFUNDED_JOBS_EVENT, {
          detail: { address: wallet.address, jobs: owned.jobs },
        }));
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError : new Error("Unable to load unpublished jobs."));
      setErrorScope(scope);
    } finally {
      setLoading(false);
    }
  }, [scope, wallet.address, wallet.mode]);

  useEffect(() => {
    if (wallet.mode !== "demo") return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, wallet.mode]);

  return {
    data: dataScope === scope ? data : null,
    error: errorScope === scope ? error : null,
    loading,
    refresh: load,
    load,
  };
}

export function useJobs(): ResourceState<JobsResponse> {
  const [data, setData] = useState<JobsResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading((current) => !data || current);
    setError(null);
    try {
      setData(await meritApi.jobs());
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError : new Error("Unable to load jobs."));
    } finally {
      setLoading(false);
    }
  }, [data]);

  useEffect(() => {
    const controller = new AbortController();
    meritApi.jobs(controller.signal).then(setData).catch((nextError: unknown) => {
      if ((nextError as Error).name !== "AbortError") {
        setError(nextError instanceof Error ? nextError : new Error("Unable to load jobs."));
      }
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const shouldReconcile = Boolean(data && (
      data.stats.degraded_jobs > 0
      || data.stats.settlement_pending > 0
      || data.jobs.some((job) => job.status === "UNKNOWN")
    ));
    if (!shouldReconcile) return;
    const timer = window.setInterval(refresh, 15_000);
    return () => window.clearInterval(timer);
  }, [data, refresh]);

  return { data, error, loading, refresh };
}

export function useJob(id: string): ResourceState<JobDetailResponse> {
  const [data, setData] = useState<JobDetailResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setData(await meritApi.job(id));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError : new Error("Unable to load this escrow."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    const controller = new AbortController();
    meritApi.job(id, controller.signal).then(setData).catch((nextError: unknown) => {
      if ((nextError as Error).name !== "AbortError") {
        setError(nextError instanceof Error ? nextError : new Error("Unable to load this escrow."));
      }
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [id]);

  useEffect(() => {
    if (!data) return;
    const transferStatus = String(data.job.settlement?.transfer_status || "");
    const shouldReconcile = data.job.status === "SETTLEMENT_PENDING"
      || transferStatus.startsWith("PENDING_")
      || data.job.status === "UNKNOWN";
    if (!shouldReconcile) return;
    const timer = window.setInterval(refresh, 12_000);
    return () => window.clearInterval(timer);
  }, [data, refresh]);

  return { data, error, loading, refresh };
}
