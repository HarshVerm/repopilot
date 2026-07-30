"use client";

// Module purpose: Create a GitHub issue with optional repository-file context.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  FileCode2,
  Loader2,
  Search,
} from "lucide-react";
import { useMemo, useState } from "react";
import { ErrorState } from "@/components/shared/error-state";
import {
  createConnectedRepositoryIssue,
  listConnectedRepositoryFiles,
} from "@/lib/api/github";
import { queryKeys } from "@/lib/query-client";
import type { IssueResponse } from "@/types/api";

const MAX_RELATED_FILES = 20;
const MAX_VISIBLE_FILES = 200;
const MAX_ISSUE_BODY_LENGTH = 30_000;

/** Purpose: Render the signed-in-user GitHub issue creation form. */
export function CreateIssueForm({
  repositoryId,
  repositoryName,
  onCancel,
  onCreated,
}: {
  repositoryId: string;
  repositoryName: string;
  onCancel: () => void;
  onCreated: (issue: IssueResponse) => void;
}) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [fileSearch, setFileSearch] = useState("");
  const [relatedFiles, setRelatedFiles] = useState<string[]>([]);

  const filesQuery = useQuery({
    queryKey: queryKeys.connectedRepositoryFiles(repositoryId),
    queryFn: ({ signal }) =>
      listConnectedRepositoryFiles(repositoryId, signal),
    retry: false,
    staleTime: 30_000,
  });

  const matchingFiles = useMemo(() => {
    const needle = fileSearch.trim().toLowerCase();
    const files = filesQuery.data?.files ?? [];
    if (!needle) return files;
    return files.filter((path) => path.toLowerCase().includes(needle));
  }, [fileSearch, filesQuery.data?.files]);
  const visibleFiles = matchingFiles.slice(0, MAX_VISIBLE_FILES);
  const issueBodyLength = calculateIssueBodyLength(
    description,
    relatedFiles,
  );

  const createMutation = useMutation({
    mutationFn: () =>
      createConnectedRepositoryIssue(repositoryId, {
        title: title.trim(),
        description: description.trim(),
        related_files: relatedFiles,
      }),
    onSuccess: async (issue) => {
      queryClient.setQueryData(
        queryKeys.connectedIssue(repositoryId, issue.number),
        issue,
      );
      await queryClient.invalidateQueries({
        queryKey: ["github", "repository", repositoryId, "issues"],
      });
      onCreated(issue);
    },
  });

  const canCreate =
    title.trim().length > 0 &&
    description.trim().length > 0 &&
    issueBodyLength <= MAX_ISSUE_BODY_LENGTH &&
    !createMutation.isPending;

  /** Add or remove one optional related file without allowing duplicates. */
  function toggleFile(path: string) {
    setRelatedFiles((current) =>
      current.includes(path)
        ? current.filter((item) => item !== path)
        : current.length < MAX_RELATED_FILES
          ? [...current, path]
          : current,
    );
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canCreate) createMutation.mutate();
      }}
      className="space-y-5"
    >
      <div className="rounded-md border border-[#30363D] bg-[#0D1117] px-3 py-2 text-xs text-zinc-400">
        New issue in <span className="font-code text-zinc-200">{repositoryName}</span>
      </div>

      <div>
        <label htmlFor="new-issue-title" className="text-sm font-medium text-zinc-200">
          Issue title
        </label>
        <input
          id="new-issue-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={300}
          required
          autoFocus
          placeholder="Describe the problem in one sentence"
          className="mt-2 w-full rounded-md border border-[#30363D] bg-[#0D1117] px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
        <p className="mt-1 text-right font-code text-[11px] text-zinc-600">
          {title.length}/300
        </p>
      </div>

      <div>
        <label htmlFor="new-issue-description" className="text-sm font-medium text-zinc-200">
          Description
        </label>
        <p className="mt-1 text-xs text-zinc-500">
          Explain the current behavior, expected behavior, and any useful reproduction steps.
        </p>
        <textarea
          id="new-issue-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={30_000}
          rows={7}
          required
          placeholder={"What is happening?\n\nWhat should happen instead?\n\nHow can someone reproduce it?"}
          className="mt-2 w-full resize-y rounded-md border border-[#30363D] bg-[#0D1117] p-3 text-sm leading-6 text-zinc-100 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
        <p className="mt-1 text-right font-code text-[11px] text-zinc-600">
          {issueBodyLength}/{MAX_ISSUE_BODY_LENGTH}
        </p>
        {issueBodyLength > MAX_ISSUE_BODY_LENGTH ? (
          <p className="mt-1 text-xs text-red-300">
            Shorten the description or select fewer related files.
          </p>
        ) : null}
      </div>

      <div>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-sm font-medium text-zinc-200">
              Related files <span className="text-zinc-500">(optional)</span>
            </h2>
            <p className="mt-1 text-xs text-zinc-500">
              Select up to {MAX_RELATED_FILES} files to include as context in the GitHub issue.
            </p>
          </div>
          <span className="font-code text-[11px] text-zinc-500">
            {relatedFiles.length}/{MAX_RELATED_FILES} selected
          </span>
        </div>

        <label htmlFor="related-file-search" className="sr-only">
          Search repository files
        </label>
        <div className="relative mt-3">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            id="related-file-search"
            value={fileSearch}
            onChange={(event) => setFileSearch(event.target.value)}
            placeholder="Search files by path..."
            className="w-full rounded-md border border-[#30363D] bg-[#0D1117] py-2.5 pl-9 pr-3 text-sm text-zinc-100 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
          />
        </div>

        <div className="mt-2 max-h-64 overflow-y-auto rounded-md border border-[#30363D] bg-[#0D1117]">
          {filesQuery.isFetching ? (
            <p className="flex items-center justify-center gap-2 p-6 text-sm text-zinc-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading files from GitHub...
            </p>
          ) : filesQuery.isError ? (
            <div className="p-3">
              <ErrorState
                error={filesQuery.error}
                onRetry={() => filesQuery.refetch()}
              />
            </div>
          ) : visibleFiles.length === 0 ? (
            <p className="p-6 text-center text-sm text-zinc-500">
              No repository files match this search.
            </p>
          ) : (
            visibleFiles.map((path) => {
              const checked = relatedFiles.includes(path);
              const selectionFull =
                relatedFiles.length >= MAX_RELATED_FILES && !checked;
              return (
                <label
                  key={path}
                  className={`flex cursor-pointer items-start gap-3 border-b border-[#21262D] px-3 py-2.5 last:border-0 ${
                    checked ? "bg-blue-500/10" : "hover:bg-[#161B22]"
                  } ${selectionFull ? "cursor-not-allowed opacity-50" : ""}`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={selectionFull}
                    onChange={() => toggleFile(path)}
                    className="mt-0.5 h-4 w-4 rounded border-[#30363D] bg-[#161B22] accent-blue-500"
                  />
                  <FileCode2 className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" />
                  <span className="min-w-0 break-all font-code text-xs leading-5 text-zinc-300">
                    {path}
                  </span>
                </label>
              );
            })
          )}
        </div>
        {matchingFiles.length > MAX_VISIBLE_FILES ? (
          <p className="mt-2 text-xs text-zinc-500">
            Showing the first {MAX_VISIBLE_FILES} matching files. Narrow the search to find another path.
          </p>
        ) : null}
        {filesQuery.data?.truncated ? (
          <p className="mt-2 text-xs text-amber-300">
            GitHub returned a partial repository tree. You can still create the issue without selecting a file.
          </p>
        ) : null}
      </div>

      {createMutation.isError ? (
        <ErrorState error={createMutation.error} />
      ) : null}

      <div className="flex items-center justify-between border-t border-[#30363D] pt-4">
        <button
          type="button"
          onClick={onCancel}
          disabled={createMutation.isPending}
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-[#21262D] hover:text-white disabled:opacity-50"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to issues
        </button>
        <button
          type="submit"
          disabled={!canCreate}
          className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {createMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : null}
          {createMutation.isPending ? "Creating issue..." : "Create GitHub Issue"}
        </button>
      </div>
    </form>
  );
}

/** Purpose: Match the backend's final GitHub issue-body length calculation. */
function calculateIssueBodyLength(
  description: string,
  relatedFiles: string[],
) {
  const body = description.trim();
  if (relatedFiles.length === 0) return body.length;
  const fileList = relatedFiles
    .map((path) => `- <code>${escapeHtml(path)}</code>`)
    .join("\n");
  return (
    `${body}\n\n---\n\n### Related files\n\n${fileList}`
  ).length;
}

/** Purpose: Match Python html.escape for file paths embedded in issue HTML. */
function escapeHtml(value: string) {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#x27;",
      })[character] ?? character,
  );
}
