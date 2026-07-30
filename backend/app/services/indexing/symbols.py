"""Extract searchable code symbols from Tree-sitter syntax trees."""

from dataclasses import dataclass


PYTHON_SYMBOL_TYPES = {
    "class_definition": "class",
    "function_definition": "function",
    "import_statement": "import",
    "import_from_statement": "import",
}

JS_SYMBOL_TYPES = {
    "class_declaration": "class",
    "enum_declaration": "enum",
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "import_statement": "import",
    "interface_declaration": "interface",
    "method_definition": "method",
    "type_alias_declaration": "type",
    "variable_declarator": "variable",
}

FUNCTION_VALUE_TYPES = {
    "arrow_function",
    "function_expression",
    "generator_function",
}


@dataclass
class CodeSymbolInfo:
    """Describe one symbol and its one-based location in a source file."""

    kind: str
    name: str
    start_line: int
    end_line: int


def get_node_text(
    source: bytes,
    node,
) -> str:
    """Decode the exact source text covered by a Tree-sitter node."""
    return source[
        node.start_byte:node.end_byte
    ].decode("utf-8", errors="ignore")


def get_symbol_kind(
    node,
    symbol_types: dict[str, str],
) -> str | None:
    """Map an AST node to a symbol kind, including function variables."""
    kind = symbol_types.get(
        node.type
    )

    if node.type == "variable_declarator":
        value_node = node.child_by_field_name(
            "value"
        )

        if (
            value_node
            and value_node.type
            in FUNCTION_VALUE_TYPES
        ):
            return "function"

    return kind


def extract_symbols(
    language: str,
    source: bytes,
    tree,
) -> list[CodeSymbolInfo]:
    """Walk an AST and return the named symbols used by structural search."""

    if language == "python":
        symbol_types = PYTHON_SYMBOL_TYPES
    else:
        symbol_types = JS_SYMBOL_TYPES

    results: list[CodeSymbolInfo] = []

    stack = [tree.root_node]

    while stack:

        node = stack.pop()

        kind = get_symbol_kind(
            node,
            symbol_types,
        )

        if kind:

            if kind == "import":
                name = get_node_text(
                    source,
                    node,
                )

            else:
                name_node = (
                    node.child_by_field_name(
                        "name"
                    )
                )

                if name_node:
                    name = get_node_text(
                        source,
                        name_node,
                    )
                else:
                    name = "<anonymous>"

            results.append(
                CodeSymbolInfo(
                    kind=kind,
                    name=name,
                    start_line=(
                        node.start_point[0] + 1
                    ),
                    end_line=(
                        node.end_point[0] + 1
                    ),
                )
            )

        stack.extend(
            reversed(node.named_children)
        )

    return results
