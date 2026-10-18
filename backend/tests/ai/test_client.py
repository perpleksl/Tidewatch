"""PER-14: tiered AI client. Mocked providers only; CI never calls a real API."""

import ast
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tidewatch.ai.client import (
    FALLBACK_MESSAGE,
    MARKETPLACE_SOURCE,
    AiUnavailable,
    ProfessorProviderError,
    Providers,
    collect_professor_batch,
    professor_deep,
    professor_synthesis,
    reviewer,
    submit_professor_batch,
    worker,
)
from tidewatch.ai.pricing import UnknownModelPrice, anthropic_cost
from tidewatch.ai.providers import (
    SURPLUS_BASE_URL,
    AnthropicProvider,
    Completion,
    Prompt,
    ProviderUnavailable,
    SurplusProvider,
)
from tidewatch.db.models import CostEntry, Setting
from tidewatch.ingestion.runner import get_status

PROMPT = Prompt(user="Label this synthetic post about 0xTEST.", system="Answer in one word.")


@dataclass
class FakeProvider:
    name: str
    fail_times: int = 0
    calls: list[str] = field(default_factory=list)

    def complete(self, model: str, prompt: Prompt) -> Completion:
        self.calls.append(model)
        if len(self.calls) <= self.fail_times:
            raise ProviderUnavailable("simulated outage")
        return Completion(
            text=f"answer from {model}",
            provider=self.name,
            model=model,
            input_tokens=100,
            output_tokens=10,
            cache_read_tokens=0,
            cost_usd=Decimal("0.000123"),
        )


def fakes(surplus_fails: int = 0, anthropic_fails: int = 0) -> Providers:
    return Providers(
        surplus=FakeProvider("surplus", surplus_fails),
        anthropic=FakeProvider("anthropic", anthropic_fails),
    )


def costs(session: Session) -> list[CostEntry]:
    return list(session.scalars(select(CostEntry).order_by(CostEntry.created_at)).all())


def set_tier(session: Session, tier: str, provider: str, model: str) -> None:
    """Write straight to the table, bypassing Settings validation, to test the code's own guard."""
    row = session.scalars(select(Setting).where(Setting.key == f"ai.tier.{tier}")).one()
    row.value = {"provider": provider, "model": model}
    session.flush()


@pytest.mark.parametrize(
    ("call", "tier", "provider", "model"),
    [
        (worker, "worker", "surplus", "deepseek-v4.1-flash"),
        (reviewer, "reviewer", "surplus", "deepseek-v4-pro-0813"),
        (professor_deep, "professor_deep", "anthropic", "claude-sonnet-5-5"),
        (professor_synthesis, "professor_synthesis", "anthropic", "claude-opus-5-5"),
    ],
)
def test_ac1_each_tier_uses_the_provider_and_model_from_settings(
    session: Session, call: Any, tier: str, provider: str, model: str
) -> None:
    """AC1: each tier function calls the provider and model from Settings."""
    providers = fakes()
    result = call(session, PROMPT, providers)
    assert (result.tier, result.provider, result.model) == (tier, provider, model)
    used = providers.surplus if provider == "surplus" else providers.anthropic
    other = providers.anthropic if provider == "surplus" else providers.surplus
    assert used.calls == [model]  # type: ignore[attr-defined]
    assert other.calls == []  # type: ignore[attr-defined]


def test_ac1_changing_the_setting_changes_the_model(session: Session) -> None:
    set_tier(session, "worker", "surplus", "some-other-model")
    providers = fakes()
    assert worker(session, PROMPT, providers).model == "some-other-model"


@pytest.mark.parametrize("call", [professor_deep, professor_synthesis])
def test_ac2_professor_on_surplus_is_rejected_and_no_call_is_made(
    session: Session, call: Any
) -> None:
    """AC2: a professor tier set to Surplus is rejected with a clear error; no call is made."""
    tier = call.__name__
    set_tier(session, tier, "surplus", "claude-opus-5-5")
    providers = fakes()
    with pytest.raises(ProfessorProviderError, match="official Anthropic API"):
        call(session, PROMPT, providers)
    assert providers.surplus.calls == []  # type: ignore[attr-defined]
    assert providers.anthropic.calls == []  # type: ignore[attr-defined]
    assert costs(session) == []


def test_ac2_professor_batch_also_refuses_surplus(session: Session) -> None:
    set_tier(session, "professor_deep", "surplus", "x")
    with pytest.raises(ProfessorProviderError):
        submit_professor_batch(session, "professor_deep", {"a": PROMPT}, provider=None)


