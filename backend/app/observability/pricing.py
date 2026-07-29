from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


class ModelPricingService:
    def __init__(
        self,
        *,
        prices: dict[str, ModelPrice] | None = None,
    ) -> None:
        self.prices = prices or {}

    def estimate_cost_usd(
        self,
        *,
        model: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> float | None:
        if (
            not model
            or input_tokens is None
            or output_tokens is None
        ):
            return None

        price = self.prices.get(
            model
        )

        if price is None:
            return None

        return (
            input_tokens
            * price.input_per_million
            / 1_000_000
        ) + (
            output_tokens
            * price.output_per_million
            / 1_000_000
        )

