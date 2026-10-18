"""Spike R2 (PER-16): how many X posts mentioning a term can a history provider return?

Default: posts mentioning "nullmask" from 20 Sep to 5 Oct 2026 (the $MASK move), via
twitterapi.io's advanced search. Nothing is saved anywhere; it only prints counts.

Run (from backend/):
    X_HISTORY_API_KEY=... uv run python scripts/x_history_probe.py
    X_HISTORY_API_KEY=... uv run python scripts/x_history_probe.py --term nullmask \
        --start 2026-09-20 --end 2026-10-05 --max-pages 100

Or on GitHub without a terminal: Actions → "X history probe" → Run workflow (uses the
X_HISTORY_API_KEY repository secret).

Cost guard: at most --max-pages pages of up to 20 posts each. At twitterapi.io's listed
$0.15 per 1,000 posts, the default 100 pages cost at most about $0.30.
"""

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx

ENV_VAR = "X_HISTORY_API_KEY"
SEARCH_URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"


@dataclass(frozen=True)
class ProbeResult:
    posts: int
    pages: int
    first_seen: datetime | None
    last_seen: datetime | None
    stopped_at_page_limit: bool


def build_query(term: str, start: date, end: date) -> str:
    """Posts mentioning `term` from the start of `start` to the end of `end` (UTC)."""
    since = int(datetime.combine(start, time.min, tzinfo=UTC).timestamp())
    until = int(datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC).timestamp())
    return f"{term} since_time:{since} until_time:{until}"


def _parse_created(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return None


def probe(
    api_key: str,
    term: str,
    start: date,
    end: date,
    max_pages: int,
    http: httpx.Client,
    log: Callable[[str], None] = print,
) -> ProbeResult:
    query = build_query(term, start, end)
    cursor = ""
    posts = pages = 0
    seen: list[datetime] = []
    has_next = True
    while has_next and pages < max_pages:
        response = http.get(
            SEARCH_URL,
            params={"query": query, "queryType": "Latest", "cursor": cursor},
            headers={"X-API-Key": api_key},
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"provider answered HTTP {response.status_code}: {response.text[:200]}"
            )
        body: dict[str, Any] = response.json()
        tweets = body.get("tweets") or []
        posts += len(tweets)
        pages += 1
        seen += [d for d in (_parse_created(t.get("createdAt")) for t in tweets) if d]
        has_next = bool(body.get("has_next_page")) and bool(body.get("next_cursor"))
        cursor = str(body.get("next_cursor") or "")
        if pages % 10 == 0:
            log(f"  … {pages} pages, {posts} posts so far")
    return ProbeResult(
        posts=posts,
        pages=pages,
        first_seen=min(seen) if seen else None,
        last_seen=max(seen) if seen else None,
        stopped_at_page_limit=has_next and pages >= max_pages,
    )


def main(argv: list[str] | None = None, http: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--term", default="nullmask")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 9, 20))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 5))
    parser.add_argument("--max-pages", type=int, default=100)
    args = parser.parse_args(argv)

    api_key = os.environ.get(ENV_VAR, "").strip()
    if not api_key:
        print(
            f"No API key found. Set the {ENV_VAR} environment variable to your twitterapi.io "
            f"key (on GitHub: add a repository secret named {ENV_VAR}), then run again.",
            file=sys.stderr,
        )
        return 2

    period = f"{args.start} to {args.end} (UTC)"
    print(f'Searching "{args.term}" from {period}, up to {args.max_pages} pages…')
    client = http or httpx.Client(timeout=30.0)
    try:
        result = probe(api_key, args.term, args.start, args.end, args.max_pages, client)
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"Probe failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if http is None:
            client.close()

    print(f"Posts found: {result.posts} (in {result.pages} pages)")
    if result.first_seen and result.last_seen:
        print(f"Oldest: {result.first_seen.isoformat()}  Newest: {result.last_seen.isoformat()}")
    if result.stopped_at_page_limit:
        print(f"Stopped at the {args.max_pages}-page limit; there are more posts.")
    print("Nothing was saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
