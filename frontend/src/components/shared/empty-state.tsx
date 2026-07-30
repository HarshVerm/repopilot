// Module purpose: Render and coordinate the empty state interface.

import { Inbox } from "lucide-react";

/** Purpose: Render the empty state interface. */
export function EmptyState({
  title,
  detail,
}: {
  title: string;
  detail?: string;
}) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-xl border border-dashed border-[#3F3F46] bg-[#0D1117] p-8 text-center">
      <Inbox className="mb-3 h-7 w-7 text-zinc-500" />
      <h2 className="text-sm font-semibold text-[#FAFAFA]">{title}</h2>
      {detail ? <p className="mt-1 max-w-md text-xs text-zinc-400">{detail}</p> : null}
    </div>
  );
}
