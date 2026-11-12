from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from keklab.annotation.sampler import (
    FourplebsArchiveClient,
    archive_post_to_canonical,
    collect_archive_candidates,
    parse_index_threads,
    parse_search_posts,
    parse_thread_posts,
    sample_fourplebs,
    sample_rotlk,
)
from keklab.common.io import write_parquet
from keklab.formal.schema import Post

NOW = datetime.now(timezone.utc)


def archive_post(
    num: int,
    thread_num: int,
    timestamp: datetime,
    comment: str,
    *,
    op: bool = False,
    title: str | None = None,
) -> dict:
    return {
        "num": num,
        "thread_num": thread_num,
        "op": 1 if op else 0,
        "timestamp": int(timestamp.timestamp()),
        "comment": comment,
        "title": title,
        "poster_country": "US",
    }


def thread_payload(thread_num: int, posts: list[dict]) -> dict:
    return {
        str(thread_num): {
            "op": posts[0],
            "posts": {str(post["num"]): post for post in posts[1:]},
        }
    }


def index_payload(posts: list[dict]) -> dict:
    return {str(post["num"]): {"op": post} for post in posts}


class FakeArchiveClient:
    def __init__(self, index_pages, threads, searches=None):
        self.index_pages = index_pages
        self.threads = threads
        self.searches = searches or {}

    def index(self, page: int = 1, board: str = "pol"):
        if 1 <= page <= len(self.index_pages):
            return self.index_pages[page - 1]
        return {}

    def thread(self, num, board: str = "pol"):
        return self.threads.get(str(num), {})

    def search(self, text: str, page: int = 1, board: str = "pol"):
        return self.searches.get((text, page), {})


def test_parse_archive_payloads():
    op = archive_post(1, 1, NOW, "op", op=True, title="Title")
    reply = archive_post(2, 1, NOW, ">>1 reply")
    index = index_payload([op])
    thread = thread_payload(1, [op, reply])
    search = {"0": {"posts": [reply]}, "meta": {"page": 1}}

    assert parse_index_threads(index) == [op]
    assert [post["num"] for post in parse_thread_posts(thread)] == [1, 2]

    # A flat thread object and a list of replies are also accepted.
    assert [post["num"] for post in parse_thread_posts({"op": op, "posts": [reply]})] == [1, 2]
    assert [post["num"] for post in parse_search_posts(search)] == [2]


def test_archive_post_maps_to_canonical_shape():
    post = archive_post(2, 1, NOW, "&gt;&gt;1 hello", title="Subject")
    mapped = archive_post_to_canonical(post, thread_num=1)

    assert mapped["no"] == "2"
    assert mapped["resto"] == "1"
    assert mapped["time"] == post["timestamp"]
    assert mapped["com"] == "&gt;&gt;1 hello"
    assert mapped["sub"] == "Subject"
    assert mapped["country"] == "US"


