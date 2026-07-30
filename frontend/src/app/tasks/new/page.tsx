"use client";

// Module purpose: Render the new application route.

import { useRouter } from "next/navigation";
import { CreateTaskModal } from "@/components/tasks/create-task-modal";

/** Purpose: Render the new task page interface. */
export default function NewTaskPage() {
  const router = useRouter();
  return (
    <CreateTaskModal
      open
      onClose={() => router.push("/tasks")}
    />
  );
}
