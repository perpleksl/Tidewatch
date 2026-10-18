"""Spike R3 (PER-17): meme-classification bake-off across four model setups.

Runs on GitHub Actions ("Meme bake-off" workflow) against a throwaway database, so the
CostEntry rows are real but disposable. Never point DATABASE_URL at staging or production.

Steps
1. Read docs/spikes/R3-sample.csv (the Owner-approved labels).
2. Fetch each token's CoinGecko profile (description, official links, chain + contract).
   CoinGecko's own categories are left out so the answer isn't given away.
3. Ask each setup to classify every token with the same prompt, through tidewatch.ai only:
   worker (Surplus) x2, reviewer (Surplus) x2, fallback Haiku x1, professor Sonnet x1.
4. Write results to an output folder: results CSV, profiles JSON, summary JSON.

Cost guard: stops starting new calls once logged AI spend reaches MAX_SPEND_USD.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tidewatch.ai.client import AiResult, AiUnavailable, professor_deep, reviewer, worker
from tidewatch.ai.providers import Prompt, ProviderUnavailable, surplus_model_ids
from tidewatch.db.models import CostEntry
from tidewatch.db.session import make_engine
from tidewatch.db.settings import get_setting, update_setting

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/{id}"
COINGECKO_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
MAX_SPEND_USD = Decimal("10")
NO_MATERIALS = "No product materials found"

INSTRUCTIONS = """You classify crypto tokens for a research tool that excludes meme coins.

Definition (PRD 3.2): a token is a MEME if its value proposition is mainly culture, humour,
a mascot, a celebrity or community hype, with no real product, protocol or network that the
token is needed for. It is NOT_MEME if it powers or governs a real product, protocol or network,
even if its branding is playful.

Use ONLY the profile you are given. Cite sources only from the profile's links; never invent
URLs. If the profile contains no product materials (no description of a product and no
website/docs/code links), answer MEME with low confidence and the rationale
"No product materials found".

