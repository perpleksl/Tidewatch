"""The two AI providers (ARCHITECTURE.md AD9). Only this package talks to them.

- Surplus Intelligence marketplace: OpenAI-compatible chat completions,
  https://api.surplusintelligence.ai/v1 (verified 18 Oct 2026), key in SURPLUS_API_KEY.
- Official Anthropic API through the official SDK, key in ANTHROPIC_API_KEY.
"""

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import anthropic
import httpx

from tidewatch.ai.pricing import anthropic_cost, surplus_cost

SURPLUS_BASE_URL = "https://api.surplusintelligence.ai/v1"
#: Pinned on purpose. The Anthropic SDK would otherwise honour an ANTHROPIC_BASE_URL environment
#: variable, which marketplace guides (incl. Surplus's "Anthropic skin") tell people to set; that
#: would silently route professor calls through a marketplace (ARCHITECTURE.md AD9).
ANTHROPIC_OFFICIAL_BASE_URL = "https://api.anthropic.com"
SURPLUS_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class Prompt:
    """What to ask. `cached_context` is fixed instruction text worth caching (Anthropic only)."""

    user: str
    system: str | None = None
    cached_context: str | None = None
    max_tokens: int = 1024


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class ProviderUnavailable(Exception):  # noqa: N818
    """The provider failed, timed out or has no supply. The client may retry or fall back."""


class Provider(Protocol):
    name: str

    def complete(self, model: str, prompt: Prompt) -> Completion: ...


def _require_key(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ProviderUnavailable(f"{name} is not set")
    return value


class SurplusProvider:
    """Worker and reviewer tiers only. Never used for professor tasks."""

    name = "surplus"

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http

    def complete(self, model: str, prompt: Prompt) -> Completion:
        messages: list[dict[str, str]] = []
        system = "\n\n".join(p for p in (prompt.cached_context, prompt.system) if p)
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt.user})
        http = self._http or httpx.Client(timeout=SURPLUS_TIMEOUT_SECONDS)
        try:
            response = http.post(
                f"{SURPLUS_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {_require_key('SURPLUS_API_KEY')}"},
                json={"model": model, "messages": messages, "max_tokens": prompt.max_tokens},
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Surplus request failed: {type(exc).__name__}") from exc
        finally:
            if self._http is None:
                http.close()
        # 402 no balance, 404 no sellers, 429, 5xx no healthy sellers: all mean "use fallback".
        if response.status_code != 200:
            raise ProviderUnavailable(f"Surplus answered HTTP {response.status_code}")
        body: dict[str, Any] = response.json()
        usage = body.get("usage") or {}
        reported = usage.get("buyer_cost_micro") or response.headers.get("x-si-buyer-cost-micro")
        if reported is None:
            raise ProviderUnavailable("Surplus response did not report its cost")
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable("Surplus response had no answer") from exc
        return Completion(
            text=text,
            provider=self.name,
            model=str(body.get("model") or model),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=surplus_cost(reported),
            raw=body,
        )


def anthropic_system(prompt: Prompt) -> list[dict[str, Any]]:
    """System blocks; fixed context is marked for prompt caching (cache reads cost less)."""
    blocks: list[dict[str, Any]] = []
    if prompt.cached_context:
        blocks.append(
            {"type": "text", "text": prompt.cached_context, "cache_control": {"type": "ephemeral"}}
        )
    if prompt.system:
        blocks.append({"type": "text", "text": prompt.system})
    return blocks


def anthropic_completion(model: str, message: Any, batch: bool = False) -> Completion:
    """Turn an SDK Message (live or from a batch) into a Completion with its official cost."""
    usage = message.usage
    cache_read = int(getattr(usage, "cache_read_input_tokens", None) or 0)
    cache_write = int(getattr(usage, "cache_creation_input_tokens", None) or 0)
    text = "".join(block.text for block in message.content if block.type == "text")
    return Completion(
        text=text,
        provider="anthropic",
        model=model,
        input_tokens=int(usage.input_tokens),
        output_tokens=int(usage.output_tokens),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cost_usd=anthropic_cost(
            model, int(usage.input_tokens), int(usage.output_tokens), cache_read, cache_write, batch
        ),
    )


class AnthropicProvider:
    """Professor tiers and the fallback. Official API only."""

    name = "anthropic"

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client

    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=_require_key("ANTHROPIC_API_KEY"), base_url=ANTHROPIC_OFFICIAL_BASE_URL
            )
        return self._client

    def request(self, model: str, prompt: Prompt) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": prompt.max_tokens,
            "messages": [{"role": "user", "content": prompt.user}],
        }
        system = anthropic_system(prompt)
        if system:
            params["system"] = system
        return params

    def complete(self, model: str, prompt: Prompt) -> Completion:
        try:
            message = self.client().messages.create(**self.request(model, prompt))
        except anthropic.APIError as exc:
            raise ProviderUnavailable(f"Anthropic request failed: {type(exc).__name__}") from exc
        return anthropic_completion(model, message)


def surplus_model_ids(http: httpx.Client | None = None) -> list[str]:
    """IDs currently in Surplus's catalog (GET /v1/models). Used to check the tier defaults."""
    client = http or httpx.Client(timeout=SURPLUS_TIMEOUT_SECONDS)
    try:
        response = client.get(
            f"{SURPLUS_BASE_URL}/models",
            headers={"Authorization": f"Bearer {_require_key('SURPLUS_API_KEY')}"},
        )
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(f"Surplus request failed: {type(exc).__name__}") from exc
    finally:
        if http is None:
            client.close()
    if response.status_code != 200:
        raise ProviderUnavailable(f"Surplus answered HTTP {response.status_code}")
    data = response.json().get("data") or []
    return sorted(str(m.get("id")) for m in data if isinstance(m, dict) and m.get("id"))
