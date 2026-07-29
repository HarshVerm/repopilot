"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Archive, Github, Lock, Search } from "lucide-react";
import { useState } from "react";
import { getGitHubSetupUrl } from "@/lib/api/auth";
import { listConnectedRepositories } from "@/lib/api/github";
import { queryKeys } from "@/lib/query-client";
import { PageHeader } from "@/components/app-shell/page-header";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";

export function RepositoriesView() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const repositoriesQuery = useQuery({
    queryKey: queryKeys.repositories(search, page),
    queryFn: ({ signal }) =>
      listConnectedRepositories(
        {
          search,
          page,
          perPage: 30,
          includeArchived: true,
          refresh: search === "" && page === 1,
        },
        signal,
      ),
    refetchOnMount: "always",
  });
  const setupMutation = useMutation({
    mutationFn: getGitHubSetupUrl,
    onSuccess: ({ url }) => window.location.assign(url),
  });

  return (
    <>
      <PageHeader
        title="Repositories"
        subtitle="GitHub App repositories available to RepoPilot"
      />
      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-5xl">
          <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row">
            <label className="relative max-w-md flex-1">
              <span className="sr-only">Search repositories</span>
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                placeholder="Search repositories..."
                className="w-full rounded-md border border-[#30363D] bg-[#0D1117] py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-400"
              />
            </label>
            <button
              type="button"
              onClick={() => setupMutation.mutate()}
              disabled={setupMutation.isPending}
              className="rounded-md border border-[#30363D] bg-[#21262D] px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-[#30363D] disabled:opacity-50"
            >
              Manage GitHub Access
            </button>
          </div>

          {repositoriesQuery.isPending ? <LoadingState title="Loading repositories" rows={6} /> : null}
          {repositoriesQuery.isError ? (
            <ErrorState error={repositoriesQuery.error} onRetry={() => repositoriesQuery.refetch()} />
          ) : null}
          {setupMutation.isError ? <ErrorState error={setupMutation.error} /> : null}

          {repositoriesQuery.data ? (
            <div className="overflow-hidden rounded-lg border border-[#30363D] bg-[#161B22]">
              {repositoriesQuery.data.repositories.map((repository) => (
                <div
                  key={repository.id}
                  className="flex items-center justify-between border-b border-[#30363D] px-4 py-3 last:border-0"
                >
                  <div className="min-w-0">
                    <p className="truncate font-code text-sm text-zinc-100">{repository.full_name}</p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {repository.private ? "Private" : "Public"} · {repository.default_branch} ·{" "}
                      {repository.access_status === "active" ? "Connected" : "Access removed"}
                    </p>
                  </div>
                  <div className="ml-4 flex items-center gap-2 text-zinc-500">
                    {repository.archived ? <Archive className="h-4 w-4" aria-label="Archived" /> : null}
                    {repository.private ? <Lock className="h-4 w-4" aria-label="Private" /> : <Github className="h-4 w-4" />}
                  </div>
                </div>
              ))}
              {repositoriesQuery.data.repositories.length === 0 ? (
                <div className="p-10 text-center">
                  <p className="text-sm font-medium text-zinc-200">No repositories connected</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {search
                      ? "No repositories match the current search."
                      : "Repository access refreshes automatically. Manage GitHub access only to grant the app its first repository."}
                  </p>
                </div>
              ) : null}
              <div className="flex items-center justify-between border-t border-[#30363D] px-4 py-3">
                <button type="button" disabled={page === 1} onClick={() => setPage(page - 1)} className="text-xs text-zinc-400 disabled:opacity-30">Previous</button>
                <span className="font-code text-[11px] text-zinc-600">
                  {repositoriesQuery.data.total} repositories · page {page}
                </span>
                <button type="button" disabled={!repositoriesQuery.data.has_next} onClick={() => setPage(page + 1)} className="text-xs text-zinc-400 disabled:opacity-30">Next</button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
