# Role: tests for the 4chan markup cleaner (HTML tags, <wbr>, /pol/ jokes).
# Connects to: formal/markup_regex, formal/cleaning.

from keklab.formal.cleaning import clean_post
from keklab.formal.markup_regex import (
    strip_markup,
    strip_markup_plain,
)


def test_wbr_is_removed_without_inserting_a_space():
    # `<wbr>` is a word-break hint: removing it must not split the word.
    assert strip_markup("students-a<wbr>t-claremont") == (
        "students-at-claremont"
    )
    assert strip_markup_plain("students-a<wbr>t-claremont") == (
        "students-at-claremont"
    )


def test_wbr_forms_are_case_insensitive():
    for raw in ("a<wbr>b", "a<wbr/>b", "a<WBR>b", "a<Wbr />b"):
        assert strip_markup(raw) == "ab"
        assert strip_markup_plain(raw) == "ab"


def test_wbr_is_removed_inside_html_markup():
    raw = (
        '<span class="quote">&gt; quoted</span><br>'
        "body<wbr>text"
    )
    cleaned = strip_markup(raw)
    assert "wbr" not in cleaned
    assert cleaned.split() == [">", "quoted", "bodytext"]


def test_invented_pol_tags_are_preserved():
    # `</kanye>` is part of the post, not markup of the file.
    raw = "he's the greatest troll of ALL TIME </kanye>"
    assert strip_markup(raw) == raw
    assert strip_markup_plain(raw) == raw


def test_real_html_tags_are_stripped():
    assert strip_markup('<a href=" target="_blank">').strip() == ""
    assert strip_markup('<iframe width="560" src="https://x/y"></iframe>ok').strip() == "ok"
    assert strip_markup("<div><b>bold</b></div>").strip() == "bold"
    assert strip_markup("<ul><li>one</li></ul>").strip() == "one"


def test_strip_markup_is_idempotent():
    raw = '<span class="quote">x</span><br>a<wbr>b</a>'
    once = strip_markup(raw)
    assert strip_markup(once) == once


def test_clean_post_removes_wbr_from_a_real_post():
    text_clean, _, _ = clean_post(
        "claremontindependent.com/students-a<wbr>t-claremont"
    )
    assert text_clean == (
        "claremontindependent.com/students-at-claremont"
    )


def test_clean_post_keeps_pol_jokes():
    text_clean, _, _ = clean_post("he's the greatest troll of ALL TIME </kanye>")
    assert "</kanye>" in text_clean
