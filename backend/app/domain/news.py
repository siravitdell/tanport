"""News text clean-up and de-duplication (pure).

- `repair_mojibake`: some provider texts arrive UTF-8-decoded-as-Latin-1/cp1252
  ("Buffettâ\\u0080\\u0099s"). Only runs that form valid UTF-8 again are repaired; anything
  else is left exactly as it was.
- `headline_key`: a normalized headline (case, punctuation, spacing, a trailing " - Outlet").
- `dedupe`: drop items whose headline matches one already kept or stored: same key, or the
  same words for the most part (Jaccard ≥ 0.8 on word sets of 4+ words). The same story
  from several outlets usually differs in URL but not in headline.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Protocol

# A UTF-8 lead byte (as the Latin-1 char it was misread as), then 1–3 continuation bytes
# misread as Latin-1 C1 controls / Latin-1 symbols or as their cp1252 look-alikes.
_CP1252_CONT = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ"
_MOJIBAKE = re.compile(f"[Â-ô][\u0080-¿{_CP1252_CONT}]{{1,3}}")

NEAR_DUPLICATE = 0.8
MIN_WORDS = 4


def _byte(ch: str) -> int | None:
    try:
        return ch.encode("cp1252")[0]
    except UnicodeEncodeError:
        return ord(ch) if ord(ch) < 256 else None


def _repair(match: re.Match[str]) -> str:
    raw = match.group(0)
    data = [_byte(ch) for ch in raw]
    if any(b is None for b in data):
        return raw
    try:
        return bytes(b for b in data if b is not None).decode("utf-8")
    except UnicodeDecodeError:
        return raw


def repair_mojibake(text: str) -> str:
    return _MOJIBAKE.sub(_repair, text)


_SOURCE_SUFFIX = re.compile(r"\s+[-–—|]\s+[\w .&']{2,40}$")
_NON_WORD = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")


def headline_key(headline: str) -> str:
    text = unicodedata.normalize("NFKC", repair_mojibake(headline)).strip()
    text = _SOURCE_SUFFIX.sub("", text)  # "Nvidia beats - Reuters" → "Nvidia beats"
    text = _NON_WORD.sub(" ", text.lower().replace("’", "'").replace("'", ""))
    return _SPACES.sub(" ", text).strip()


def _words(key: str) -> frozenset[str]:
    return frozenset(key.split())


def is_near_duplicate(a: str, b: str) -> bool:
    """`a`, `b` are headline keys."""
    if a == b:
        return True
    wa, wb = _words(a), _words(b)
    if len(wa) < MIN_WORDS or len(wb) < MIN_WORDS:
        return False
    return len(wa & wb) / len(wa | wb) >= NEAR_DUPLICATE


class HasHeadline(Protocol):
    @property
    def headline(self) -> str: ...

    @property
    def url(self) -> str: ...


def dedupe[T: HasHeadline](
    items: Sequence[T], known_keys: Iterable[str], known_urls: Iterable[str] = ()
) -> list[T]:
    """Keep the first of each story (callers pass items oldest first)."""
    keys = list(known_keys)
    urls = set(known_urls)
    kept: list[T] = []
    for item in items:
        if item.url in urls:
            continue
        key = headline_key(item.headline)
        if not key or any(is_near_duplicate(key, k) for k in keys):
            continue
        kept.append(item)
        keys.append(key)
        urls.add(item.url)
    return kept
