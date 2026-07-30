"use client";

// Module purpose: Render and coordinate the task table interface.

import Link from "next/link";
import { MoreVertical } from "lucide-react";
import type { TaskResponse } from "@/types/api";
import { formatDateTime, formatDuration, repositoryFullName } from "@/lib/formatters";
import { getTaskLifecycle, isWaitingForHuman } from "@/lib/task-status";
import { TaskStatusBadge } from "./task-status-badge";

/** Purpose: Render the task table interface. */
export function TaskTable({ tasks }: { tasks: TaskResponse[] }) {
  return (
    <div className="flex-1 overflow-auto rounded-xl border border-[#27272A]">
      <table className="w-full min-w-[900px] border-collapse text-left">
        <thead className="sticky top-0 z-10 border-b border-[#3F3F46] bg-[#27272A]/90 backdrop-blur-md">
          <tr className="text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
            <th className="w-72 p-3">Task</th>
            <th className="w-44 p-3">Repository</th>
            <th className="w-28 p-3">Issue</th>
            <th className="w-40 p-3">Status</th>
            <th className="w-36 p-3">Current Stage</th>
            <th className="w-24 p-3 text-right">Duration</th>
            <th className="w-32 p-3">Updated</th>
            <th className="w-14 p-3 text-center">Act</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#27272A] bg-[#09090B] text-xs">
          {tasks.map((task) => {
            const lifecycle = getTaskLifecycle(task);
            const activeStage =
              lifecycle.find((stage) => stage.state === "active" || stage.state === "waiting") ??
              lifecycle.find((stage) => stage.state === "failed") ??
              lifecycle[lifecycle.length - 1];

            return (
              <tr key={task.task_id} className="group transition-colors hover:bg-[#18181B]">
                <td className="p-3 align-top">
                  <Link
                    href={`/tasks/${task.task_id}`}
                    className={`block max-w-64 truncate font-semibold ${
                      isWaitingForHuman(task) ? "text-amber-400" : "text-blue-400"
                    }`}
                    title={task.issue?.title ?? task.task_id}
                  >
                    {task.issue?.title ?? `Issue #${task.issue_number}`}
                  </Link>
                  <span className="mt-0.5 block truncate font-code text-[10px] text-zinc-500">
                    {task.task_id} · v{task.version}
                  </span>
                </td>
                <td className="p-3 align-top">
                  <span className="block max-w-40 truncate font-medium text-zinc-300" title={repositoryFullName(task)}>
                    {repositoryFullName(task)}
                  </span>
                </td>
                <td className="p-3 align-top font-code text-zinc-400">#{task.issue_number}</td>
                <td className="p-3 align-top">
                  <TaskStatusBadge status={task.status} />
                </td>
                <td className="p-3 align-top font-medium text-zinc-400">{activeStage.label}</td>
                <td className="p-3 text-right align-top font-code text-zinc-400">
                  {formatDuration(task.started_at, task.completed_at)}
                </td>
                <td className="p-3 align-top font-code text-[11px] text-zinc-500">
                  {formatDateTime(task.updated_at ?? task.last_event_at)}
                </td>
                <td className="p-3 text-center align-top">
                  <Link
                    href={`/tasks/${task.task_id}`}
                    className="inline-flex rounded-lg p-1 text-zinc-400 opacity-0 transition-opacity hover:text-blue-400 group-hover:opacity-100"
                    title="Open task"
                  >
                    <MoreVertical className="h-4 w-4" />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
