"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { notFound, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { getPlan } from "@/lib/api/plans";
import { getPublication, getReviewPublication } from "@/lib/api/publications";
import { getTask } from "@/lib/api/tasks";
import { isApiError } from "@/lib/api/client";
import { queryKeys } from "@/lib/query-client";
import { isActiveTask } from "@/lib/task-status";
import type { IssueResponse, TaskResponse } from "@/types/api";
import type { TaskTab } from "@/types/task";
import { DebugAttemptList } from "@/components/debugger/debug-attempt-list";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";
import { PlanReview } from "@/components/plan/plan-review";
import { FinalReview } from "@/components/review/final-review";
import { VerificationSummary } from "@/components/verification/verification-summary";
import { TaskMetrics } from "@/components/metrics/task-metrics";
import { TaskTimeline } from "@/components/timeline/task-timeline";
import { TaskDetailHeader } from "./task-detail-header";
import { TaskOverview } from "./task-overview";
import { TaskTabs, normalizeTaskTab } from "./task-tabs";

export function TaskDetailView({ taskId }: { taskId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const activeTab = normalizeTaskTab(searchParams.get("tab"));

  const taskQuery = useQuery({
    queryKey: queryKeys.task(taskId),
    queryFn: ({ signal }) => getTask(taskId, signal),
    refetchInterval: (query) => {
      const task = query.state.data;
      return task && isActiveTask(task) ? 3000 : false;
    },
  });

  const task = taskQuery.data;
  const issue = task ? taskIssue(task) : undefined;

  const planQuery = useQuery({
    queryKey: task?.active_plan_id ? queryKeys.plan(task.active_plan_id) : ["plan", "none"],
    queryFn: ({ signal }) => getPlan(task!.active_plan_id!, signal),
    enabled: Boolean(task?.active_plan_id),
  });

  const publicationByIdQuery = useQuery({
    queryKey: task?.publication_id ? queryKeys.publication(task.publication_id) : ["publication", "none"],
    queryFn: ({ signal }) => getPublication(task!.publication_id!, signal),
    enabled: Boolean(task?.publication_id),
  });

  const reviewPublicationQuery = useQuery({
    queryKey: task?.active_review_id
      ? queryKeys.reviewPublication(task.active_review_id)
      : ["review", "none", "publication"],
    queryFn: ({ signal }) => getReviewPublication(task!.active_review_id!, signal),
    enabled: Boolean(task?.active_review_id && !task.publication_id),
    retry: false,
  });

  const publication = publicationByIdQuery.data ?? reviewPublicationQuery.data ?? null;

  const setTab = (tab: TaskTab) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.replace(`/tasks/${taskId}?${params.toString()}`, { scroll: false });
  };

  const refreshing = taskQuery.isFetching;
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.task(taskId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.taskTimeline(taskId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.taskMetrics(taskId) }),
      task?.active_plan_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.plan(task.active_plan_id) })
        : Promise.resolve(),
      task?.active_change_set_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.changeSetDiff(task.active_change_set_id) })
        : Promise.resolve(),
      task?.active_execution_run_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.executionRun(task.active_execution_run_id) })
        : Promise.resolve(),
      task?.active_review_id
        ? queryClient.invalidateQueries({ queryKey: queryKeys.review(task.active_review_id) })
        : Promise.resolve(),
    ]);
  };

  const body = useMemo(() => {
    if (!task) return null;
    if (activeTab === "overview") {
      return (
        <TaskOverview
          task={task}
          issue={issue}
          plan={planQuery.data}
          publication={publication}
        />
      );
    }
    if (activeTab === "plan") return <PlanReview task={task} />;
    if (activeTab === "changes") return <FinalReview task={task} />;
    if (activeTab === "verification") return <VerificationSummary task={task} />;
    if (activeTab === "debug") return <DebugAttemptList task={task} />;
    if (activeTab === "timeline") return <TaskTimeline task={task} />;
    if (activeTab === "metrics") return <TaskMetrics task={task} />;
    return null;
  }, [activeTab, issue, planQuery.data, publication, task]);

  if (taskQuery.isLoading) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <LoadingState title="Loading task" rows={8} />
      </div>
    );
  }

  if (taskQuery.isError) {
    if (isApiError(taskQuery.error) && taskQuery.error.status === 404) {
      notFound();
    }

    return (
      <div className="flex-1 overflow-y-auto p-6">
        <ErrorState error={taskQuery.error} onRetry={() => taskQuery.refetch()} />
      </div>
    );
  }

  if (!task) {
    return null;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[#09090B] text-[#FAFAFA]">
      <TaskDetailHeader
        task={task}
        issue={issue}
        publication={publication}
        onTabChange={setTab}
        onRefresh={refresh}
        refreshing={refreshing}
      />
      <TaskTabs activeTab={activeTab} onTabChange={setTab} />
      <div className="flex-1 overflow-y-auto p-6 pb-20">{body}</div>
    </div>
  );
}

function taskIssue(task: TaskResponse): IssueResponse | undefined {
  if (!task.issue) return undefined;
  return {
    id: task.issue.github_issue_id ?? 0,
    number: task.issue.number,
    title: task.issue.title ?? `Issue #${task.issue.number}`,
    body: task.issue.body,
    state: "snapshot",
    html_url: task.issue.html_url ?? "",
    comments: 0,
    labels: task.issue.labels,
    author: task.issue.author,
    created_at: task.issue.created_at,
    updated_at: task.issue.updated_at_at_creation,
  };
}
