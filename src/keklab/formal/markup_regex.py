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
# Word-break hint: HTML-only noise that survives the generic tag list.
WBR_RE = re.compile(r"<wbr\s*/?>", flags=re.IGNORECASE)
# Blockquotes
BLOCKQUOTE_RE = re.compile(r"<blockquote.*?>.*?</blockquote>", flags=re.IGNORECASE | re.DOTALL)
# Real HTML tags. This is an explicit whitelist on purpose: 4chan posts also
# contain invented tags that are part of the joke (`</kanye>`), and a generic
# `<[^>]+>` rule would delete the text along with the markup. `wbr` is not in
# this list because it is a word-break hint, not a separator: it is removed
# without inserting a space (see `WBR_RE`).
HTML_TAGS_RE = re.compile(
    r"</?(?:a|abbr|acronym|address|area|article|aside|audio|b|base|bdi|bdo|big|"
    r"blockquote|body|br|button|canvas|caption|center|cite|code|col|colgroup|"
    r"data|datalist|dd|del|details|dfn|dialog|div|dl|dt|em|embed|fieldset|"
    r"figcaption|figure|font|footer|form|h1|h2|h3|h4|h5|h6|head|header|hgroup|"
    r"hr|html|i|iframe|img|input|ins|kbd|label|legend|li|link|main|map|mark|"
    r"marquee|menu|meta|nav|noframes|noscript|object|ol|optgroup|option|"
    r"output|p|param|picture|pre|progress|q|rp|rt|ruby|s|samp|script|section|"
    r"select|small|source|span|strike|strong|style|sub|summary|sup|svg|table|"
    r"tbody|td|template|textarea|tfoot|th|thead|time|title|tr|track|u|ul|var|"
    r"video)\b[^>]*>",
    flags=re.IGNORECASE,
)


def has_html(text: str) -> bool:
    if not text:
        return False
    return bool(HTML_TAG_RE.search(text) or HTML_ENTITY_RE.search(text))


def extract_quotes(text: str) -> list[str]:
    if not text:
        return []
    return QUOTE_RE.findall(html.unescape(text))


def count_greentext(text: str) -> int:
    if not text:
        return 0
    # `<br>` is a line boundary in raw 4chan HTML, so normalize it before
    # looking for lines that start with `>`.
    normalized = BR_RE.sub("\n", html.unescape(text))
    return len(GREENTEXT_RE.findall(normalized))


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
    t = WBR_RE.sub("", t)
    t = HTML_TAGS_RE.sub(" ", t)
    return t


def strip_markup_plain(text: str) -> str:
    """Para casos sin HTML: desescapa y quita el ruido de `<wbr>`."""
    if not text:
        return ""
    t = html.unescape(text)
    t = WBR_RE.sub("", t)
    t = HTML_TAGS_RE.sub(" ", t)
    return t
