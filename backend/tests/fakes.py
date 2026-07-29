from types import SimpleNamespace


EMBEDDING_DIMENSIONS = 1536


class FakeEmbeddingClient:
    model = "fake-embedding-model"
    dimensions = EMBEDDING_DIMENSIONS
    batch_size = 2

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [
            fake_embedding(text)
            for text in texts
        ]


def fake_embedding(
    text: str,
) -> list[float]:
    lowered = text.lower()
    vector = [
        0.001
        for _ in range(EMBEDDING_DIMENSIONS)
    ]

    keyword_groups = [
        (
            0,
            [
                "debounce",
                "delay",
                "wait",
                "briefly",
                "keypress",
                "key press",
            ],
        ),
        (
            1,
            [
                "search",
                "api",
                "request",
                "fetch",
                "products",
            ],
        ),
        (
            2,
            [
                "input",
                "searchbox",
                "component",
            ],
        ),
        (
            3,
            [
                "python",
                "backend",
                "index",
            ],
        ),
    ]

    for dimension, keywords in keyword_groups:
        for keyword in keywords:
            if keyword in lowered:
                vector[dimension] += 1.0

    return vector


class FakeOpenAIEmbeddings:
    def __init__(
        self,
        dimensions: int,
    ) -> None:
        self.dimensions = dimensions
        self.calls: list[list[str]] = []

    async def create(
        self,
        *,
        model: str,
        input: list[str],
        dimensions: int,
    ):
        self.calls.append(input)

        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    index=index,
                    embedding=[
                        float(index + 1)
                        for _ in range(dimensions)
                    ],
                )
                for index, _ in enumerate(input)
            ]
        )


class FakeOpenAIClient:
    def __init__(
        self,
        dimensions: int,
    ) -> None:
        self.embeddings = FakeOpenAIEmbeddings(
            dimensions
        )
