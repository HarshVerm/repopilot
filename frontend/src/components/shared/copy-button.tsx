"use client";

// Module purpose: Render and coordinate the copy button interface.

import { Check, Copy } from "lucide-react";
import { useState } from "react";

/** Purpose: Render the copy button interface. */
export function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  /** Purpose: Copy module state for this frontend workflow. */
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setFailed(false);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setFailed(true);
      window.setTimeout(() => setFailed(false), 1800);
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-lg border border-[#3F3F46] bg-[#27272A] px-2.5 py-1.5 text-[11px] font-semibold text-zinc-300 hover:text-white"
      title={label}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      <span>{failed ? "Unavailable" : copied ? "Copied" : label}</span>
    </button>
  );
}
