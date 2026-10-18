"""The one way Tidewatch calls AI (ARCHITECTURE.md AD9; CLAUDE.md §4).

    from tidewatch.ai.client import worker, reviewer, professor_deep, professor_synthesis

Each function reads its tier's provider and model from Settings, makes the call, and writes
exactly one CostEntry. Worker and reviewer calls that fail on Surplus are retried once, then
answered by the fallback model, and System Health shows the marketplace as unavailable.
Professor tiers only ever use the official Anthropic API.

Callers pass only the prompt content they were given. Never put keys, environment data or
personal data in a prompt.
"""

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from tidewatch.ai.providers import (
    AnthropicProvider,
    Completion,
    Prompt,
    Provider,
    ProviderUnavailable,
    SurplusProvider,
    anthropic_completion,
)
from tidewatch.db.models import CostEntry
from tidewatch.db.settings import AiTier, get_setting

log = logging.getLogger("tidewatch.ai")

#: Shown on System Health while worker/reviewer calls are being answered by the fallback.
MARKETPLACE_SOURCE = "ai_marketplace"
FALLBACK_MESSAGE = "AI marketplace unavailable — using fallback"

PROFESSOR_TIERS = ("professor_deep", "professor_synthesis")


class ProfessorProviderError(ValueError):
    """A professor tier is configured for a provider other than Anthropic. No call is made."""


class AiUnavailable(Exception):  # noqa: N818
    """The call could not be answered (professor down, or fallback also failed)."""


@dataclass(frozen=True)
class AiResult:
    text: str
    tier: str
    provider: str
    model: str
    cost_usd: Decimal
    used_fallback: bool


@dataclass
class Providers:
    """The providers to use; tests replace them with fakes."""

    surplus: Provider
    anthropic: Provider


def default_providers() -> Providers:
    return Providers(surplus=SurplusProvider(), anthropic=AnthropicProvider())


def _provider(providers: Providers, name: str) -> Provider:
    if name == "anthropic":
        return providers.anthropic
    if name == "surplus":
        return providers.surplus
    raise AiUnavailable(f"unknown AI provider {name!r}")


def _log_cost(session: Session, tier: str, done: Completion, batch: bool = False) -> None:
    session.add(
        CostEntry(
            source=done.provider,
            category="ai",
            amount_usd=done.cost_usd,
            model=done.model,
            tier=tier,
            input_tokens=done.input_tokens,
            output_tokens=done.output_tokens,
            cache_read_tokens=done.cache_read_tokens,
            cache_write_tokens=done.cache_write_tokens,
            batch=batch,
            at=datetime.now(UTC),
        )
    )
    session.flush()


def _marketplace_status(session: Session, using_fallback: bool) -> None:
    # Imported here so `ai` does not depend on ingestion at import time.
    from tidewatch.ingestion.runner import get_status

    row = get_status(session, MARKETPLACE_SOURCE)
    if using_fallback:
        row.status = "degraded"
        row.last_error = FALLBACK_MESSAGE
        row.last_attempt_at = datetime.now(UTC)
    elif row.status != "ok" or row.last_error:
        row.status = "ok"
        row.last_error = None
    row.last_success_at = datetime.now(UTC) if not using_fallback else row.last_success_at


def _result(tier: str, done: Completion, used_fallback: bool) -> AiResult:
    return AiResult(done.text, tier, done.provider, done.model, done.cost_usd, used_fallback)


def professor_tier(session: Session, tier: str) -> AiTier:
    """The tier's setting, refusing anything but Anthropic (AD9 hard rule)."""
    setting: AiTier = get_setting(session, f"ai.tier.{tier}")
    if setting.provider != "anthropic":
        raise ProfessorProviderError(
            f"{tier} must use the official Anthropic API, not {setting.provider!r} (AD9)"
        )
    return setting


