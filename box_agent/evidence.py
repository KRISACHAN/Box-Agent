"""Shared URL normalization and evidence extraction helpers."""

from __future__ import annotations

import re
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["extract_http_urls", "normalize_search_url"]

_URL_TRACKING_PARAMS: Final[set[str]] = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}
_HTTP_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"https?://[^\s<>\"'\]\[{}()]+",
    re.IGNORECASE,
)


def normalize_search_url(value: Any) -> str:
    """Normalize a URL for evidence identity and duplicate detection."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.casefold()

    query_items = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        key_lower = key.casefold()
        if key_lower.startswith("utm_") or key_lower in _URL_TRACKING_PARAMS:
            continue
        query_items.append((key, val))
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            parts.path.rstrip("/") or parts.path,
            urlencode(query_items, doseq=True),
            "",
        )
    )


def extract_http_urls(value: Any) -> set[str]:
    """Return normalized HTTP(S) URLs recursively contained in ``value``."""
    if isinstance(value, str):
        return {
            normalized
            for match in _HTTP_URL_RE.findall(value)
            if (normalized := normalize_search_url(match.rstrip(".,;:!?，。；：！？")))
        }
    if isinstance(value, dict):
        urls: set[str] = set()
        for item in value.values():
            urls.update(extract_http_urls(item))
        return urls
    if isinstance(value, (list, tuple, set)):
        urls: set[str] = set()
        for item in value:
            urls.update(extract_http_urls(item))
        return urls
    return set()
