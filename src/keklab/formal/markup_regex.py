# Role: regex for 4chan /pol/ markup (quotes, greentext, spoilers, backlinks).
# Connects to: formal/cleaning, formal/features.
# Maneja: ROTLK (poco HTML) vs 4plebs (HTML presente)

from __future__ import annotations

import html
import re

# Detección HTML
HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_ENTITY_RE = re.compile(r"&[a-zA-Z0-9#]+;")

# Citas: >>12345
QUOTE_RE = re.compile(r">>(\d+)")
# Greentext: líneas que empiezan con > pero no >>
GREENTEXT_RE = re.compile(r"(?m)^\s*>(?!>)(.+)$")
# Spoilers
SPOILER_RE = re.compile(r"\[spoiler\].*?\[/spoiler\]", flags=re.IGNORECASE | re.DOTALL)
SPOILER_HTML_RE = re.compile(r"<span[^>]+class=['\"]spoiler['\"][^>]*>.*?</span>", flags=re.IGNORECASE | re.DOTALL)
# Backlinks/citas con link
BACKLINK_RE = re.compile(r"<a[^>]*quotelink[^>]*>.*?</a>", flags=re.IGNORECASE | re.DOTALL)
# Saltos de línea
BR_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
# Blockquotes
BLOCKQUOTE_RE = re.compile(r"<blockquote.*?>.*?</blockquote>", flags=re.IGNORECASE | re.DOTALL)
# Otros tags comunes
EXTRA_TAGS_RE = re.compile(r"</?(?:span|div|b|i|strong|em|s|u)[^>]*>", flags=re.IGNORECASE)


def has_html(text: str) -> bool:
    if not text:
        return False
    return bool(HTML_TAG_RE.search(text) or HTML_ENTITY_RE.search(text))


def extract_quotes(text: str) -> list[str]:
    if not text:
        return []
    return QUOTE_RE.findall(text)


def count_greentext(text: str) -> int:
    if not text:
        return 0
    return len(GREENTEXT_RE.findall(text))


def strip_markup(text: str) -> str:
    """
    Elimina markup HTML/BBCode de 4chan.
    Funciona tanto si hay HTML como si no (operaciones son idempotentes).
    """
    if not text:
        return ""
    t = html.unescape(text)
    t = SPOILER_RE.sub(" ", t)
    t = SPOILER_HTML_RE.sub(" ", t)
    t = BACKLINK_RE.sub(" ", t)
    t = BLOCKQUOTE_RE.sub(" ", t)
    t = BR_RE.sub("\n", t)
    t = EXTRA_TAGS_RE.sub(" ", t)
    return t


def strip_markup_plain(text: str) -> str:
    """Para casos sin HTML, solo limpiar espacios extra."""
    if not text:
        return ""
    t = html.unescape(text)
    return t
