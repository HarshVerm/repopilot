export function formatDueDate(isoDate: string): string {
  const date = new Date(isoDate);
  return `${date.getMonth() + 1}/${date.getDate()}/${date.getFullYear()}`;
}

export function groupByTag(items: Array<{ tags: string[] }>) {
  return items.reduce<Record<string, number>>((acc, item) => {
    const tag = item.tags[0] || "untagged";
    acc[tag] = (acc[tag] || 0) + 1;
    return acc;
  }, {});
}

export function summarizeCounts(counts: Record<string, number>): string {
  return Object.entries(counts)
    .map(([key, value]) => `${key}:${value}`)
    .join(",");
}
