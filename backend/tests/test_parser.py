from app.services.indexing.parser import (
    parse_source,
)
from app.services.indexing.symbols import (
    extract_symbols,
)


def symbol_by_name(
    language: str,
    source: bytes,
):
    tree = parse_source(
        language,
        source,
    )

    assert tree.root_node is not None
    assert not tree.root_node.has_error

    symbols = extract_symbols(
        language,
        source,
        tree,
    )

    return {
        symbol.name: symbol
        for symbol in symbols
    }


def test_python_symbols():
    source = b"""def search_items(query):
    pass

class SearchIndex:
    pass
"""

    symbols = symbol_by_name(
        "python",
        source,
    )

    assert symbols["search_items"].kind == "function"
    assert symbols["SearchIndex"].kind == "class"


def test_javascript_symbols():
    source = b"""function debounce(fn, delay) {
    return fn;
}

class SearchService {
    search(query) {
        return query;
    }
}
"""

    symbols = symbol_by_name(
        "javascript",
        source,
    )

    assert symbols["debounce"].kind == "function"
    assert symbols["SearchService"].kind == "class"
    assert symbols["search"].kind == "method"


def test_typescript_symbols():
    source = b"""export function debounce<T>(
    fn: T,
    delay: number
) {
    return fn;
}

export class SearchService {
    search(query: string) {
        return query;
    }
}
"""

    symbols = symbol_by_name(
        "typescript",
        source,
    )

    assert symbols["debounce"].kind == "function"
    assert symbols["SearchService"].kind == "class"
    assert symbols["search"].kind == "method"


def test_tsx_symbols_use_tsx_grammar():
    source = b"""export function SearchBox() {
    return <input />;
}
"""

    typescript_tree = parse_source(
        "typescript",
        source,
    )
    tsx_symbols = symbol_by_name(
        "tsx",
        source,
    )

    assert typescript_tree.root_node.has_error
    assert tsx_symbols["SearchBox"].kind == "function"


def test_symbol_line_numbers_are_one_based():
    source = b"""import api from "./api";

function debounce(fn, delay) {
    return fn;
}
"""

    symbols = symbol_by_name(
        "javascript",
        source,
    )

    assert symbols["debounce"].start_line == 3
    assert symbols["debounce"].end_line == 5


def test_arrow_and_function_expression_symbols_are_functions():
    source = b"""const debounce = () => {};
const search = function () {};
export const SearchBox = () => {};
"""

    symbols = symbol_by_name(
        "typescript",
        source,
    )

    assert symbols["debounce"].kind == "function"
    assert symbols["search"].kind == "function"
    assert symbols["SearchBox"].kind == "function"
