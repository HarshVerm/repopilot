import { ExternalLink, GitPullRequest } from "lucide-react";
import type { PublicationResponse } from "@/types/api";
import { CopyButton } from "@/components/shared/copy-button";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatDateTime, shortSha } from "@/lib/formatters";

export function PublicationResult({ publication }: { publication: PublicationResponse | null | undefined }) {
  if (!publication) {
    return (
      <div className="rounded-xl border border-[#27272A] bg-[#0D1117] p-4 text-xs text-zinc-400">
        No publication yet.
      </div>
    );
  }

  return (
    <section className="rounded-xl border border-[#27272A] bg-[#141c24] p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-sm font-bold text-[#dae3ee]">
            <GitPullRequest className="h-4 w-4 text-violet-400" />
            {publication.status === "published" ? "Pull Request Created" : "Publication"}
          </h2>
          <div className="mt-2 flex flex-wrap gap-2">
            <StatusBadge status={publication.status} />
            {publication.error_message ? (
              <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-rose-300">
                Partial Failure
              </span>
            ) : null}
          </div>
        </div>
        {publication.pull_request_url ? (
          <a
            href={publication.pull_request_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open Pull Request
          </a>
        ) : null}
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
        <Pair label="PR Number" value={publication.pull_request_number ? `#${publication.pull_request_number}` : "—"} />
        <Pair label="Branch" value={publication.head_branch ?? "—"} />
        <Pair label="Commit" value={shortSha(publication.commit_sha)} />
        <Pair label="Base Branch" value={publication.base_branch ?? "—"} />
        <Pair label="Published" value={formatDateTime(publication.published_at ?? publication.pr_created_at)} />
        <Pair label="Retries" value={String(publication.retry_count)} />
      </dl>

      {publication.pull_request_url ? (
        <div className="mt-4">
          <CopyButton value={publication.pull_request_url} label="Copy PR URL" />
        </div>
      ) : null}

      {publication.error_message ? (
        <div className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-100">
          {publication.error_message}
        </div>
      ) : null}
    </section>
  );
}

function Pair({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-code text-[11px] text-zinc-500">{label}</dt>
      <dd className="mt-1 truncate font-code text-xs font-semibold text-[#dae3ee]" title={value}>
        {value}
      </dd>
    </div>
  );
}
