"""PER-16: the X history probe script (mocked provider; no real calls, no database)."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "x_history_probe.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("x_history_probe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_script = load()


def test_ac3_without_a_key_it_says_which_variable_to_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC3: runs without an API key and prints which environment variable to set."""
    monkeypatch.delenv("X_HISTORY_API_KEY", raising=False)
    assert probe_script.main([]) == 2
    assert "X_HISTORY_API_KEY" in capsys.readouterr().err


def test_ac4_with_a_key_it_prints_the_number_of_posts_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC4: with a key, prints how many posts were found for the period; saves nothing."""
    monkeypatch.setenv("X_HISTORY_API_KEY", "test-key-not-real")
    monkeypatch.delenv("DATABASE_URL", raising=False)  # the probe must not need a database
    requests: list[httpx.Request] = []
    pages = [
        {
            "tweets": [{"id": "1", "createdAt": "Mon Sep 28 10:00:00 +0000 2026"}] * 20,
            "has_next_page": True,
            "next_cursor": "c2",
        },
        {
            "tweets": [{"id": "2", "createdAt": "Thu Oct 01 09:00:00 +0000 2026"}] * 7,
            "has_next_page": False,
            "next_cursor": "",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=pages[len(requests) - 1])

    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert probe_script.main([], http=http) == 0
    out = capsys.readouterr().out
    assert "Posts found: 27 (in 2 pages)" in out
    assert "Nothing was saved." in out
    first = requests[0]
    assert first.headers["X-API-Key"] == "test-key-not-real"
    # 20 Sep 2026 00:00 UTC to 6 Oct 2026 00:00 UTC (end date inclusive).
    assert first.url.params["query"] == "nullmask since_time:1789862400 until_time:1791244800"
    assert requests[1].url.params["cursor"] == "c2"


def test_probe_stops_at_the_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = {"tweets": [{}] * 20, "has_next_page": True, "next_cursor": "x"}
        return httpx.Response(200, json=body)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    from datetime import date

    result = probe_script.probe(
        "k", "nullmask", date(2026, 9, 20), date(2026, 10, 5), 3, http, log=lambda _: None
    )
    assert (result.posts, result.pages, result.stopped_at_page_limit) == (60, 3, True)


def test_provider_error_is_reported_not_crashed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("X_HISTORY_API_KEY", "bad")
    http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401, text="no")))
    assert probe_script.main([], http=http) == 1
    assert "HTTP 401" in capsys.readouterr().err
