"""Column mapping (spec 10.2): header normalization, signature, synonym suggestions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

CORE_TARGETS = ("part_number", "part_name", "description", "revision")

SYNONYMS: dict[str, tuple[str, ...]] = {
    "part_number": ("part_number", "part_no", "partno", "pn", "part", "item", "item_no", "item_number",
                    "user_number", "user_no", "novo_pn"),
    "part_name": ("part_name", "name", "item_name", "title", "short_description"),
    "description": ("description", "desc", "desc1", "long_description", "details"),
    "revision": ("revision", "rev", "rev_level", "revision_level"),
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_header(header: str) -> str:
    """Lowercase, trim, non-alphanumerics -> '_', repeats collapsed (edge underscores dropped)."""
    return _NON_ALNUM.sub("_", header.strip().lower()).strip("_")


def signature(headers: Iterable[str]) -> str:
    """sha256 of the normalized headers, sorted, joined by newlines."""
    return hashlib.sha256("\n".join(sorted(normalize_header(h) for h in headers)).encode("utf-8")).hexdigest()


def suggest(headers: list[str], custom: list[tuple[str, str]]) -> dict[str, str | None]:
    """header -> target (core key or custom key) or None (Ignore). Each target is used by one column only;
    the first matching column wins."""
    lookup: dict[str, str] = {}
    for target, names in SYNONYMS.items():
        for n in names:
            lookup.setdefault(n, target)
    for key, label in custom:
        lookup.setdefault(normalize_header(key), key)
        lookup.setdefault(normalize_header(label), key)
    used: set[str] = set()
    out: dict[str, str | None] = {}
    for h in headers:
        target = lookup.get(normalize_header(h))
        if target and target not in used:
            out[h] = target
            used.add(target)
        else:
            out[h] = None
    return out
