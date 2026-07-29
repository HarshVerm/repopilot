import Link from "next/link";

export default function TaskNotFound() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="rounded-xl border border-[#27272A] bg-[#18181B] p-6 text-center">
        <h1 className="text-lg font-bold text-[#FAFAFA]">Task not found</h1>
        <p className="mt-2 text-sm text-zinc-400">RepoPilot does not have a task with that ID.</p>
        <Link
          href="/tasks"
          className="mt-4 inline-flex rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500"
        >
          View Tasks
        </Link>
      </div>
    </div>
  );
}
