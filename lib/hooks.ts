"use client";

import { useCallback, useEffect, useState } from "react";
import { meritApi } from "@/lib/api";
import type { JobDetailResponse, JobsResponse } from "@/lib/types";

interface ResourceState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refresh: () => Promise<void>;
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
    if (!data || data.job.settlement?.transfer_status !== "PENDING_FINALIZATION") return;
    const timer = window.setInterval(refresh, 12_000);
    return () => window.clearInterval(timer);
  }, [data, refresh]);

  return { data, error, loading, refresh };
}
