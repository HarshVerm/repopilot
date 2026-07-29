"use client";

import { useRouter } from "next/navigation";
import { CreateTaskModal } from "@/components/tasks/create-task-modal";

export default function NewTaskPage() {
  const router = useRouter();
  return (
    <CreateTaskModal
      open
      onClose={() => router.push("/tasks")}
    />
  );
}