def test_ac3_two_surplus_failures_fall_back_and_show_on_system_health(session: Session) -> None:
    """AC3: Surplus fails twice; the fallback model answers; System Health shows the notice."""
    providers = fakes(surplus_fails=2)
    result = worker(session, PROMPT, providers)
    assert result.used_fallback is True
    assert (result.provider, result.model) == ("anthropic", "claude-haiku-5-5")
    assert providers.surplus.calls == ["deepseek-v4.1-flash"] * 2  # type: ignore[attr-defined]
    status = get_status(session, MARKETPLACE_SOURCE)
    assert status.status == "degraded"
    assert status.last_error == FALLBACK_MESSAGE == "AI marketplace unavailable — using fallback"


def test_ac3_one_failure_is_retried_without_fallback(session: Session) -> None:
    providers = fakes(surplus_fails=1)
    result = reviewer(session, PROMPT, providers)
    assert result.used_fallback is False
    assert result.provider == "surplus"


def test_ac3_marketplace_notice_clears_when_surplus_answers_again(session: Session) -> None:
    worker(session, PROMPT, fakes(surplus_fails=2))
    worker(session, PROMPT, fakes())
    status = get_status(session, MARKETPLACE_SOURCE)
    assert (status.status, status.last_error) == ("ok", None)


def test_fallback_failing_too_raises(session: Session) -> None:
    with pytest.raises(AiUnavailable):
        worker(session, PROMPT, fakes(surplus_fails=2, anthropic_fails=1))


def test_professor_outage_does_not_fall_back_to_the_marketplace(session: Session) -> None:
    providers = fakes(anthropic_fails=1)
    with pytest.raises(AiUnavailable):
        professor_deep(session, PROMPT, providers)
    assert providers.surplus.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("call", "surplus_fails"),
    [(worker, 0), (worker, 2), (reviewer, 1), (professor_deep, 0), (professor_synthesis, 0)],
)
def test_ac4_every_call_writes_exactly_one_cost_entry(
    session: Session, call: Any, surplus_fails: int
) -> None:
    """AC4: one CostEntry per call, with provider, model, tier, tokens and USD cost."""
    result = call(session, PROMPT, fakes(surplus_fails=surplus_fails))
    [entry] = costs(session)
    assert entry.category == "ai"
    assert (entry.source, entry.model, entry.tier) == (result.provider, result.model, result.tier)
    assert (entry.input_tokens, entry.output_tokens, entry.cache_read_tokens) == (100, 10, 0)
    assert entry.amount_usd == Decimal("0.000123")


# --- Real adapters with mocked transport ------------------------------------------------


def surplus_with(handler: Any, monkeypatch: pytest.MonkeyPatch) -> SurplusProvider:
    monkeypatch.setenv("SURPLUS_API_KEY", "test-key-not-real")
    return SurplusProvider(http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_ac5_surplus_cost_comes_from_the_price_surplus_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: Surplus cost is the charge Surplus reports (usage.buyer_cost_micro)."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4.1-flash",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": 2, "buyer_cost_micro": "37"},
            },
        )

    done = surplus_with(handler, monkeypatch).complete("deepseek-v4.1-flash", PROMPT)
    assert seen["url"] == f"{SURPLUS_BASE_URL}/chat/completions"
    assert seen["auth"] == "Bearer test-key-not-real"
    assert done.cost_usd == Decimal("0.000037")
    assert (done.input_tokens, done.output_tokens, done.text) == (40, 2, "ok")


def test_ac5_surplus_cost_header_is_used_when_body_lacks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-si-buyer-cost-micro": "1500"},
            json={"choices": [{"message": {"content": "ok"}}], "usage": {}},
        )

    done = surplus_with(handler, monkeypatch).complete("m", PROMPT)
    assert done.cost_usd == Decimal("0.0015")


@pytest.mark.parametrize("status", [402, 404, 429, 500, 503])
def test_surplus_errors_and_no_supply_count_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    provider = surplus_with(lambda _: httpx.Response(status, json={}), monkeypatch)
    with pytest.raises(ProviderUnavailable):
        provider.complete("m", PROMPT)


def test_surplus_timeout_counts_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderUnavailable):
        surplus_with(handler, monkeypatch).complete("m", PROMPT)


def test_missing_keys_count_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SURPLUS_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailable, match="SURPLUS_API_KEY"):
        SurplusProvider(http=httpx.Client()).complete("m", PROMPT)


def message(input_tokens: int, output_tokens: int, cache_read: int, cache_write: int) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text="verdict")],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
    )


class FakeAnthropicClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.batch_requests: list[Any] = []
        outer = self

        class Messages:
            def create(self, **params: Any) -> Any:
                outer.created.append(params)
                return message(1000, 200, 5000, 0)

            class batches:  # noqa: N801 - mirrors the SDK's attribute name
                @staticmethod
                def create(requests: Any) -> Any:
                    outer.batch_requests = requests
                    return SimpleNamespace(id="msgbatch_TEST")

                @staticmethod
                def retrieve(batch_id: str) -> Any:
                    return SimpleNamespace(processing_status="ended")

                @staticmethod
                def results(batch_id: str) -> Any:
                    return [
                        SimpleNamespace(
                            custom_id="token-1",
                            result=SimpleNamespace(
                                type="succeeded", message=message(1000, 200, 0, 0)
                            ),
                        ),
                        SimpleNamespace(
                            custom_id="token-2", result=SimpleNamespace(type="errored")
                        ),
                    ]

        self.messages = Messages()


def test_ac6_professor_prompt_caching_marks_fixed_context_and_prices_cache_reads(
    session: Session,
) -> None:
    """AC6: fixed instructions are sent for caching; cached tokens use the cache-read price."""
    client = FakeAnthropicClient()
    providers = Providers(surplus=FakeProvider("surplus"), anthropic=AnthropicProvider(client))  # type: ignore[arg-type]
    prompt = Prompt(user="Assess 0xTEST.", system="Be brief.", cached_context="Long fixed rubric")
    result = professor_deep(session, prompt, providers)

    [params] = client.created
    assert params["system"][0] == {
        "type": "text",
        "text": "Long fixed rubric",
        "cache_control": {"type": "ephemeral"},
    }
    [entry] = costs(session)
    assert entry.cache_read_tokens == 5000
    # Sonnet 5.5: $2/M input, $0.10/M cache read, $10/M output.
    expected = (1000 * Decimal("2") + 5000 * Decimal("0.10") + 200 * Decimal("10")) / 1_000_000
    assert result.cost_usd == entry.amount_usd == expected


def test_ac6_professor_batch_submission_and_collection_at_batch_price(session: Session) -> None:
    """AC6: professor prompts can be submitted as a Batch; results are logged at 50% price."""
    client = FakeAnthropicClient()
    provider = AnthropicProvider(client)  # type: ignore[arg-type]
    batch_id = submit_professor_batch(
        session, "professor_synthesis", {"token-1": PROMPT, "token-2": PROMPT}, provider
    )
    assert batch_id == "msgbatch_TEST"
    assert [r["custom_id"] for r in client.batch_requests] == ["token-1", "token-2"]
    assert client.batch_requests[0]["params"]["model"] == "claude-opus-5-5"

    results = collect_professor_batch(session, "professor_synthesis", batch_id, provider)
    assert results is not None
    assert list(results) == ["token-1"]  # the errored request is skipped, not billed
    [entry] = costs(session)
    assert entry.batch is True
    full = (1000 * Decimal("4") + 200 * Decimal("20")) / 1_000_000
    assert entry.amount_usd == full / 2


def test_batches_are_professor_only(session: Session) -> None:
    with pytest.raises(ValueError, match="professor tiers only"):
        submit_professor_batch(session, "worker", {"a": PROMPT})


def test_official_prices_per_million_tokens() -> None:
    """Prices match platform.claude.com/docs/en/about-claude/pricing (18 Oct 2026)."""
    m = 1_000_000
    assert anthropic_cost("claude-opus-5-5", m, 0) == Decimal("4")
    assert anthropic_cost("claude-opus-5-5", 0, m) == Decimal("20")
    assert anthropic_cost("claude-sonnet-5-5", 0, 0, cache_read_tokens=m) == Decimal("0.10")
    assert anthropic_cost("claude-sonnet-5-5", 0, 0, cache_write_tokens=m) == Decimal("2.50")
    assert anthropic_cost("claude-haiku-5-5", m // 10, 0) == Decimal("0.01")
    # Haiku prompts over 100K tokens use the higher rate.
    assert anthropic_cost("claude-haiku-5-5", 200_000, 0) == Decimal("0.1")
    with pytest.raises(UnknownModelPrice):
        anthropic_cost("claude-unknown", 1, 1)


def test_ac7_only_the_ai_package_talks_to_ai_providers() -> None:
    """AC7: no module outside ai/ imports the Anthropic SDK or calls the Surplus URL."""
    package = Path(__file__).resolve().parents[2] / "tidewatch"
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        if path.parent.name == "ai" and path.parent.parent == package:
            continue
        source = path.read_text()
        if "surplusintelligence" in source.lower():
            offenders.append(f"{path.name}: Surplus URL")
        for node in ast.walk(ast.parse(source)):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n == "anthropic" or n.startswith("anthropic.") for n in names):
                offenders.append(f"{path.name}: imports anthropic")
    assert offenders == []
