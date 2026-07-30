"use client";

// Module purpose: Render and coordinate the confirmation dialog interface.

import { X } from "lucide-react";
import { useEffect, useRef } from "react";

/** Purpose: Render the confirmation dialog interface. */
export function ConfirmationDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  variant = "primary",
  pending = false,
  error,
  reason,
  reasonLabel = "Reason",
  reasonPlaceholder = "Optional reason",
  reasonRequired = false,
  onReasonChange,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  variant?: "primary" | "danger";
  pending?: boolean;
  error?: string;
  reason?: string;
  reasonLabel?: string;
  reasonPlaceholder?: string;
  reasonRequired?: boolean;
  onReasonChange?: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const reasonIsMissing = reasonRequired && !(reason ?? "").trim();

  useEffect(() => {
    if (open) {
      if (onReasonChange) {
        reasonRef.current?.focus();
      } else {
        confirmRef.current?.focus();
      }
    }
  }, [onReasonChange, open]);

  useEffect(() => {
    if (!open) return;
    /** Purpose: Handle on key down for this frontend module. */
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !pending) {
        onCancel();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCancel, open, pending]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 p-4" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="w-full max-w-md rounded-xl border border-[#27272A] bg-[#18181B] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#27272A] px-5 py-4">
          <h2 id="confirm-title" className="text-sm font-bold text-[#FAFAFA]">
            {title}
          </h2>
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-[#27272A] hover:text-white disabled:opacity-50"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">
          <p className="text-sm leading-relaxed text-zinc-300">{description}</p>
          {error ? (
            <p
              role="alert"
              className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300"
            >
              {error}
            </p>
          ) : null}
          {onReasonChange ? (
            <label className="block text-xs font-medium text-zinc-300">
              {reasonLabel}
              {reasonRequired ? (
                <span className="ml-1 text-rose-300" aria-hidden="true">
                  *
                </span>
              ) : null}
              <textarea
                ref={reasonRef}
                value={reason}
                onChange={(event) => onReasonChange(event.target.value)}
                rows={4}
                required={reasonRequired}
                aria-required={reasonRequired}
                className="mt-2 w-full rounded-lg border border-[#3F3F46] bg-[#0D1117] p-3 text-xs text-[#FAFAFA] placeholder:text-zinc-500"
                placeholder={reasonPlaceholder}
              />
            </label>
          ) : null}
        </div>
        <div className="flex justify-end gap-3 border-t border-[#27272A] px-5 py-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={pending}
            className="rounded-lg border border-[#3F3F46] bg-[#27272A] px-4 py-2 text-xs font-semibold text-zinc-200 hover:bg-[#3F3F46] disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            ref={confirmRef}
            onClick={onConfirm}
            disabled={pending || reasonIsMissing}
            className={`rounded-lg px-4 py-2 text-xs font-bold text-white disabled:opacity-50 ${
              variant === "danger"
                ? "bg-rose-600 hover:bg-rose-500"
                : "bg-blue-600 hover:bg-blue-500"
            }`}
          >
            {pending ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
