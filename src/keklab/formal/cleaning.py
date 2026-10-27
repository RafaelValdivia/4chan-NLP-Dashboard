# Role: unified cleaning by source (kek/ROTLK vs fourplebs).
# Connects to: formal/markup_regex, formal/normalize, ingest/*.
# ROTLK: minimal/no HTML. 4plebs: HTML present.

from __future__ import annotations

import html
from typing import Literal

from keklab.formal.markup_regex import (
    count_greentext,
    extract_quotes,
    has_html,
    strip_markup,
    strip_markup_plain,
)
from keklab.formal.normalize import normalize_text


def clean_post(text: str, source: Literal["kek", "fourplebs"] = "kek") -> tuple[str, list[str], int]:
    """
    Limpia post según fuente.
    
    Args:
        text: raw_html/com del post
        source: 'kek' (ROTLK, poco HTML) o 'fourplebs' (HTML presente)
    
    Returns:
        (text_clean, quotes, greentext_count)
    """
    if not text:
        return "", [], 0

    if source == "fourplebs":
        # 4plebs siempre puede tener HTML
        stripped = strip_markup(text)
    else:
        # kek/ROTLK: detectar si hay HTML
        if has_html(text):
            stripped = strip_markup(text)
        else:
            stripped = strip_markup_plain(text)

    # Buscar quotes en texto unescaped (>> o &gt;&gt;)
    quotes = extract_quotes(html.unescape(text))
    greentext_count = count_greentext(html.unescape(text))
    text_clean = normalize_text(stripped)
    return text_clean, quotes, greentext_count

