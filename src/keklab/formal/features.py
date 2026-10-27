# Role: structural features from markup/AST.
# Connects to: formal/markup_regex, formal/glc_grammar, ingest/*.
# Features: profundidad_anidamiento, n_citas, tags_usados, thread-level features

from __future__ import annotations

from collections import defaultdict

from keklab.formal.markup_regex import count_greentext, extract_quotes


def post_structural_features(text: str) -> dict[str, int]:
    """Features estructurales a nivel post."""
    if not text:
        return {"quote_count": 0, "greentext_count": 0, "cite_depth_max": 0}
    quotes = extract_quotes(text)
    return {
        "quote_count": len(quotes),
        "greentext_count": count_greentext(text),
        "cite_depth_max": 0,  # TODO: calcular desde AST GLC
    }


def thread_features(posts_html: list[str]) -> dict[str, int]:
    """Features a nivel hilo calculados sobre todos los posts."""
    if not posts_html:
        return {"thread_depth": 0, "thread_cite_count": 0, "thread_greentext_count": 0}
    all_quotes = []
    all_greentext = 0
    for t in posts_html:
        if not t:
            continue
        all_quotes.extend(extract_quotes(t))
        all_greentext += count_greentext(t)
    return {
        "thread_depth": len(posts_html),
        "thread_cite_count": len(set(all_quotes)),
        "thread_greentext_count": all_greentext,
    }
