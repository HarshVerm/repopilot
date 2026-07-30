// Module purpose: Render the [task id] application route.

import { TaskDetailView } from "@/components/tasks/task-detail-view";

/** Purpose: Render the task detail page interface. */
export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const { taskId } = await params;
  return <TaskDetailView taskId={taskId} />;
}
