"use client";

import { useState } from "react";
import { CheckIcon, CopyIcon } from "@/components/icons";

export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2400);
    } catch {
      setCopied(false);
    }
  };
  return <button className="copy-button" type="button" onClick={copy} aria-label={`Copy ${label}`} title={`Copy ${label}`}>{copied ? <CheckIcon/> : <CopyIcon/>}<span className="sr-only" aria-live="polite">{copied ? `${label} copied` : ""}</span></button>;
}
