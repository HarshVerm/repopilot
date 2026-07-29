"use client";

import { FileText, Maximize2 } from "lucide-react";
import { useMemo, useState } from "react";
import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { parseUnifiedDiff } from "@/lib/diff";

export function DiffViewer({ diff }: { diff: string | null | undefined }) {
  const files = useMemo(() => parseUnifiedDiff(diff), [diff]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const selectedFile = files.find((file) => file.path === selectedPath) ?? files[0];

  if (files.length === 0 || !selectedFile) {
    return <EmptyState title="No source changes were generated." />;
  }

  const visibleLines = selectedFile.lines.slice(0, 1200);
  const truncated = selectedFile.lines.length > visibleLines.length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        {files.map((file) => (
          <button
            key={file.path}
            type="button"
            onClick={() => setSelectedPath(file.path)}
            className={`shrink-0 rounded border px-3 py-1.5 font-code text-xs transition-colors ${
              selectedFile.path === file.path
                ? "border-[#acc7ff] bg-[#182028] text-[#acc7ff]"
                : "border-[#30363D] bg-[#141c24] text-[#c1c6d6] hover:text-[#dae3ee]"
            }`}
            title={file.path}
          >
            {file.path.split("/").at(-1) ?? file.path}
          </button>
        ))}
      </div>

      <section
        className={`flex flex-col overflow-hidden rounded-lg border border-[#30363D] bg-[#182028] ${
          expanded ? "fixed inset-4 z-[75] bg-[#0D1117] shadow-2xl" : ""
        }`}
      >
        <div className="flex items-center justify-between border-b border-[#30363D] bg-[#2d363e] px-4 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="h-4 w-4 shrink-0 text-[#c1c6d6]" />
            <span className="truncate font-code text-xs font-semibold text-[#dae3ee]">
              {selectedFile.path}
            </span>
            <span className="shrink-0 font-code text-[11px] text-[#7ee787]">
              +{selectedFile.additions}
            </span>
            <span className="shrink-0 font-code text-[11px] text-[#ff7b72]">
              -{selectedFile.deletions}
            </span>
          </div>
          <div className="flex shrink-0 gap-2">
            <CopyButton value={selectedFile.path} label="Path" />
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="rounded-lg p-1 text-[#c1c6d6] transition-colors hover:bg-[#182028] hover:text-[#dae3ee]"
              title="Toggle expand"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="max-h-[60vh] overflow-auto bg-black py-2 font-code text-xs">
          <table className="w-full border-collapse">
            <tbody>
              {visibleLines.map((line, index) => (
                <tr
                  key={`${line.oldLine ?? ""}-${line.newLine ?? ""}-${index}`}
                  className={`hover:bg-[#222b33]/40 ${
                    line.type === "added"
                      ? "diff-added"
                      : line.type === "removed"
                        ? "diff-removed"
                        : line.type === "meta"
                          ? "bg-[#0D1117] text-zinc-500"
                          : ""
                  }`}
                >
                  <td className="diff-line-num">{line.oldLine ?? ""}</td>
                  <td className="diff-line-num">{line.newLine ?? ""}</td>
                  <td className="w-6 text-center font-bold text-[#8b909f]">
                    {line.type === "added" ? "+" : line.type === "removed" ? "-" : ""}
                  </td>
                  <td className="min-w-[640px] whitespace-pre px-3 text-[#dae3ee]">
                    {line.content}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {truncated ? (
            <div className="border-t border-[#30363D] bg-[#0D1117] px-4 py-3 text-xs text-amber-300">
              Large diff truncated in the browser view. Review file-by-file before approval.
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
