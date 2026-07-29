import subprocess
from pathlib import Path


def init_git_repo(
    repo_path: Path,
) -> None:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=repo_path,
        check=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        check=True,
    )


def write_file(
    repo_path: Path,
    relative_path: str,
    content: bytes,
) -> None:
    path = repo_path / relative_path
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_bytes(content)


def create_retrieval_fixture_repo(
    repo_path: Path,
) -> None:
    repo_path.mkdir(
        parents=True,
        exist_ok=True,
    )
    write_file(
        repo_path,
        "src/utils/debounce.ts",
        b"""const DEFAULT_DELAY = 300;

export function debounce(
  fn: () => void,
  delay: number = DEFAULT_DELAY
) {
  return setTimeout(fn, delay);
}
""",
    )
    write_file(
        repo_path,
        "src/hooks/useDebounce.ts",
        b"""export function useDebounce(
  value: string,
  delay: number
) {
  const timeoutMs = delay;
  return value;
}
""",
    )
    write_file(
        repo_path,
        "src/components/SearchBox.tsx",
        b"""import { useDebounce } from "../hooks/useDebounce";

export function SearchBox() {
  const query = "";
  const debounced = useDebounce(query, 300);

  return <input value={debounced} />;
}
""",
    )
    write_file(
        repo_path,
        "src/api/searchApi.ts",
        b"""export async function searchProducts(
  query: string
) {
  return fetch(`/search?q=${query}`);
}
""",
    )
    write_file(
        repo_path,
        "backend/search.py",
        b"""def search_items(query):
    return query


class SearchIndex:
    pass
""",
    )
    write_file(
        repo_path,
        "node_modules/noise/index.js",
        b"export function dependencyNoise() {}\n",
    )
    write_file(
        repo_path,
        "dist/generated.js",
        b"export function generatedNoise() {}\n",
    )
    write_file(
        repo_path,
        "src/generated.min.js",
        b"function minifiedNoise(){}\n",
    )
    init_git_repo(repo_path)
