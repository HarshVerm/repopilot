import { useEffect, useState } from "react";
import { useDebounce } from "../hooks/useDebounce";

type SearchBoxProps = {
  initialQuery?: string;
  onSearch: (query: string) => void;
};

export function SearchBox({ initialQuery = "", onSearch }: SearchBoxProps) {
  const [query, setQuery] = useState(initialQuery);
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    onSearch(query);
  }, [onSearch, query]);

  return (
    <label>
      Search
      <input
        aria-label="Search tasks"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <span data-testid="search-preview">{debouncedQuery}</span>
    </label>
  );
}
