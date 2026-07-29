"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { ExternalLink, GitBranch, GitPullRequest } from "lucide-react";
import { PageHeader } from "@/components/app-shell/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { getPublication } from "@/lib/api/publications";
import { listTasks } from "@/lib/api/tasks";
import { formatDateTime, repositoryFullName } from "@/lib/formatters";
import { queryKeys } from "@/lib/query-client";
import type { PublicationResponse } from "@/types/api";

function hasPullRequest(
  publication: PublicationResponse | undefined,
): publication is PublicationResponse {
  return Boolean(publication?.pull_request_url);
}

export function GitHubView() {
  const tasksQuery = useQuery({
    queryKey: queryKeys.tasks,
    queryFn: ({ signal }) => listTasks(signal),
  });

  const publicationIds =
    tasksQuery.data?.tasks.flatMap((task) => (task.publication_id ? [task.publication_id] : [])) ?? [];

  const publicationQueries = useQueries({
    queries: publicationIds.map((publicationId) => ({
      queryKey: queryKeys.publication(publicationId),
      queryFn: ({ signal }: { signal: AbortSignal }) => getPublication(publicationId, signal),
      retry: false,
    })),
  });

  const publications = publicationQueries
    .map((query) => query.data)
    .filter(hasPullRequest);

  return (
    <>
      <PageHeader title="GitHub" subtitle="Pull Requests created by RepoPilot tasks" />
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-[#dae3ee]">
            <GitBranch className="h-5 w-5 text-[#acc7ff]" />
            GitHub Integrations & Pull Requests
          </h1>
          <p className="mt-1 text-xs text-[#c1c6d6]">Publication history is derived from real task/publication data.</p>
        </div>

        {tasksQuery.isLoading ? <LoadingState title="Loading publications" rows={5} /> : null}
        {tasksQuery.isError ? <ErrorState error={tasksQuery.error} onRetry={() => tasksQuery.refetch()} /> : null}

        {tasksQuery.isSuccess && publicationIds.length === 0 ? (
          <EmptyState title="No publication history" detail="Publication history is available through completed RepoPilot tasks." />
        ) : null}

        {publications.length > 0 ? (
          <section className="overflow-hidden rounded-lg border border-[#30363D] bg-[#161B22]">
            <div className="border-b border-[#30363D] p-4">
              <h2 className="text-sm font-bold text-[#dae3ee]">Pull Requests Created</h2>
            </div>
            <div className="divide-y divide-[#30363D] bg-[#0D1117] text-xs">
              {publications.map((publication) => {
                const task = tasksQuery.data?.tasks.find((item) => item.publication_id === publication.publication_id);
                const repository =
                  task ? repositoryFullName(task) : String(publication.repository.full_name ?? "repository unavailable");
                return (
                  <div key={publication.publication_id} className="flex items-center justify-between gap-4 p-4 hover:bg-[#161B22]">
                    <div className="flex min-w-0 items-start gap-3">
                      <GitPullRequest className="mt-0.5 h-4 w-4 shrink-0 text-[#8957e5]" />
                      <div className="min-w-0">
                        <div className="truncate font-semibold text-[#dae3ee]">
                          Pull Request Created {publication.pull_request_number ? `#${publication.pull_request_number}` : ""}
                        </div>
                        <div className="mt-0.5 text-[11px] text-[#8b909f]">
                          {repository} · {formatDateTime(publication.pr_created_at ?? publication.published_at)}
                        </div>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <StatusBadge status={publication.status} />
                      {publication.pull_request_url ? (
                        <a
                          href={publication.pull_request_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300"
                          title="Open Pull Request"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ) : null}
      </div>
    </>
  );
}