Answer with JSON only, no other text:
{"label": "meme" | "not_meme", "confidence": "high" | "low",
 "rationale": "1-3 sentences", "sources": ["https://..."]}"""


@dataclass(frozen=True)
class Setup:
    name: str
    tier: str  # worker | reviewer | anthropic
    model_override: str | None
    runs: int


SETUPS = (
    Setup("worker_surplus", "worker", None, 2),
    Setup("reviewer_surplus", "reviewer", None, 2),
    Setup("fallback_haiku", "anthropic", "claude-haiku-5-5", 1),
    Setup("professor_sonnet", "anthropic", "claude-sonnet-5-5", 1),
)


def clean_text(text: str, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def profile_from_coingecko(body: dict[str, Any]) -> dict[str, Any]:
    links = body.get("links") or {}

    def urls(value: Any) -> list[str]:
        items = value if isinstance(value, list) else [value]
        return [u for u in items if isinstance(u, str) and u.startswith("http")]

    repos = (links.get("repos_url") or {}).get("github") or []
    twitter = links.get("twitter_screen_name")
    platforms = body.get("detail_platforms") or {}
    chain, contract = "native", ""
    for platform, detail in platforms.items():
        address = (detail or {}).get("contract_address") or ""
        if platform and address:
            chain, contract = platform, address
            break
    return {
        "name": body.get("name"),
        "symbol": str(body.get("symbol") or "").upper(),
        "chain": chain if contract else (body.get("asset_platform_id") or "native"),
        "contract": contract or "native",
        "description": clean_text((body.get("description") or {}).get("en", ""), 1500),
        "links": {
            "homepage": urls(links.get("homepage")),
            "whitepaper": urls(links.get("whitepaper")),
            "docs_and_explorers": urls(links.get("blockchain_site"))[:3],
            "github": urls(repos)[:3],
            "twitter": [f"https://x.com/{twitter}"] if twitter else [],
        },
    }


def fetch_profiles(sample: list[dict[str, str]], key: str, out: Path) -> dict[str, Any]:
    cache = out / "profiles.json"
    if cache.exists():
        return dict(json.loads(cache.read_text()))
    profiles: dict[str, Any] = {}
    with httpx.Client(timeout=30.0, headers={"x-cg-demo-api-key": key}) as http:
        for row in sample:
            cg_id = row["coingecko_id"]
            try:
                for attempt in range(4):
                    response = http.get(
                        COINGECKO_URL.format(id=cg_id),
                        params={
                            "localization": "false",
                            "tickers": "false",
                            "market_data": "false",
                        },
                    )
                    if response.status_code == 429:
                        time.sleep(20 * (attempt + 1))
                        continue
                    break
                if response.status_code == 404:
                    # Unknown ID: look the coin up by name and keep a match with the same ticker.
                    found = http.get(COINGECKO_SEARCH_URL, params={"query": row["name"]}).json()
                    match = next(
                        (
                            c["id"]
                            for c in found.get("coins", [])
                            if str(c.get("symbol", "")).upper() == row["ticker_display"].upper()
                        ),
                        None,
                    )
                    if match:
                        time.sleep(2.2)
                        response = http.get(
                            COINGECKO_URL.format(id=match),
                            params={
                                "localization": "false",
                                "tickers": "false",
                                "market_data": "false",
                            },
                        )
                if response.status_code == 200:
                    profiles[cg_id] = profile_from_coingecko(response.json())
                else:
                    profiles[cg_id] = {"error": f"CoinGecko HTTP {response.status_code}"}
            except Exception as exc:  # one bad profile must not stop the run
                profiles[cg_id] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"profile {row['n']:>3} {cg_id}: {profiles[cg_id].get('error', 'ok')}")
            time.sleep(2.2)  # stay under the Demo plan's rate limit
    cache.write_text(json.dumps(profiles, indent=1))
    return profiles


def prompt_for(row: dict[str, str], profile: dict[str, Any]) -> Prompt:
    shown = {k: v for k, v in profile.items() if k != "error"} or {
        "name": row["name"],
        "symbol": row["ticker_display"],
        "description": "",
        "links": {},
    }
    return Prompt(
        user="Token profile:\n" + json.dumps(shown, indent=1),
        cached_context=INSTRUCTIONS,
        max_tokens=1500,  # room for models that reason before answering
    )


def _json_candidates(text: str) -> list[str]:
    """Every balanced {...} block in the text, last first (the final answer usually comes last)."""
    found: list[str] = []
    depth, start, in_string, escaped = 0, -1, False, False
    for i, ch in enumerate(text):
        if in_string:
            escaped = (ch == "\\") and not escaped
            if ch == '"' and not escaped:
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                found.append(text[start : i + 1])
    return list(reversed(found))


def parse_answer(text: str) -> dict[str, Any]:
    # Reasoning models may wrap thoughts in <think>...</think>; ignore that part.
    visible = re.sub(r"<think>.*?</think>", " ", text or "", flags=re.DOTALL)
    data: Any = None
    for candidate in _json_candidates(visible):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "label" in parsed:
            data = parsed
            break
    if data is None:
        return {
            "parse_error": "no JSON answer found",
            "raw_answer": re.sub(r"\s+", " ", text or "")[:400],
        }
    label = str(data.get("label", "")).lower().replace("-", "_").replace(" ", "_")
    confidence = str(data.get("confidence", "")).lower()
    sources = [s for s in data.get("sources") or [] if isinstance(s, str)]
    rationale = str(data.get("rationale", "")).strip()
    if label not in ("meme", "not_meme"):
        return {"parse_error": f"unknown label {label!r}"}
    return {
        "label": label,
        "confidence": confidence if confidence in ("high", "low") else "low",
        "rationale": rationale,
        "sources": sources or ([NO_MATERIALS] if NO_MATERIALS.lower() in rationale.lower() else []),
    }


def spent(sessions: sessionmaker[Session]) -> Decimal:
    with sessions() as s:
        return Decimal(s.scalar(select(func.coalesce(func.sum(CostEntry.amount_usd), 0))) or 0)


def call(sessions: sessionmaker[Session], setup: Setup, prompt: Prompt) -> AiResult:
    with sessions.begin() as s:
        if setup.tier == "worker":
            return worker(s, prompt)
        if setup.tier == "reviewer":
            return reviewer(s, prompt)
        return professor_deep(s, prompt)  # model set per setup in Settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default="../docs/spikes/R3-sample.csv")
    parser.add_argument("--out", default="bakeoff-output")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--threads", type=int, default=6)
    args = parser.parse_args()

    for name in ("DATABASE_URL", "SURPLUS_API_KEY", "ANTHROPIC_API_KEY", "COINGECKO_API_KEY"):
        if not os.environ.get(name):
            print(f"Missing environment variable {name}", file=sys.stderr)
            return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(args.sample, newline="") as f:
        sample = list(csv.DictReader(f))[: args.limit]

    summary: dict[str, Any] = {"surplus_catalog_check": {}}
    try:
        catalog = surplus_model_ids()
        for model in ("deepseek-v4.1-flash", "deepseek-v4-pro-0813"):
            summary["surplus_catalog_check"][model] = model in catalog
        summary["surplus_deepseek_models"] = [m for m in catalog if "deepseek" in m.lower()]
    except Exception as exc:  # a catalog problem must not stop the bake-off
        summary["surplus_catalog_check"] = {"error": f"{type(exc).__name__}: {exc}"}
    print("Surplus catalog:", json.dumps(summary["surplus_catalog_check"]))
    write_outputs(out, [], summary)

    profiles = fetch_profiles(sample, os.environ["COINGECKO_API_KEY"], out)
    sessions = sessionmaker(make_engine())
    results: list[dict[str, Any]] = []
    stopped = False

    for setup in SETUPS:
        if setup.model_override:
            with sessions.begin() as s:
                update_setting(
                    s,
                    "ai.tier.professor_deep",
                    {"provider": "anthropic", "model": setup.model_override},
                )
        before = spent(sessions)
        for run in range(1, setup.runs + 1):

            def one(row: dict[str, str], setup: Setup = setup, run: int = run) -> dict[str, Any]:
                base = {
                    "n": row["n"],
                    "coingecko_id": row["coingecko_id"],
                    "setup": setup.name,
                    "run": run,
                }
                if spent(sessions) >= MAX_SPEND_USD:
                    return {**base, "error": "skipped: spend limit reached"}
                try:
                    result = call(sessions, setup, prompt_for(row, profiles[row["coingecko_id"]]))
                except (AiUnavailable, ProviderUnavailable) as exc:
                    cause = exc.__cause__
                    detail = f" ({type(cause).__name__}: {cause})" if cause else ""
                    return {**base, "error": f"AI unavailable: {exc}{detail}"[:300]}
                except Exception as exc:
                    return {**base, "error": f"{type(exc).__name__}: {exc}"[:300]}
                answer = parse_answer(result.text)
                return {
                    **base,
                    "provider": result.provider,
                    "model": result.model,
                    "used_fallback": result.used_fallback,
                    "cost_usd": str(result.cost_usd),
                    **{k: (json.dumps(v) if isinstance(v, list) else v) for k, v in answer.items()},
                }

            with ThreadPoolExecutor(max_workers=args.threads) as pool:
                batch = list(pool.map(one, sample))
            results += batch
            done = sum(1 for r in batch if r.get("label"))
            print(f"{setup.name} run {run}: {done}/{len(batch)} answered")
        summary.setdefault("cost_usd", {})[setup.name] = str(spent(sessions) - before)
        write_outputs(out, results, summary)
        if spent(sessions) >= MAX_SPEND_USD:
            stopped = True
            break

    with sessions() as s:
        tiers = s.scalars(select(CostEntry.model).distinct()).all()
        summary["models_billed"] = sorted(m for m in tiers if m)
        professor = get_setting(s, "ai.tier.professor_deep")
        summary["professor_setting_at_end"] = {
            "provider": professor.provider,
            "model": professor.model,
        }
    summary["total_cost_usd"] = str(spent(sessions))
    summary["stopped_at_spend_limit"] = stopped

    write_outputs(out, results, summary)
    print(json.dumps(summary, indent=1))
    return 0


FIELDS = [
    "n", "coingecko_id", "setup", "run", "provider", "model", "used_fallback", "label",
    "confidence", "rationale", "sources", "cost_usd", "parse_error", "raw_answer", "error",
]  # fmt: skip


def write_outputs(out: Path, results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    """Save what we have so far, so a later failure never loses earlier results."""
    with open(out / "R3-results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))


def run_safely() -> int:
    """Run main(); on a crash, save the full error into the output folder (uploaded by CI)."""
    try:
        return main()
    except Exception:
        report = traceback.format_exc()
        print(report, file=sys.stderr)
        out = Path(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), ""))
        if "--out" in sys.argv:
            out = Path(sys.argv[sys.argv.index("--out") + 1])
        out = out if str(out) not in ("", ".") else Path("bakeoff-output")
        out.mkdir(parents=True, exist_ok=True)
        (out / "error.txt").write_text(report)
        return 1


if __name__ == "__main__":
    sys.exit(run_safely())
