export function LoadingState({
  title = "Loading",
  rows = 4,
}: {
  title?: string;
  rows?: number;
}) {
  return (
    <div className="rounded-xl border border-[#27272A] bg-[#18181B] p-4">
      <div className="mb-4 h-4 w-40 animate-pulse rounded bg-[#27272A]" aria-label={title} />
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="h-10 animate-pulse rounded-lg bg-[#0D1117]" />
        ))}
      </div>
    </div>
  );
}
