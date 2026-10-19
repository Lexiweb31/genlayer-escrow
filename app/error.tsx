"use client";

import { ErrorState } from "@/components/ui";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="page-container"><ErrorState message={error.message || "The page encountered an unexpected error."} retry={reset}/></div>;
}
