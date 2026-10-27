# Role: normalization (Unicode, whitespace, URLs, emojis, codified jargon).
# Connects to: formal/cleaning.

from __future__ import annotations

import re
import unicodedata

URL_RE = re.compile(r"https?://\S+|www\.\S+")
WS_RE = re.compile(r"\s+")
MULTI_PUNCT_RE = re.compile(r"([!?.]){2,}")


def normalize_unicode(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text)


def normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    return WS_RE.sub(" ", text).strip()


def strip_urls(text: str, repl: str = " ") -> str:
    if not text:
        return ""
    return URL_RE.sub(repl, text)


def normalize_punct(text: str) -> str:
    if not text:
        return ""
    return MULTI_PUNCT_RE.sub(r"\1", text)


def normalize_text(text: str) -> str:
    """Pipeline completo de normalización."""
    t = normalize_unicode(text)
    t = strip_urls(t)
    t = normalize_punct(t)
    t = normalize_whitespace(t)
    return t
