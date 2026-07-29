"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  Github,
  Loader2,
  Lock,
  Search,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getGitHubSetupUrl, listInstallations } from "@/lib/api/auth";
import {
  getConnectedRepositoryIssue,
  listConnectedRepositories,
  listConnectedRepositoryIssues,
} from "@/lib/api/github";
import { createTask } from "@/lib/api/tasks";
import { queryKeys } from "@/lib/query-client";
import { ErrorState } from "@/components/shared/error-state";

function useDebouncedValue(value: string, delayMs: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(handle);
  }, [delayMs, value]);
  return debounced;
}

export function CreateTaskModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [repositorySearch, setRepositorySearch] = useState("");
  const [issueSearch, setIssueSearch] = useState("");
  const [repositoryPage, setRepositoryPage] = useState(1);
  const [issuePage, setIssuePage] = useState(1);
  const [repositoryId, setRepositoryId] = useState<string | null>(null);
  const [issueNumber, setIssueNumber] = useState<number | null>(null);
  const [instructions, setInstructions] = useState("");
  const debouncedRepositorySearch = useDebouncedValue(repositorySearch, 300);
  const debouncedIssueSearch = useDebouncedValue(issueSearch, 300);

  const installationsQuery = useQuery({
    queryKey: queryKeys.installations,
    queryFn: ({ signal }) => listInstallations(signal),
    enabled: open,
    retry: false,
  });
  const repositoriesQuery = useQuery({
    queryKey: queryKeys.repositories(debouncedRepositorySearch, repositoryPage),
    queryFn: ({ signal }) =>
      listConnectedRepositories(
        {
          search: debouncedRepositorySearch,
          page: repositoryPage,
          perPage: 20,
          includeArchived: true,
          refresh: debouncedRepositorySearch === "" && repositoryPage === 1,
        },
        signal,
      ),
    enabled: open && step === 1,
    retry: false,
    refetchOnMount: "always",
  });
  const issuesQuery = useQuery({
    queryKey: repositoryId
      ? queryKeys.connectedIssues(repositoryId, debouncedIssueSearch, issuePage)
      : ["github", "repository", "none", "issues"],
    queryFn: ({ signal }) =>
      listConnectedRepositoryIssues(
        repositoryId!,
        { search: debouncedIssueSearch, page: issuePage, perPage: 30 },
        signal,
      ),
    enabled: open && step >= 2 && Boolean(repositoryId),
    retry: false,
  });
  const issueQuery = useQuery({
    queryKey:
      repositoryId && issueNumber
        ? ["github", "repository", repositoryId, "issue", issueNumber]
        : ["github", "repository", "none", "issue"],
    queryFn: ({ signal }) =>
      getConnectedRepositoryIssue(repositoryId!, issueNumber!, signal),
    enabled: open && step >= 3 && Boolean(repositoryId && issueNumber),
    retry: false,
  });

  const selectedRepository = repositoriesQuery.data?.repositories.find(
    (repository) => repository.id === repositoryId,
  );
  const summary = useMemo(
    () => (issueQuery.data ? issueUnderstanding(issueQuery.data.title, issueQuery.data.body) : null),
    [issueQuery.data],
  );

  const createMutation = useMutation({
    mutationFn: () => {
      if (!repositoryId || !issueNumber) {
        throw new Error("Select a repository and issue first.");
      }
      return createTask({
        repository_id: repositoryId,
        issue_number: issueNumber,
        user_instructions: instructions.trim() || undefined,
      });
    },
    onSuccess: async (task) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.tasks });
      onClose();
      router.push(`/tasks/${task.task_id}`);
    },
  });

  const setupMutation = useMutation({
    mutationFn: getGitHubSetupUrl,
    onSuccess: ({ url }) => {
      window.location.assign(url);
    },
  });

  if (!open) return null;

  const noInstallations =
    installationsQuery.isSuccess &&
    installationsQuery.data.installations.filter((item) => item.status === "active").length === 0;
  const canContinue =
    (step === 1 && Boolean(repositoryId) && !selectedRepository?.archived) ||
    (step === 2 && Boolean(issueNumber)) ||
    step === 3;

  return (
    <div className="fixed inset-y-0 right-0 left-16 z-[70] flex min-h-screen flex-col overflow-hidden bg-[#0D1117] text-[#dae3ee] lg:left-64">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#30363D] px-5">
        <div>
          <span className="text-sm font-semibold text-white">Create Task</span>
          <span className="ml-3 text-xs text-zinc-500">GitHub issue workflow</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          disabled={createMutation.isPending}
          aria-label="Close create task"
          className="rounded-md p-2 text-zinc-400 hover:bg-[#21262D] hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="flex min-h-0 flex-1 justify-center overflow-y-auto px-5 py-8">
        <div className="w-full max-w-3xl">
          <ol className="mb-8 grid grid-cols-4 gap-2" aria-label="Task creation progress">
            {["Repository", "Issue", "Understanding", "Instructions"].map((label, index) => {
              const number = index + 1;
              return (
                <li
                  key={label}
                  className={`border-t-2 pt-2 text-xs ${
                    number <= step ? "border-blue-400 text-zinc-200" : "border-[#30363D] text-zinc-600"
                  }`}
                >
                  <span className="font-code">{number}.</span> {label}
                </li>
              );
            })}
          </ol>

          {installationsQuery.isError ? (
            <ErrorState error={installationsQuery.error} onRetry={() => installationsQuery.refetch()} />
          ) : noInstallations ? (
            <section className="rounded-lg border border-[#30363D] bg-[#161B22] p-8 text-center">
              <Github className="mx-auto h-6 w-6 text-zinc-400" />
              <h1 className="mt-4 text-base font-semibold text-white">No repositories connected</h1>
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-zinc-400">
                Install or configure the RepoPilot GitHub App, then choose the repositories it may access.
              </p>
              <button
                type="button"
                onClick={() => setupMutation.mutate()}
                disabled={setupMutation.isPending}
                className="mt-5 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {setupMutation.isPending ? "Opening GitHub..." : "Configure GitHub Access"}
              </button>
              {setupMutation.isError ? <div className="mt-4"><ErrorState error={setupMutation.error} /></div> : null}
            </section>
          ) : (
            <section className="rounded-lg border border-[#30363D] bg-[#161B22]">
              <div className="border-b border-[#30363D] p-5">
                <h1 className="text-base font-semibold text-white">
                  {step === 1 && "Select a repository"}
                  {step === 2 && "Select an open issue"}
                  {step === 3 && "Review RepoPilot's understanding"}
                  {step === 4 && "Add optional instructions"}
                </h1>
                <p className="mt-1 text-xs text-zinc-400">
                  {step === 1 && "Only repositories authorized through your GitHub App installations are shown."}
                  {step === 2 && "Pull requests are excluded from this list."}
                  {step === 3 && "The raw GitHub issue remains the source snapshot for the task."}
                  {step === 4 && "Instructions cannot override repository scope or security policy."}
                </p>
              </div>

              <div className="p-5">
                {step === 1 ? (
                  <Selector
                    search={repositorySearch}
                    onSearch={(value) => {
                      setRepositorySearch(value);
                      setRepositoryPage(1);
                    }}
                    placeholder="Search repositories..."
                  >
                    {repositoriesQuery.isFetching ? <LoadingRows /> : null}
                    {repositoriesQuery.isError ? (
                      <ErrorState error={repositoriesQuery.error} onRetry={() => repositoriesQuery.refetch()} />
                    ) : null}
                    {repositoriesQuery.data?.repositories.map((repository) => (
                      <button
                        type="button"
                        key={repository.id}
                        onClick={() => setRepositoryId(repository.id)}
                        className={`flex w-full items-center justify-between border-b border-[#21262D] px-3 py-3 text-left last:border-0 ${
                          repositoryId === repository.id ? "bg-blue-500/10" : "hover:bg-[#21262D]"
                        }`}
                      >
                        <span>
                          <span className="block font-code text-sm text-zinc-100">{repository.full_name}</span>
                          <span className="mt-1 block text-xs text-zinc-500">
                            {repository.private ? "Private" : "Public"} · {repository.default_branch}
                            {repository.archived ? " · Archived" : ""}
                          </span>
                        </span>
                        {repository.private ? <Lock className="h-3.5 w-3.5 text-zinc-500" /> : null}
                      </button>
                    ))}
                    {repositoriesQuery.isSuccess && repositoriesQuery.data.repositories.length === 0 ? (
                      <p className="p-6 text-center text-sm text-zinc-500">No repositories match this search.</p>
                    ) : null}
                    <Pagination
                      page={repositoryPage}
                      hasNext={repositoriesQuery.data?.has_next ?? false}
                      onPage={setRepositoryPage}
                    />
                  </Selector>
                ) : null}

                {step === 2 ? (
                  <Selector
                    search={issueSearch}
                    onSearch={(value) => {
                      setIssueSearch(value);
                      setIssuePage(1);
                    }}
                    placeholder="Search issues..."
                  >
                    {issuesQuery.isFetching ? <LoadingRows /> : null}
                    {issuesQuery.isError ? (
                      <ErrorState error={issuesQuery.error} onRetry={() => issuesQuery.refetch()} />
                    ) : null}
                    {issuesQuery.data?.issues.map((issue) => (
                      <button
                        type="button"
                        key={issue.id}
                        onClick={() => setIssueNumber(issue.number)}
                        className={`w-full border-b border-[#21262D] px-3 py-3 text-left last:border-0 ${
                          issueNumber === issue.number ? "bg-blue-500/10" : "hover:bg-[#21262D]"
                        }`}
                      >
                        <span className="font-code text-xs text-zinc-500">#{issue.number}</span>
                        <span className="ml-2 text-sm text-zinc-100">{issue.title}</span>
                        <span className="mt-1 block truncate text-xs text-zinc-500">
                          {issue.labels.join(" · ") || `${issue.comments} comments`}
                        </span>
                      </button>
                    ))}
                    {issuesQuery.isSuccess && issuesQuery.data.issues.length === 0 ? (
                      <p className="p-6 text-center text-sm text-zinc-500">No open issues match this search.</p>
                    ) : null}
                    <Pagination
                      page={issuePage}
                      hasNext={issuesQuery.data?.has_next ?? false}
                      onPage={setIssuePage}
                    />
                  </Selector>
                ) : null}

                {step === 3 ? (
                  issueQuery.isFetching ? <LoadingRows /> : issueQuery.isError ? (
                    <ErrorState error={issueQuery.error} onRetry={() => issueQuery.refetch()} />
                  ) : issueQuery.data && summary ? (
                    <div className="space-y-5">
                      <div>
                        <div className="flex items-start justify-between gap-4">
                          <h2 className="text-sm font-semibold text-white">
                            #{issueQuery.data.number} {issueQuery.data.title}
                          </h2>
                          <a
                            href={issueQuery.data.html_url}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="Open issue on GitHub"
                            className="text-zinc-400 hover:text-white"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        </div>
                        <p className="mt-3 max-h-36 overflow-y-auto whitespace-pre-wrap rounded-md border border-[#30363D] bg-[#0D1117] p-3 text-xs leading-5 text-zinc-400">
                          {issueQuery.data.body || "No issue body provided."}
                        </p>
                      </div>
                      <dl className="grid gap-4 md:grid-cols-2">
                        {summary.map(([label, value]) => (
                          <div key={label}>
                            <dt className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">{label}</dt>
                            <dd className="mt-1 text-sm leading-6 text-zinc-200">{value}</dd>
                          </div>
                        ))}
                      </dl>
                      <p className="text-xs text-zinc-500">
                        The backend independently derives and persists the authoritative task summary. If summarization is unavailable, the raw issue still starts the task.
                      </p>
                    </div>
                  ) : null
                ) : null}

                {step === 4 ? (
                  <div>
                    <label htmlFor="task-instructions" className="text-sm font-medium text-zinc-200">
                      Additional Instructions <span className="text-zinc-500">(optional)</span>
                    </label>
                    <textarea
                      id="task-instructions"
                      value={instructions}
                      onChange={(event) => setInstructions(event.target.value)}
                      maxLength={10_000}
                      rows={7}
                      placeholder="Do not add a dependency. Add regression tests. Reuse the existing debounce hook."
                      className="mt-2 w-full resize-y rounded-md border border-[#30363D] bg-[#0D1117] p-3 text-sm leading-6 text-zinc-100 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
                    />
                    <p className="mt-2 text-right font-code text-[11px] text-zinc-600">
                      {instructions.length}/10000
                    </p>
                    <div className="mt-5 rounded-md border border-[#30363D] bg-[#0D1117] p-4 text-xs text-zinc-400">
                      <p><span className="text-zinc-200">Repository:</span> {selectedRepository?.full_name}</p>
                      <p className="mt-1"><span className="text-zinc-200">Issue:</span> #{issueNumber} {issueQuery.data?.title}</p>
                      <p className="mt-1"><span className="text-zinc-200">Autonomy:</span> Standard · final diff review required</p>
                    </div>
                  </div>
                ) : null}

                {createMutation.isError ? <div className="mt-4"><ErrorState error={createMutation.error} /></div> : null}
              </div>

              <footer className="flex items-center justify-between border-t border-[#30363D] px-5 py-4">
                <button
                  type="button"
                  onClick={() => (step === 1 ? onClose() : setStep((value) => value - 1))}
                  disabled={createMutation.isPending}
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-[#21262D] hover:text-white"
                >
                  <ArrowLeft className="h-4 w-4" />
                  {step === 1 ? "Cancel" : "Back"}
                </button>
                {step < 4 ? (
                  <button
                    type="button"
                    disabled={!canContinue}
                    onClick={() => setStep((value) => value + 1)}
                    className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Continue <ArrowRight className="h-4 w-4" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => createMutation.mutate()}
                    disabled={createMutation.isPending}
                    className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
                  >
                    {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    {createMutation.isPending ? "Creating task..." : "Create Task"}
                  </button>
                )}
              </footer>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function Selector({
  search,
  onSearch,
  placeholder,
  children,
}: {
  search: string;
  onSearch: (value: string) => void;
  placeholder: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="sr-only" htmlFor={`selector-${placeholder}`}>{placeholder}</label>
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
        <input
          id={`selector-${placeholder}`}
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-md border border-[#30363D] bg-[#0D1117] py-2.5 pl-9 pr-3 text-sm text-zinc-100 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
      </div>
      <div className="overflow-hidden rounded-md border border-[#30363D] bg-[#0D1117]">{children}</div>
    </div>
  );
}

function Pagination({
  page,
  hasNext,
  onPage,
}: {
  page: number;
  hasNext: boolean;
  onPage: (page: number) => void;
}) {
  if (page === 1 && !hasNext) return null;
  return (
    <div className="flex items-center justify-between border-t border-[#30363D] px-3 py-2">
      <button type="button" disabled={page === 1} onClick={() => onPage(page - 1)} className="text-xs text-zinc-400 disabled:opacity-30">Previous</button>
      <span className="font-code text-[11px] text-zinc-600">Page {page}</span>
      <button type="button" disabled={!hasNext} onClick={() => onPage(page + 1)} className="text-xs text-zinc-400 disabled:opacity-30">Next</button>
    </div>
  );
}

function LoadingRows() {
  return <p className="p-6 text-center text-sm text-zinc-500">Loading from GitHub...</p>;
}

function issueUnderstanding(title: string, body: string | null): [string, string][] {
  return [
    ["Problem", title],
    ["Expected behaviour", body?.slice(0, 420) || "Determine the expected behavior from the issue title and repository context."],
    ["Likely area", "Repository retrieval and planning will identify the relevant code paths."],
    ["Success criteria", "Implement the requested behavior, preserve existing constraints, add suitable regression coverage, and pass real verification."],
  ];
}
