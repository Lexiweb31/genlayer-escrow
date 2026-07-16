"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { meritApi } from "@/lib/api";
import type { DemoConfig } from "@/lib/types";

interface DemoContextValue {
  demo: DemoConfig | null;
  loading: boolean;
  error: Error | null;
}

const DemoContext = createContext<DemoContextValue>({ demo: null, loading: true, error: null });

export function Providers({ children }: { children: React.ReactNode }) {
  const [demo, setDemo] = useState<DemoConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    meritApi.demoMode(controller.signal).then(setDemo).catch((nextError: unknown) => {
      if ((nextError as Error).name !== "AbortError") {
        setError(nextError instanceof Error ? nextError : new Error("Demo configuration unavailable."));
      }
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const value = useMemo(() => ({ demo, loading, error }), [demo, loading, error]);
  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemoMode() {
  return useContext(DemoContext);
}
