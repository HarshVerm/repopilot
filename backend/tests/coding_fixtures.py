import subprocess
from pathlib import Path

from app.agents.coder.agent import (
    CoderRunResult,
)
from app.schemas.changes import (
    CoderOutput,
    FileChange,
)


def run_git(
    repo: Path,
    args: list[str],
) -> None:
    subprocess.run(
        [
            "git",
            *args,
        ],
        cwd=repo,
        check=True,
    )


def write_file(
    repo: Path,
    path: str,
    content: str,
) -> None:
    target = repo / path
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    target.write_text(
        content,
        encoding="utf-8",
    )


def create_coding_fixture_repo(
    repo: Path,
) -> None:
    repo.mkdir(
        parents=True,
        exist_ok=True,
    )
    write_file(
        repo,
        "src/components/SearchBox.tsx",
        """import { useEffect, useState } from "react";
import { useDebounce } from "../hooks/useDebounce";
import { searchProducts } from "../api/searchApi";

export function SearchBox() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    searchProducts(query);
  }, [query]);

  return (
    <input
      value={query}
      onChange={(event) => setQuery(event.target.value)}
    />
  );
}
""",
    )
    write_file(
        repo,
        "src/hooks/useDebounce.ts",
        """export function useDebounce(
  value: string,
  delay: number
) {
  return value;
}
""",
    )
    write_file(
        repo,
        "src/api/searchApi.ts",
        """export async function searchProducts(query: string) {
  return fetch(`/search?q=${query}`);
}
""",
    )
    run_git(
        repo,
        ["init", "-q"],
    )
    run_git(
        repo,
        ["add", "."],
    )
    run_git(
        repo,
        [
            "-c",
            "user.name=RepoPilot Test",
            "-c",
            "user.email=repopilot@example.com",
            "commit",
            "-m",
            "initial fixture",
            "-q",
        ],
    )


def fixed_searchbox_content() -> str:
    return """import { useEffect, useState } from "react";
import { useDebounce } from "../hooks/useDebounce";
import { searchProducts } from "../api/searchApi";

export function SearchBox() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (!debouncedQuery) {
      return;
    }

    searchProducts(debouncedQuery);
  }, [debouncedQuery]);

  return (
    <input
      value={query}
      onChange={(event) => setQuery(event.target.value)}
    />
  );
}
"""


class FakeCoderRunner:
    model = "fake-coder-model"

    def __init__(
        self,
        scenario,
    ) -> None:
        self.scenario = scenario
        self.invocations = 0
        self.inputs: list[str] = []

    async def run(
        self,
        coder_input: str,
        *,
        editor,
        trace_metadata: dict[str, str],
    ) -> CoderRunResult:
        self.invocations += 1
        self.inputs.append(coder_input)
        output = self.scenario(
            editor
        )

        return CoderRunResult(
            output=output,
            latency_ms=10.0,
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
            patch_operations_requested=(
                editor.operations_requested
            ),
            patch_operations_accepted=(
                editor.operations_accepted
            ),
            patch_operations_rejected=(
                editor.operations_rejected
            ),
        )


def successful_searchbox_scenario(
    editor,
) -> CoderOutput:
    editor.update_file(
        path="src/components/SearchBox.tsx",
        content=fixed_searchbox_content(),
    )

    return CoderOutput(
        summary="Updated SearchBox to search with the debounced query.",
        files_changed=[
            FileChange(
                path="src/components/SearchBox.tsx",
                change_type="update",
                summary="Use debounced query for search execution.",
            )
        ],
        implementation_notes=[
            "Tests were not run in Step 6."
        ],
    )


def needs_revision_scenario(
    editor,
) -> CoderOutput:
    return CoderOutput(
        summary="Approved scope is insufficient.",
        needs_plan_revision=True,
        revision_reason=(
            "The fix requires modifying src/hooks/useDebounce.ts, "
            "which is outside the approved modification scope."
        ),
    )
