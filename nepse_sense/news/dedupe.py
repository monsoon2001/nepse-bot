"""Headline normalization + dedupe keys for cross-source story deduplication."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date

_NON_ALNUM = re.compile(r"[^a-z0-9\u0900-\u097f]+", re.IGNORECASE)
_WS = re.compile(r"\s+")


def normalize_headline(headline: str) -> str:
    """Normalize a headline for cross-source comparison.

    - Unicode NFKC (folds full-width/punctuation variants)
    - lowercase
    - keep ASCII alphanumerics and Devanagari (Nepali) characters only
    - collapse whitespace
    """
    if not headline:
        return ""
    text = unicodedata.normalize("NFKC", str(headline)).lower()
    text = _NON_ALNUM.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    return text


def headline_key(headline: str, published: date) -> str:
    """Dedupe key: normalized headline + publication date (UTC date)."""
    basis = f"{normalize_headline(headline)}|{published.isoformat()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