def test_archive_client_falls_back_to_curl(tmp_path, monkeypatch):
    class RejectingClient:
        def get(self, *_args, **_kwargs):
            raise RuntimeError("403 from the archive filter")

    client = FourplebsArchiveClient(cache_dir=tmp_path, http_client=RejectingClient())
    client._curl = "/usr/bin/curl"

    class Result:
        returncode = 0
        stdout = '{"ok": true}'
        stderr = ""

    monkeypatch.setattr(
        "keklab.annotation.sampler.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    assert client._fetch("https://example.test/api") == {"ok": True}


def test_collect_archive_candidates_stops_outside_window():
    recent = archive_post(1, 1, NOW - timedelta(days=10), "recent", op=True)
    old = archive_post(2, 2, NOW - timedelta(days=900), "old", op=True)
    client = FakeArchiveClient(
        index_pages=[index_payload([recent]), index_payload([old])],
        threads={},
    )

    candidates = collect_archive_candidates(client, months=2, max_pages=5)

    assert [candidate["num"] for candidate in candidates] == ["1"]


def test_sample_fourplebs_dedupes_identical_content():
    """Copypasta across threads must not enter the sample twice."""
    first = archive_post(100, 100, NOW - timedelta(days=3), "bump", op=True)
    second = archive_post(200, 200, NOW - timedelta(days=70), "bump", op=True)
    third = archive_post(300, 300, NOW - timedelta(days=40), "unique text", op=True)

    client = FakeArchiveClient(
        index_pages=[index_payload([first, second, third])],
        threads={
            "100": thread_payload(100, [first]),
            "200": thread_payload(200, [second]),
            "300": thread_payload(300, [third]),
        },
    )

    samples = sample_fourplebs(
        random_count=3,
        targeted_count=0,
        months=24,
        seed=1,
        max_pages=2,
        client=client,
    )

    assert len(samples) == 2
    assert len({sample.content_hash for sample in samples}) == 2


def test_sample_fourplebs_builds_random_and_targeted_samples():
    recent_a = archive_post(
        100, 100, NOW - timedelta(days=3), "Random political post", op=True
    )
    reply_a = archive_post(101, 100, NOW - timedelta(days=3), ">>100 I agree")
    recent_b = archive_post(
        200, 200, NOW - timedelta(days=70), "Another post", op=True
    )
    reply_b = archive_post(201, 200, NOW - timedelta(days=70), "reply")

    targeted_op = archive_post(
        300, 300, NOW - timedelta(days=5), "Russia thread", op=True
    )
    targeted_reply = archive_post(
        301, 300, NOW - timedelta(days=5), ">>300 Russia is a menace"
    )

    threads = {
        "100": thread_payload(100, [recent_a, reply_a]),
        "200": thread_payload(200, [recent_b, reply_b]),
        "300": thread_payload(300, [targeted_op, targeted_reply]),
    }
    searches = {("russia", 1): {"0": {"posts": [targeted_reply]}}}

    client = FakeArchiveClient(
        index_pages=[index_payload([recent_a, recent_b])],
        threads=threads,
        searches=searches,
    )

    samples = sample_fourplebs(
        random_count=2,
        targeted_count=1,
        months=24,
        seed=1,
        max_pages=2,
        client=client,
    )

    assert len(samples) == 3
    random_samples = [s for s in samples if s.stratum["reason"] == "random"]
    targeted = [s for s in samples if s.stratum["reason"] == "targeted"]

    assert len(random_samples) == 2
    assert len(targeted) == 1
    assert targeted[0].post_id == "301"
    assert targeted[0].stratum["frame"] == "rusophobia"
    assert targeted[0].context.op is not None
    assert targeted[0].context.op.post_id == "300"
    assert "Russia" in targeted[0].text_clean

    for sample in samples:
        assert sample.source == "fourplebs"
        assert sample.period == "recent_2020_plus"
        assert sample.thread_id in {"100", "200", "300"}
        assert sample.content_hash


def make_post_row(
    post_id: str,
    thread_id: str,
    timestamp: datetime,
    text: str,
    *,
    is_op: bool,
    quotes: list[str] | None = None,
    content_hash: str | None = None,
) -> dict:
    return Post(
        post_id=post_id,
        thread_id=thread_id,
        timestamp_utc=timestamp,
        is_op=is_op,
        subject=None,
        raw_html=text,
        text_clean=text,
        quotes=quotes or [],
        source="kek",
        content_hash=content_hash or f"hash-{post_id}",
        period="hist_2016_2019",
    ).model_dump()


def make_rotlk_parquet(tmp_path):
    rows = [
        make_post_row("1", "t1", datetime(2021, 3, 10, tzinfo=timezone.utc), "general news", is_op=True),
        make_post_row("2", "t1", datetime(2021, 3, 11, tzinfo=timezone.utc), "russia is dangerous", is_op=False, quotes=["1"]),
        make_post_row("3", "t2", datetime(2021, 2, 10, tzinfo=timezone.utc), "economic downturn", is_op=True),
        make_post_row("4", "t2", datetime(2021, 2, 11, tzinfo=timezone.utc), ">>3 reply", is_op=False, quotes=["3"]),
    ]
    path = tmp_path / "canonical.parquet"
    write_parquet(pd.DataFrame(rows), path)
    return path


def test_sample_rotlk_random_stratifies_by_month(tmp_path):
    parquet = make_rotlk_parquet(tmp_path)
    samples = sample_rotlk(
        parquet,
        random_count=2,
        targeted_count=0,
        months=2,
        seed=7,
    )

    assert len(samples) == 2
    assert {sample.source for sample in samples} == {"kek"}
    assert {sample.stratum["month"] for sample in samples} == {"2021-02", "2021-03"}
    assert all(sample.content_hash for sample in samples)


def test_sample_rotlk_dedupes_identical_content(tmp_path):
    rows = [
        make_post_row(
            "1",
            "t1",
            datetime(2021, 3, 10, tzinfo=timezone.utc),
            "bump",
            is_op=True,
            content_hash="hash-bump",
        ),
        make_post_row(
            "2",
            "t2",
            datetime(2021, 3, 11, tzinfo=timezone.utc),
            "bump",
            is_op=True,
            content_hash="hash-bump",
        ),
        make_post_row(
            "3",
            "t3",
            datetime(2021, 3, 12, tzinfo=timezone.utc),
            "unique text",
            is_op=True,
        ),
    ]
    path = tmp_path / "duplicates.parquet"
    write_parquet(pd.DataFrame(rows), path)

    samples = sample_rotlk(
        path,
        random_count=3,
        targeted_count=0,
        months=1,
        seed=7,
    )

    assert len(samples) == 2
    assert len({sample.content_hash for sample in samples}) == 2


def test_sample_rotlk_targeted_uses_seed_terms_and_context(tmp_path):
    parquet = make_rotlk_parquet(tmp_path)
    samples = sample_rotlk(
        parquet,
        random_count=0,
        targeted_count=1,
        months=12,
        seed=7,
    )

    assert len(samples) == 1
    sample = samples[0]
    assert sample.stratum["reason"] == "targeted"
    assert sample.stratum["frame"] == "rusophobia"
    assert "russia" in sample.text_clean.lower()
    assert sample.context.op is not None
    assert sample.context.op.post_id == "1"