def _call_with_fallback(
    session: Session, tier: str, prompt: Prompt, providers: Providers
) -> AiResult:
    setting: AiTier = get_setting(session, f"ai.tier.{tier}")
    primary = _provider(providers, setting.provider)
    attempts = 2 if setting.provider == "surplus" else 1  # Surplus: retry once
    for attempt in range(1, attempts + 1):
        try:
            done = primary.complete(setting.model, prompt)
        except ProviderUnavailable as exc:
            log.warning("%s via %s failed (attempt %d): %s", tier, setting.provider, attempt, exc)
            continue
        _log_cost(session, tier, done)
        if setting.provider == "surplus":
            _marketplace_status(session, using_fallback=False)
        return _result(tier, done, used_fallback=False)

    fallback: AiTier = get_setting(session, "ai.tier.fallback")
    if setting.provider == "surplus":
        _marketplace_status(session, using_fallback=True)
    try:
        done = _provider(providers, fallback.provider).complete(fallback.model, prompt)
    except ProviderUnavailable as exc:
        raise AiUnavailable(f"{tier}: primary and fallback both failed") from exc
    _log_cost(session, tier, done)
    return _result(tier, done, used_fallback=True)


def worker(session: Session, prompt: Prompt, providers: Providers | None = None) -> AiResult:
    """High volume, low judgment (labelling). Surplus first, fallback if unavailable."""
    return _call_with_fallback(session, "worker", prompt, providers or default_providers())


def reviewer(session: Session, prompt: Prompt, providers: Providers | None = None) -> AiResult:
    """Medium judgment (triage). Surplus first, fallback if unavailable."""
    return _call_with_fallback(session, "reviewer", prompt, providers or default_providers())


def _professor(
    session: Session, tier: str, prompt: Prompt, providers: Providers | None
) -> AiResult:
    setting = professor_tier(session, tier)  # raises before any call if not Anthropic
    provider = (providers or default_providers()).anthropic
    try:
        done = provider.complete(setting.model, prompt)
    except ProviderUnavailable as exc:
        raise AiUnavailable(f"{tier}: Anthropic unavailable") from exc
    _log_cost(session, tier, done)
    return _result(tier, done, used_fallback=False)


def professor_deep(
    session: Session, prompt: Prompt, providers: Providers | None = None
) -> AiResult:
    """Judgments shown to the Owner. Official Anthropic API only; no marketplace fallback."""
    return _professor(session, "professor_deep", prompt, providers)


def professor_synthesis(
    session: Session, prompt: Prompt, providers: Providers | None = None
) -> AiResult:
    """Once-daily cross-market reasoning. Official Anthropic API only."""
    return _professor(session, "professor_synthesis", prompt, providers)


# --- Batch API (professor work that isn't time-critical: 50% cheaper) -----------------------


def submit_professor_batch(
    session: Session,
    tier: str,
    prompts: dict[str, Prompt],
    provider: AnthropicProvider | None = None,
) -> str:
    """Submit professor prompts as one Anthropic batch. Returns the batch ID to collect later.

    `prompts` maps your own ID (e.g. a token ID) to its prompt.
    """
    if tier not in PROFESSOR_TIERS:
        raise ValueError(f"batches are for professor tiers only, not {tier!r}")
    setting = professor_tier(session, tier)
    anthropic_provider = provider or AnthropicProvider()
    requests = [
        {"custom_id": custom_id, "params": anthropic_provider.request(setting.model, prompt)}
        for custom_id, prompt in prompts.items()
    ]
    batch = anthropic_provider.client().messages.batches.create(requests=requests)  # type: ignore[arg-type]
    return str(batch.id)


def collect_professor_batch(
    session: Session, tier: str, batch_id: str, provider: AnthropicProvider | None = None
) -> dict[str, AiResult] | None:
    """Results of a finished batch (None while it is still running).

    Each successful result is logged as one CostEntry at the batch price.
    """
    setting = professor_tier(session, tier)
    client = (provider or AnthropicProvider()).client()
    if client.messages.batches.retrieve(batch_id).processing_status != "ended":
        return None
    results: dict[str, AiResult] = {}
    for item in client.messages.batches.results(batch_id):
        if item.result.type != "succeeded":
            log.warning("batch %s: %s %s", batch_id, item.custom_id, item.result.type)
            continue
        done = anthropic_completion(setting.model, item.result.message, batch=True)
        done = replace(done, model=setting.model)
        _log_cost(session, tier, done, batch=True)
        results[item.custom_id] = _result(tier, done, used_fallback=False)
    return results
