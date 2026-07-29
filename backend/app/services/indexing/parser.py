from tree_sitter import Language, Parser

import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript


PYTHON_LANGUAGE = Language(
    tspython.language()
)

JAVASCRIPT_LANGUAGE = Language(
    tsjavascript.language()
)

TYPESCRIPT_LANGUAGE = Language(
    tstypescript.language_typescript()
)

TSX_LANGUAGE = Language(
    tstypescript.language_tsx()
)


LANGUAGES = {
    "python": PYTHON_LANGUAGE,
    "javascript": JAVASCRIPT_LANGUAGE,
    "typescript": TYPESCRIPT_LANGUAGE,
    "tsx": TSX_LANGUAGE,
}


def supports_ast_parsing(
    language_name: str,
) -> bool:
    return language_name in LANGUAGES


def parse_source(
    language_name: str,
    source: bytes,
):
    language = LANGUAGES.get(
        language_name
    )

    if not language:
        raise ValueError(
            f"Unsupported language: {language_name}"
        )

    parser = Parser(language)

    return parser.parse(source)
