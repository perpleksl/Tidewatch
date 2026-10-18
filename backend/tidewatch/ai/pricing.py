"""Official Anthropic prices, USD per million tokens (verified 18 Oct 2026 against
https://platform.claude.com/docs/en/about-claude/pricing).

Surplus calls are not priced here: every Surplus response reports its own exact charge
(`usage.buyer_cost_micro`), which is what gets logged.
"""

from dataclasses import dataclass
from decimal import Decimal

MILLION = Decimal(1_000_000)
#: Batch API: 50% off input and output.
BATCH_DISCOUNT = Decimal("0.5")


@dataclass(frozen=True)
class Rates:
    input: Decimal
    cache_write_5m: Decimal
    cache_read: Decimal
    output: Decimal


@dataclass(frozen=True)
class ModelPrice:
    standard: Rates
    #: Haiku 5.5 charges more when the prompt exceeds 100K tokens.
    long_prompt: Rates | None = None
    long_prompt_threshold: int = 100_000


ANTHROPIC_PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(
        Rates(Decimal("4"), Decimal("5"), Decimal("0.20"), Decimal("20"))
    ),
    "claude-sonnet-5-5": ModelPrice(
        Rates(Decimal("2"), Decimal("2.50"), Decimal("0.10"), Decimal("10"))
    ),
    "claude-haiku-5-5": ModelPrice(
        Rates(Decimal("0.10"), Decimal("0.125"), Decimal("0.01"), Decimal("0.50")),
        long_prompt=Rates(Decimal("0.50"), Decimal("0.625"), Decimal("0.05"), Decimal("2.50")),
    ),
}


class UnknownModelPrice(KeyError):  # noqa: N818
    """No official price is recorded for this model; add it before using the model."""


def anthropic_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    batch: bool = False,
) -> Decimal:
    """USD cost of one Anthropic call.

    `input_tokens` excludes cached tokens, as the API reports them.
    """
    try:
        price = ANTHROPIC_PRICES[model]
    except KeyError:
        raise UnknownModelPrice(model) from None
    prompt_size = input_tokens + cache_read_tokens + cache_write_tokens
    rates = price.standard
    if price.long_prompt is not None and prompt_size > price.long_prompt_threshold:
        rates = price.long_prompt
    cost = (
        input_tokens * rates.input
        + cache_write_tokens * rates.cache_write_5m
        + cache_read_tokens * rates.cache_read
        + output_tokens * rates.output
    ) / MILLION
    return cost * BATCH_DISCOUNT if batch else cost


def surplus_cost(buyer_cost_micro: str | int) -> Decimal:
    """Surplus reports its charge in microdollars (millionths of a USD)."""
    return Decimal(str(buyer_cost_micro)) / MILLION
