"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Github, LogOut, Settings } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { getCurrentUser, getGitHubSetupUrl, listInstallations, logout } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-client";
import { PageHeader } from "@/components/app-shell/page-header";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { StatusBadge } from "@/components/shared/status-badge";

export function SettingsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const githubNotice =
    searchParams.get("github") === "connected"
      ? "GitHub repository access is connected and synchronized."
      : searchParams.get("github") === "approval-required"
        ? "Organization approval required. Ask a GitHub organization owner to approve RepoPilot."
        : null;
  const userQuery = useQuery({
    queryKey: queryKeys.currentUser,
    queryFn: ({ signal }) => getCurrentUser(signal),
  });
  const installationsQuery = useQuery({
    queryKey: queryKeys.installations,
    queryFn: ({ signal }) => listInstallations(signal),
  });
  const setupMutation = useMutation({
    mutationFn: getGitHubSetupUrl,
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      queryClient.clear();
      router.replace("/login");
    },
  });

  return (
    <>
      <PageHeader title="Settings" subtitle="Account and GitHub repository access" />
      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-bold text-[#dae3ee]">
              <Settings className="h-5 w-5 text-[#acc7ff]" />
              GitHub
            </h1>
            <p className="mt-1 text-xs text-[#c1c6d6]">
              OAuth identifies your account. GitHub App installations control repository access.
            </p>
          </div>

          {githubNotice ? (
            <div
              role="status"
              className="rounded-lg border border-blue-400/30 bg-blue-500/10 px-4 py-3 text-sm text-blue-100"
            >
              {githubNotice}
            </div>
          ) : null}

          {userQuery.isPending || installationsQuery.isPending ? (
            <LoadingState title="Loading GitHub settings" rows={4} />
          ) : null}
          {userQuery.isError ? <ErrorState error={userQuery.error} onRetry={() => userQuery.refetch()} /> : null}
          {installationsQuery.isError ? <ErrorState error={installationsQuery.error} onRetry={() => installationsQuery.refetch()} /> : null}

          {userQuery.data ? (
            <section className="rounded-lg border border-[#30363D] bg-[#161B22] p-5">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Connected account</h2>
              <div className="mt-4 flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-zinc-100">
                    {userQuery.data.github_name || userQuery.data.github_login}
                  </p>
                  <p className="mt-1 font-code text-xs text-zinc-500">@{userQuery.data.github_login}</p>
                </div>
                <StatusBadge status="connected" />
              </div>
            </section>
          ) : null}

          {installationsQuery.data ? (
            <section className="overflow-hidden rounded-lg border border-[#30363D] bg-[#161B22]">
              <div className="flex items-center justify-between border-b border-[#30363D] p-5">
                <div>
                  <h2 className="text-sm font-semibold text-zinc-100">RepoPilot installations</h2>
                  <p className="mt-1 text-xs text-zinc-500">Tokens are minted server-side only when needed.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setupMutation.mutate()}
                  disabled={setupMutation.isPending}
                  className="rounded-md border border-[#30363D] bg-[#21262D] px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-[#30363D] disabled:opacity-50"
                >
                  Configure Access
                </button>
              </div>
              {installationsQuery.data.installations.map((installation) => (
                <div key={installation.id} className="flex items-center justify-between border-b border-[#30363D] px-5 py-4 last:border-0">
                  <div className="flex items-center gap-3">
                    <Github className="h-4 w-4 text-zinc-500" />
                    <div>
                      <p className="text-sm text-zinc-100">{installation.account_login}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {installation.account_type} · {installation.repository_count} repositories · {installation.repository_selection}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={installation.status} />
                </div>
              ))}
              {installationsQuery.data.installations.length === 0 ? (
                <p className="p-6 text-center text-sm text-zinc-500">No GitHub App installation is connected.</p>
              ) : null}
            </section>
          ) : null}

          {setupMutation.isError ? <ErrorState error={setupMutation.error} /> : null}
          {logoutMutation.isError ? <ErrorState error={logoutMutation.error} /> : null}

          <section className="flex items-center justify-between rounded-lg border border-[#30363D] bg-[#161B22] p-5">
            <div>
              <h2 className="text-sm font-semibold text-zinc-100">Account</h2>
              <p className="mt-1 text-xs text-zinc-500">Revoke this browser session.</p>
            </div>
            <button
              type="button"
              onClick={() => logoutMutation.mutate()}
              disabled={logoutMutation.isPending}
              className="flex items-center gap-2 rounded-md border border-red-400/30 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-500/10 disabled:opacity-50"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign Out
            </button>
          </section>
        </div>
      </div>
    </>
  );
}
