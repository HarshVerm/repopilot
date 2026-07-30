// Module purpose: Provide reusable diff frontend utilities.

export type DiffLineType = "context" | "added" | "removed" | "meta";

export interface ParsedDiffLine {
  oldLine?: number;
  newLine?: number;
  type: DiffLineType;
  content: string;
}

export interface ParsedDiffFile {
  path: string;
  oldPath?: string;
  newPath?: string;
  additions: number;
  deletions: number;
  lines: ParsedDiffLine[];
}

/** Purpose: Normalize path for this frontend workflow. */
function normalizePath(path: string) {
  return path.replace(/^a\//, "").replace(/^b\//, "");
}

/** Purpose: Parse hunk header for this frontend workflow. */
function parseHunkHeader(line: string) {
  const match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
  if (!match) {
    return null;
  }

  return {
    oldLine: Number(match[1]),
    newLine: Number(match[2]),
  };
}

/** Purpose: Parse unified diff for this frontend workflow. */
export function parseUnifiedDiff(diff: string | null | undefined): ParsedDiffFile[] {
  if (!diff?.trim()) {
    return [];
  }

  const files: ParsedDiffFile[] = [];
  let current: ParsedDiffFile | null = null;
  let oldLine = 0;
  let newLine = 0;

  for (const rawLine of diff.split("\n")) {
    if (rawLine.startsWith("diff --git ")) {
      const parts = rawLine.split(" ");
      const oldPath = parts[2] ? normalizePath(parts[2]) : undefined;
      const newPath = parts[3] ? normalizePath(parts[3]) : undefined;
      current = {
        path: newPath ?? oldPath ?? "unknown",
        oldPath,
        newPath,
        additions: 0,
        deletions: 0,
        lines: [{ type: "meta", content: rawLine }],
      };
      files.push(current);
      continue;
    }

    if (!current) {
      current = {
        path: "diff",
        additions: 0,
        deletions: 0,
        lines: [],
      };
      files.push(current);
    }

    if (rawLine.startsWith("+++ ")) {
      current.newPath = normalizePath(rawLine.slice(4));
      current.path = current.newPath === "/dev/null" ? current.oldPath ?? current.path : current.newPath;
      current.lines.push({ type: "meta", content: rawLine });
      continue;
    }

    if (rawLine.startsWith("--- ")) {
      current.oldPath = normalizePath(rawLine.slice(4));
      current.lines.push({ type: "meta", content: rawLine });
      continue;
    }

    if (rawLine.startsWith("@@")) {
      const hunk = parseHunkHeader(rawLine);
      if (hunk) {
        oldLine = hunk.oldLine;
        newLine = hunk.newLine;
      }
      current.lines.push({ type: "meta", content: rawLine });
      continue;
    }

    if (rawLine.startsWith("+") && !rawLine.startsWith("+++")) {
      current.additions += 1;
      current.lines.push({ type: "added", newLine, content: rawLine.slice(1) });
      newLine += 1;
      continue;
    }

    if (rawLine.startsWith("-") && !rawLine.startsWith("---")) {
      current.deletions += 1;
      current.lines.push({ type: "removed", oldLine, content: rawLine.slice(1) });
      oldLine += 1;
      continue;
    }

    current.lines.push({
      type: "context",
      oldLine,
      newLine,
      content: rawLine.startsWith(" ") ? rawLine.slice(1) : rawLine,
    });
    oldLine += 1;
    newLine += 1;
  }

  return files;
}
