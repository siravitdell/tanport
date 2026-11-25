from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.domain.news import dedupe, headline_key, is_near_duplicate, repair_mojibake

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "finnhub"


@pytest.mark.parametrize(
    ("raw", "fixed"),
    [
        ("Buffettâ\u0080\u0099s 1999 framework", "Buffett’s 1999 framework"),  # C1 form
        ("Buffettâ€™s", "Buffett’s"),  # cp1252 form (â€™)
        ("cafÃ© and naÃ¯ve", "café and naïve"),  # 2-byte chars
        ("â\u0080\u009cquotedâ\u0080\u009d", "“quoted”"),
        # left alone: plain text, real accents, real curly quotes, broken sequences
        ("Nvidia beats estimates", "Nvidia beats estimates"),
        ("Nestlé à Paris", "Nestlé à Paris"),
        ("It’s “fine”", "It’s “fine”"),
        ("â\u0080 alone", "â\u0080 alone"),
        ("ไทย ภาษา", "ไทย ภาษา"),
    ],
)
def test_repair_mojibake(raw: str, fixed: str) -> None:
    assert repair_mojibake(raw) == fixed


def test_repairs_the_recorded_seekingalpha_item() -> None:
    items = json.loads((FIXTURES / "company_news_VOO.json").read_text(encoding="utf-8"))
    broken = [i for i in items if "â\u0080" in i["summary"]]
    assert broken, "fixture should contain a double-encoded summary"
    for item in broken:
        repaired = repair_mojibake(item["summary"])
        assert "â\u0080" not in repaired
        assert "’" in repaired


@pytest.mark.parametrize(
    ("headline", "key"),
    [
        ("Nvidia Beats Estimates; Stock Jumps!", "nvidia beats estimates stock jumps"),
        ("Nvidia beats estimates - Reuters", "nvidia beats estimates"),
        ("Nvidia's   CEO  speaks", "nvidias ceo speaks"),
        ("Nvidia’s CEO speaks", "nvidias ceo speaks"),
        ("Ｎｖｉｄｉａ ＡＩ", "nvidia ai"),  # full-width (NFKC)
        ("!!!", ""),
    ],
)
def test_headline_key(headline: str, key: str) -> None:
    assert headline_key(headline) == key


@pytest.mark.parametrize(
    ("a", "b", "dup"),
    [
        ("nvidia beats estimates stock jumps", "nvidia beats estimates stock jumps", True),
        # one word different out of six: same story
        (
            "nvidia beats third quarter estimates shares jump",
            "nvidia beats third quarter estimates shares rise",
            False,  # 6/8 = 0.75 < 0.8
        ),
        (
            "nvidia beats third quarter revenue estimates as shares jump",
            "nvidia beats third quarter revenue estimates as shares rise",
            True,  # 8/10 = 0.8
        ),
        ("nvidia up", "nvidia up today", False),  # too short to call
        ("dow jones futures fall techs tumble", "nvidia earnings preview what to expect", False),
    ],
)
def test_near_duplicates(a: str, b: str, dup: bool) -> None:
    assert is_near_duplicate(a, b) is dup


@dataclass(frozen=True)
class Item:
    headline: str
    url: str


def test_dedupe_keeps_the_first_of_each_story() -> None:
    items = [
        Item("Nvidia beats third quarter revenue estimates as shares jump", "u1"),
        Item("Nvidia Beats Third-Quarter Revenue Estimates as Shares Jump - Yahoo", "u2"),
        Item("Nvidia beats third quarter revenue estimates as shares rise", "u3"),
        Item("Fed minutes due today", "u4"),
        Item("Something else entirely", "u1"),  # URL already kept
        Item("Old story already stored for this ticker", "u5"),
        Item("Seen URL", "stored-url"),
        Item("???", "u6"),  # nothing left after normalizing
    ]
    kept = dedupe(
        items,
        known_keys=["old story already stored for this ticker"],
        known_urls=["stored-url"],
    )
    assert [i.url for i in kept] == ["u1", "u4"]
