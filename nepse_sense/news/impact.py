"""Impact scoring rules for news items.

Rules are transparent and deterministic: keyword weights + symbol/watchlist
matches + same-day event bonus. Items with score 0 (no market relevance) are
dropped from briefings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# keyword -> weight. Nepali + English market terms.
KEYWORD_RULES: list[tuple[str, float]] = [
    ("nepse", 25),
    ("नेपसे", 25),
    ("sebon", 25),
    ("सेबोन", 25),
    ("share market", 25),
    ("stock market", 25),
    ("शेयर बजार", 25),
    ("शेयरबजार", 25),
    ("सेयर बजार", 25),
    ("सेयरबजार", 25),
    ("पूँजी बजार", 25),
    ("पुँजी बजार", 25),
    ("पुँजीबजार", 25),
    ("स्टक एक्सचेन्ज", 30),
    ("नेपाल स्टक", 30),
    ("monetary policy", 30),
    ("मौद्रिक नीति", 30),
    ("interest rate", 20),
    ("ब्याजदर", 20),
    ("ब्याज दर", 20),
    ("circuit", 20),
    ("सर्किट", 20),
    ("ipo", 18),
    ("fpo", 18),
    ("dividend", 18),
    ("लाभांश", 18),
    ("bonus share", 18),
    ("बोनस", 18),
    ("right share", 18),
    ("नाफाविभाजन", 18),
    ("अग्रिम शुल्क", 18),
    ("agm", 15),
    ("book closure", 15),
    ("मूल्य अभिलेख", 15),
    ("trading halt", 20),
    ("सूचीबद्ध", 12),
    ("merger", 15),
    ("सम्मिलन", 15),
    ("credit rating", 12),
    ("रेटिङ", 12),
    (" hydropower", 8),
    (" बैंक", 12),
    (" बैंकिङ", 12),
    (" banking", 12),
    (" बीमा", 10),
    ("insurance", 10),
    ("शेयर", 15),
    ("लगानी", 10),
    ("ऋण", 8),
    ("अर्थ मन्त्रालय", 15),
    ("nrb", 20),
    ("राष्ट्र बैंक", 20),
    ("नेपाल राष्ट्र बैंक", 20),
]

HIGH_IMPACT_THRESHOLD = 60.0


@dataclass
class ImpactResult:
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    symbol: str | None = None
    on_watchlist: bool = False
    matched_keywords: list[str] = field(default_factory=list)
    matched: bool = False  # any real market match (not the source bonus)

    @property
    def is_high_impact(self) -> bool:
        return self.score >= HIGH_IMPACT_THRESHOLD

    @property
    def is_relevant(self) -> bool:
        # source weight alone must not make a headline "relevant"
        return self.matched


def match_symbol(headline: str, known_symbols: list[str]) -> str | None:
    """Match a known symbol token in the headline (word-boundary, case-insensitive).

    Nepali-script company names are matched by first 4 chars of the symbol only
    when they appear as a standalone token; this keeps false positives low.
    """
    if not headline or not known_symbols:
        return None
    lower = f" {headline.lower()} "
    for sym in known_symbols:
        if not sym:
            continue
        token = sym.strip().lower()
        if not token:
            continue
        # require non-alphanumeric boundaries around the token
        pattern = rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
        if re.search(pattern, lower):
            return sym.upper()
    return None


def score_news_item(
    headline: str,
    *,
    known_symbols: list[str] | None = None,
    watchlist_symbols: list[str] | None = None,
    events_by_symbol: dict[str, list[date]] | None = None,
    today: date | None = None,
    source_weight: float = 5.0,
) -> ImpactResult:
    """Score a headline. Deterministic, rule-based, explainable."""
    result = ImpactResult()
    text = (headline or "").lower()

    # 1. Symbol match
    symbol = match_symbol(headline, known_symbols or [])
    if symbol:
        result.symbol = symbol
        result.score += 20
        result.matched = True
        result.reasons.append("symbol mention (+20)")

    # 2. Watchlist match (checked against matched symbol OR raw mention)
    watch = {s.upper() for s in (watchlist_symbols or []) if s}
    matched_watch = None
    if symbol and symbol.upper() in watch:
        matched_watch = symbol
    else:
        for w in watch:
            if re.search(rf"(?<![a-z0-9]){re.escape(w.lower())}(?![a-z0-9])", text):
                matched_watch = w
                if not result.symbol:
                    result.symbol = w
                break
    if matched_watch:
        result.on_watchlist = True
        result.matched = True
        result.score += 40
        result.reasons.append("watchlist stock (+40)")

    # 3. Keyword rules (capped so keyword stuffing can't dominate)
    keyword_total = 0.0
    for keyword, weight in KEYWORD_RULES:
        if keyword in text:
            result.matched_keywords.append(keyword)
            keyword_total += weight
    keyword_total = min(keyword_total, 50.0)
    if keyword_total:
        result.score += keyword_total
        result.matched = True
        result.reasons.append(f"keywords {result.matched_keywords} (+{keyword_total:.0f})")

    # 4. Same-day corporate event for the matched symbol
    if result.symbol and events_by_symbol and today:
        dates = events_by_symbol.get(result.symbol.upper(), [])
        if today in dates:
            result.score += 15
            result.matched = True
            result.reasons.append("corporate event today (+15)")

    # 5. Base source weight
    if source_weight:
        result.score += source_weight
        result.reasons.append(f"source weight (+{source_weight:.0f})")

    result.score = float(min(100.0, round(result.score, 1)))
    return result


def rank_items(items: list, max_items: int = 10) -> list:
    """Watchlist stocks first, then impact score descending."""
    ordered = sorted(
        items,
        key=lambda it: (0 if getattr(it, "on_watchlist", False) else 1, -getattr(it, "score", 0.0)),
    )
    return ordered[:max_items]
