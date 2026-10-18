"""PER-17: parsing helpers of the bake-off script (no AI or network calls)."""

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "meme_bakeoff.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("meme_bakeoff", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bakeoff = load()


def test_parses_a_json_answer_even_with_surrounding_text() -> None:
    answer = bakeoff.parse_answer(
        'Sure:\n{"label": "Not meme", "confidence": "HIGH", "rationale": "Runs a DEX.",'
        ' "sources": ["https://example.test"]}'
    )
    assert answer["label"] == "not_meme"
    assert answer["confidence"] == "high"
    assert answer["sources"] == ["https://example.test"]


def test_ac2_no_materials_answer_keeps_the_marker_as_its_source() -> None:
    answer = bakeoff.parse_answer(
        '{"label": "meme", "confidence": "low", "rationale": "No product materials found",'
        ' "sources": []}'
    )
    assert answer["sources"] == [bakeoff.NO_MATERIALS]


def test_unusable_answers_are_flagged_not_guessed() -> None:
    assert "parse_error" in bakeoff.parse_answer("I think it's a meme")
    assert "parse_error" in bakeoff.parse_answer('{"label": "maybe"}')


def test_profile_hides_categories_and_keeps_links_and_contract() -> None:
    profile = bakeoff.profile_from_coingecko(
        {
            "name": "Test Token",
            "symbol": "test",
            "categories": ["Meme"],
            "asset_platform_id": "solana",
            "detail_platforms": {"solana": {"contract_address": "TESTmint111"}},
            "description": {"en": "<p>A <b>test</b> protocol.</p>"},
            "links": {
                "homepage": ["https://test.example", ""],
                "repos_url": {"github": ["https://github.com/test/test"]},
                "twitter_screen_name": "testtoken",
            },
        }
    )
    assert "categories" not in profile
    assert (profile["chain"], profile["contract"]) == ("solana", "TESTmint111")
    assert profile["description"] == "A test protocol."
    assert profile["links"]["homepage"] == ["https://test.example"]
    assert profile["links"]["twitter"] == ["https://x.com/testtoken"]
