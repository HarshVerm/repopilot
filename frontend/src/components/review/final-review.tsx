"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileCheck2 } from "lucide-react";
import { useState } from "react";
import { getChangeSetDiff } from "@/lib/api/change-sets";
import {
  createFinalReview,
  approveTaskReview,
  getFinalReview,
  rejectTaskReview,
  requestTaskReviewChanges,
} from "@/lib/api/reviews";
import { getPublication, getReviewPublication, publishTask } from "@/lib/api/publications";
import { isApiError } from "@/lib/api/client";
import { queryKeys } from "@/lib/query-client";
import { shortSha } from "@/lib/formatters";
import { canRetryPublication } from "@/lib/task-actions";
import type { FinalReviewResponse, TaskResponse } from "@/types/api";
import { ConfirmationDialog } from "@/components/shared/confirmation-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { DiffViewer } from "@/components/changes/diff-viewer";
import { PublicationResult } from "@/components/publication/publication-result";

export function FinalReview({ task }: { task: TaskResponse }) {
  const queryClient = useQueryClient();
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [changesOpen, setChangesOpen] = useState(false);
  const [changeFeedback, setChangeFeedback] = useState("");
  const [staleReviewNotice, setStaleReviewNotice] = useState<string | null>(null);

  const diffQuery = useQuery({
    queryKey: task.active_change_set_id
      ? queryKeys.changeSetDiff(task.active_change_set_id)
      : ["changeSet", "none", "diff"],
    queryFn: ({ signal }) => getChangeSetDiff(task.active_change_set_id!, signal),
    enabled: Boolean(task.active_change_set_id),
  });

  const reviewQuery = useQuery({
    queryKey: task.active_review_id ? queryKeys.review(task.active_review_id) : ["review", "none"],
    queryFn: ({ signal }) => getFinalReview(task.active_review_id!, signal),
    enabled: Boolean(task.active_review_id),
  });

  const publicationByIdQuery = useQuery({
    queryKey: task.publication_id ? queryKeys.publication(task.publication_id) : ["publication", "none"],
    queryFn: ({ signal }) => getPublication(task.publication_id!, signal),
    enabled: Boolean(task.publication_id),
  });

  const reviewPublicationQuery = useQuery({
    queryKey: task.active_review_id
      ? queryKeys.reviewPublication(task.active_review_id)
      : ["review", "none", "publication"],
    queryFn: ({ signal }) => getReviewPublication(task.active_review_id!, signal),
    enabled: Boolean(task.active_review_id) && !task.publication_id,
    retry: false,
  });

  const publication = publicationByIdQuery.data ?? reviewPublicationQuery.data ?? null;

  const invalidateReviewState = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.task(task.task_id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.taskTimeline(task.task_id) }),
      task.active_change_set_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.changeSetDiff(task.active_change_set_id) })
        : Promise.resolve(),
      task.active_review_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.review(task.active_review_id) })
        : Promise.resolve(),
      task.active_review_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.reviewPublication(task.active_review_id) })
        : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks }),
    ]);
  };

  const createReviewMutation = useMutation({
    mutationFn: () => createFinalReview(task.active_change_set_id!),
    onSuccess: invalidateReviewState,
  });

  const approveMutation = useMutation({
    mutationFn: () =>
      approveTaskReview(task.task_id, reviewIntegrity(task, reviewQuery.data!)),
    onSuccess: invalidateReviewState,
    onError: async (error) => {
      if (isApiError(error) && error.status === 409) {
        setStaleReviewNotice(error.message);
        await invalidateReviewState();
      }
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () =>
      rejectTaskReview(task.task_id, {
        ...reviewIntegrity(task, reviewQuery.data!),
        reason: rejectReason.trim() || undefined,
      }),
    onSuccess: async () => {
      setRejectOpen(false);
      setRejectReason("");
      await invalidateReviewState();
    },
  });

  const requestChangesMutation = useMutation({
    mutationFn: () =>
      requestTaskReviewChanges(task.task_id, {
        ...reviewIntegrity(task, reviewQuery.data!),
        feedback: changeFeedback.trim(),
      }),
    onSuccess: async () => {
      setChangesOpen(false);
      setChangeFeedback("");
      await invalidateReviewState();
    },
    onError: async (error) => {
      if (isApiError(error) && error.status === 409) {
        setStaleReviewNotice(error.message);
        await invalidateReviewState();
      }
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => publishTask(task.task_id),
    onSuccess: invalidateReviewState,
    onError: async (error) => {
      if (isApiError(error) && error.status === 409) {
        await invalidateReviewState();
      }
    },
  });

  if (!task.active_change_set_id) {
    return <EmptyState title="No changes generated" detail="RepoPilot has not produced a change set for this task." />;
  }

  if (diffQuery.isLoading || reviewQuery.isLoading) {
    return <LoadingState title="Loading reviewed diff" rows={7} />;
  }

  if (diffQuery.isError) {
    return <ErrorState error={diffQuery.error} onRetry={() => diffQuery.refetch()} />;
  }

  if (reviewQuery.isError) {
    return <ErrorState error={reviewQuery.error} onRetry={() => reviewQuery.refetch()} />;
  }

  const review = reviewQuery.data;
  const diff = review?.diff ?? diffQuery.data?.diff ?? null;
  const canCreateReview = !task.active_review_id && task.status === "verification_passed";
  const canApproveReview = review?.status === "pending_review";
  const reviewApproved = review?.status === "approved" || task.status === "review_approved";
  const retryPublication = canRetryPublication(task, publication);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header className="flex flex-col justify-between gap-3 border-b border-[#30363D] pb-3 md:flex-row md:items-end">
        <div>
          <h1 className="mb-0.5 text-lg font-bold text-[#dae3ee]">Final Diff Review</h1>
          <p className="text-xs text-[#c1c6d6]">
            Review the exact diff before approving publication.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {review ? <StatusBadge status={review.status} /> : null}
          <span className="rounded border border-[#30363D] bg-[#182028] px-2.5 py-1 font-code text-xs text-[#c1c6d6]">
            {diffQuery.data?.files_changed.length ?? 0} files · +{diffQuery.data?.lines_added ?? 0} -{diffQuery.data?.lines_deleted ?? 0}
          </span>
        </div>
      </header>

      {staleReviewNotice ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
          <h2 className="text-sm font-semibold text-amber-300">Review is stale</h2>
          <p className="mt-1 text-xs leading-relaxed text-amber-100">
            {staleReviewNotice} RepoPilot refreshed the latest task state. Review the updated diff before approving again.
          </p>
        </div>
      ) : null}

      {review ? (
        <section className="rounded-xl border border-[#27272A] bg-[#141c24] p-4">
          <div className="flex items-center gap-2">
            <FileCheck2 className="h-4 w-4 text-emerald-400" />
            <h2 className="text-sm font-bold text-[#dae3ee]">Review Integrity</h2>
          </div>
          <dl className="mt-4 grid grid-cols-1 gap-3 text-xs md:grid-cols-4">
            <Pair label="Base Commit" value={shortSha(review.base_commit_sha)} />
            <Pair label="Diff Hash" value={shortSha(review.diff_hash)} />
            <Pair label="Change Set" value={shortSha(task.active_change_set_id)} />
            <Pair label="Execution Run" value={shortSha(task.active_execution_run_id)} />
          </dl>
          <p className="mt-3 font-code text-[11px] text-zinc-500">
            Review version {review.review_version}
          </p>
          <div className="mt-4 rounded-lg border border-[#30363D] bg-[#0D1117] p-3 text-xs leading-relaxed text-zinc-300">
            {review.risk_summary || "No risk summary provided."}
          </div>
        </section>
      ) : null}

      {!review && canCreateReview ? (
        <section className="rounded-xl border border-blue-500/30 bg-blue-500/10 p-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-blue-300">Prepare Final Review</h2>
              <p className="mt-1 text-xs text-blue-100/80">
                A passed change set is ready for the mandatory human review artifact.
              </p>
            </div>
            <button
              type="button"
              onClick={() => createReviewMutation.mutate()}
              disabled={createReviewMutation.isPending}
              className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {createReviewMutation.isPending ? "Preparing..." : "Prepare Review"}
            </button>
          </div>
          {createReviewMutation.isError ? (
            <div className="mt-3">
              <ErrorState error={createReviewMutation.error} />
            </div>
          ) : null}
        </section>
      ) : null}

      {reviewApproved ? (
        <section className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-emerald-300">
                <CheckCircle2 className="h-4 w-4" />
                Final Diff Approved
              </h2>
              <p className="mt-1 text-xs text-emerald-100/80">
                The exact reviewed diff is approved for publication.
              </p>
            </div>
            {(task.status === "review_approved" && !publication) || retryPublication ? (
              <button
                type="button"
                onClick={() => publishMutation.mutate()}
                disabled={publishMutation.isPending}
                className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {publishMutation.isPending
                  ? "Publishing..."
                  : retryPublication
                    ? "Retry Publishing"
                    : "Publish Pull Request"}
              </button>
            ) : null}
          </div>
          {publishMutation.isError ? (
            <div className="mt-3">
              <ErrorState error={publishMutation.error} />
            </div>
          ) : null}
        </section>
      ) : null}

      <DiffViewer diff={diff} />
      <PublicationResult publication={publication} />

      {canApproveReview ? (
        <div className="sticky bottom-0 z-40 flex items-center justify-between gap-4 border-t border-[#30363D] bg-[#060f16] px-6 py-3 shadow-lg">
          <p className="hidden text-xs text-[#c1c6d6] sm:block">
            Approval does not publish. Pull Request publication is a separate action.
          </p>
          <div className="ml-auto flex gap-3">
            <button
              type="button"
              onClick={() => setRejectOpen(true)}
              disabled={approveMutation.isPending || rejectMutation.isPending}
              className="rounded border border-[#30363D] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-[#dae3ee] transition-colors hover:bg-[#182028] disabled:opacity-50"
            >
              Reject
            </button>
            <button
              type="button"
              onClick={() => setChangesOpen(true)}
              disabled={
                approveMutation.isPending ||
                rejectMutation.isPending ||
                requestChangesMutation.isPending
              }
              className="rounded border border-amber-400/30 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-amber-200 transition-colors hover:bg-amber-500/10 disabled:opacity-50"
            >
              Request Changes
            </button>
            <button
              type="button"
              onClick={() => approveMutation.mutate()}
              disabled={approveMutation.isPending || rejectMutation.isPending}
              className="rounded bg-[#acc7ff] px-4 py-2 text-xs font-bold uppercase tracking-wider text-[#002f68] shadow-sm transition-colors hover:bg-[#d7e2ff] disabled:opacity-50"
            >
              {approveMutation.isPending ? "Approving..." : "Approve Final Diff"}
            </button>
          </div>
        </div>
      ) : null}

      {approveMutation.isError && !staleReviewNotice ? <ErrorState error={approveMutation.error} /> : null}

      <ConfirmationDialog
        open={rejectOpen}
        title="Reject final diff?"
        description="RepoPilot will keep the task history and mark this final review as rejected."
        confirmLabel="Reject Diff"
        variant="danger"
        pending={rejectMutation.isPending}
        reason={rejectReason}
        onReasonChange={setRejectReason}
        onCancel={() => setRejectOpen(false)}
        onConfirm={() => rejectMutation.mutate()}
      />
      <ConfirmationDialog
        open={changesOpen}
        title="Request changes"
        description="Describe the revision RepoPilot should make. The current review will be invalidated and a new verified revision will run."
        confirmLabel="Send Feedback"
        pending={requestChangesMutation.isPending}
        reason={changeFeedback}
        onReasonChange={setChangeFeedback}
        onCancel={() => setChangesOpen(false)}
        onConfirm={() => {
          if (changeFeedback.trim()) requestChangesMutation.mutate();
        }}
      />
      {requestChangesMutation.isError && !staleReviewNotice ? (
        <ErrorState error={requestChangesMutation.error} />
      ) : null}
    </div>
  );
}

function reviewIntegrity(task: TaskResponse, review: FinalReviewResponse) {
  return {
    review_id: review.review_id,
    changeset_id: task.active_change_set_id!,
    diff_hash: review.diff_hash,
  };
}

function Pair({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-code text-[11px] text-zinc-500">{label}</dt>
      <dd className="truncate font-code text-xs font-semibold text-[#dae3ee]" title={value}>
        {value}
      </dd>
    </div>
  );
}
