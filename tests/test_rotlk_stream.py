from __future__ import annotations

import io
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from keklab.annotation.sampler import _windowed, sample_rotlk_stream
from keklab.annotation.schema import SamplePost
from keklab.common.io import count_ndjson_lines, iter_ndjson


def _epoch(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def _thread(
    post_id: int,
    timestamp: int,
    com: str,
    *,
    replies: tuple[tuple[int, int, str], ...] = (),
) -> dict:
    posts = [{"no": post_id, "time": timestamp, "resto": 0, "com": com}]
    for reply_id, reply_time, reply_com in replies:
        posts.append(
            {
                "no": reply_id,
                "time": reply_time,
                "resto": post_id,
                "com": reply_com,
            }
        )
    return {"posts": posts}


THREADS = [
    _thread(
        1,
        _epoch(2021, 1, 10),
        "OP general news",
        replies=((2, _epoch(2021, 1, 11), "&gt;&gt;1 russia is dangerous"),),
    ),
    _thread(3, _epoch(2021, 2, 10), "china trade policy"),
    _thread(4, _epoch(2021, 3, 10), "we must accelerate the collapse"),
    _thread(5, _epoch(2021, 3, 20), "", replies=()),
    _thread(6, _epoch(2021, 3, 25), "a plain post about the weather"),
]


def _ndjson(threads) -> str:
    return "\n".join(json.dumps(thread) for thread in threads) + "\n"


def _tar_bytes(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, text in members.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _compress_zstd(data: bytes) -> bytes:
    try:
        from compression import zstd

        return zstd.compress(data)
    except ImportError:
        pass

    try:
        result = subprocess.run(
            ["zstd", "-q", "-c"],
            input=data,
            capture_output=True,
            check=True,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        pytest.skip(f"no zstd compressor available: {exc}")


def _write_tar_zst(path: Path, members: dict[str, str]) -> Path:
    path.write_bytes(_compress_zstd(_tar_bytes(members)))
    return path


def test_iter_ndjson_reads_tar_zst(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS[:2])},
    )

    assert [thread["posts"][0]["no"] for thread in iter_ndjson(path)] == [1, 3]
    assert count_ndjson_lines(path) == 2


def test_iter_ndjson_reads_multiple_tar_members(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {
            "first.ndjson": _ndjson(THREADS[:1]),
            "second.jsonl": _ndjson(THREADS[1:2]),
        },
    )

    assert [thread["posts"][0]["no"] for thread in iter_ndjson(path)] == [1, 3]


def test_iter_ndjson_skips_malformed_tar_lines(tmp_path):
    content = _ndjson(THREADS[:1]) + "not-json\n" + _ndjson(THREADS[1:2])
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": content},
    )

    assert [thread["posts"][0]["no"] for thread in iter_ndjson(path)] == [1, 3]


def test_iter_ndjson_reads_zstd_ndjson(tmp_path):
    path = tmp_path / "threads.ndjson.zst"
    path.write_bytes(_compress_zstd(_ndjson(THREADS[:2]).encode("utf-8")))

    assert [thread["posts"][0]["no"] for thread in iter_ndjson(path)] == [1, 3]


def test_stream_random_stratifies_by_month(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS)},
    )

    samples = sample_rotlk_stream(
        path,
        random_count=3,
        targeted_count=0,
        months=12,
        seed=7,
    )

    assert len(samples) == 3
    assert {sample.source for sample in samples} == {"kek"}
    assert {sample.stratum["month"] for sample in samples} == {
        "2021-01",
        "2021-02",
        "2021-03",
    }
    assert all(sample.content_hash for sample in samples)
    assert all(sample.text_clean.strip() for sample in samples)


def test_stream_targeted_uses_terms_and_context(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS)},
    )

    samples = sample_rotlk_stream(
        path,
        random_count=0,
        targeted_count=3,
        months=12,
        seed=7,
    )

    assert len(samples) == 3
    assert {sample.stratum["frame"] for sample in samples} == {
        "rusophobia",
        "sinophobia",
        "accelerationism",
    }
    by_frame = {sample.stratum["frame"]: sample for sample in samples}

    russia = by_frame["rusophobia"]
    assert "russia" in russia.text_clean.lower()
    assert russia.context.op is not None
    assert russia.context.op.post_id == "1"
    assert {parent.post_id for parent in russia.context.parents} == {"1"}


def test_stream_include_empty(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS)},
    )

    samples = sample_rotlk_stream(
        path,
        random_count=0,
        targeted_count=0,
        months=12,
        seed=7,
        include_empty=1,
    )

    assert len(samples) == 1
    assert samples[0].text_clean == ""
    assert samples[0].stratum["reason"] == "random_empty"


def test_stream_limit_threads(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS)},
    )

    samples = sample_rotlk_stream(
        path,
        random_count=1,
        targeted_count=0,
        months=12,
        seed=7,
        limit_threads=1,
    )

    assert len(samples) == 1
    assert samples[0].stratum["month"] == "2021-01"
    assert samples[0].post_id in {"1", "2"}


def test_stream_is_deterministic(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS)},
    )

    first = sample_rotlk_stream(
        path, random_count=2, targeted_count=1, months=12, seed=21
    )
    second = sample_rotlk_stream(
        path, random_count=2, targeted_count=1, months=12, seed=21
    )

    assert [
        (sample.post_id, sample.thread_id, sample.stratum) for sample in first
    ] == [
        (sample.post_id, sample.thread_id, sample.stratum) for sample in second
    ]


def test_stream_reads_plain_ndjson(tmp_path):
    path = tmp_path / "threads.ndjson"
    path.write_text(_ndjson(THREADS), encoding="utf-8")

    samples = sample_rotlk_stream(
        path, random_count=1, targeted_count=0, months=12, seed=7
    )

    assert len(samples) == 1


def test_stream_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        sample_rotlk_stream(tmp_path / "missing.tar.zst")


def test_windowed_compares_exact_timestamp():
    cutoff = datetime(2021, 5, 16, tzinfo=timezone.utc)

    def sample(post_id: str, timestamp: datetime | None) -> SamplePost:
        return SamplePost(
            post_id=post_id,
            thread_id=post_id,
            source="kek",
            timestamp_utc=timestamp,
            content_hash=f"hash-{post_id}",
        )

    samples = [
        sample("early", datetime(2021, 5, 1, tzinfo=timezone.utc)),
        sample("boundary", cutoff),
        sample("late", datetime(2021, 5, 20, tzinfo=timezone.utc)),
        sample("missing", None),
    ]

    assert [item.post_id for item in _windowed(samples, cutoff)] == [
        "boundary",
        "late",
    ]


def test_stream_excludes_posts_before_cutoff_day(tmp_path):
    threads = [
        _thread(10, _epoch(2021, 5, 1), "too early for the window"),
        _thread(11, _epoch(2021, 5, 20), "late enough in may"),
        _thread(12, _epoch(2021, 6, 15), "the newest post"),
    ]
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(threads)},
    )

    samples = sample_rotlk_stream(
        path,
        random_count=5,
        targeted_count=0,
        months=1,
        seed=7,
    )

    # max_ts is 2021-06-15, so the cutoff is 2021-05-16: the May 1 post is in
    # the cutoff month but before the cutoff day.
    assert "10" not in {sample.post_id for sample in samples}
    assert {sample.post_id for sample in samples} == {"11", "12"}


def test_stream_random_skips_quote_only_posts(tmp_path):
    quote_only = (
        '<a href="#p1" class="quotelink">&gt;&gt;1</a>'
    )
    threads = [_thread(20, _epoch(2021, 1, 10), quote_only)]
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(threads)},
    )

    samples = sample_rotlk_stream(
        path,
        random_count=1,
        targeted_count=0,
        months=1,
        seed=7,
    )

    assert samples == []


def test_stream_respects_explicit_window(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS)},
    )

    samples = sample_rotlk_stream(
        path,
        random_count=2,
        targeted_count=0,
        seed=7,
        window_start="2021-02-01T00:00:00Z",
        window_end="2021-03-31T23:59:59Z",
    )

    assert len(samples) == 2
    timestamps = [sample.timestamp_utc for sample in samples]
    assert all(
        _epoch(2021, 2, 1) <= int(timestamp.timestamp()) <= _epoch(2021, 3, 31)
        for timestamp in timestamps
    )
    assert {sample.stratum["month"] for sample in samples} <= {"2021-02", "2021-03"}


def test_stream_rejects_inverted_window(tmp_path):
    path = _write_tar_zst(
        tmp_path / "threads.tar.zst",
        {"threads.ndjson": _ndjson(THREADS)},
    )

    with pytest.raises(ValueError, match="window_start"):
        sample_rotlk_stream(
            path,
            random_count=1,
            targeted_count=0,
            window_start="2021-03-01T00:00:00Z",
            window_end="2021-02-01T00:00:00Z",
        )


def test_stream_window_filter_does_not_require_max_timestamp(tmp_path):
    path = tmp_path / "threads.ndjson"
    path.write_text(_ndjson(THREADS[1:2]), encoding="utf-8")

    samples = sample_rotlk_stream(
        path,
        random_count=1,
        targeted_count=0,
        window_start="2021-01-01T00:00:00Z",
        window_end="2021-12-31T23:59:59Z",
    )

    assert len(samples) == 1
    assert samples[0].post_id == "3"


def test_stream_dedupes_copypasta_across_threads(tmp_path):
    threads = [
        _thread(10, _epoch(2021, 5, 1), "bump"),
        _thread(11, _epoch(2021, 5, 2), "bump"),
        _thread(12, _epoch(2021, 5, 3), "kek"),
    ]
    path = tmp_path / "threads.ndjson"
    path.write_text(_ndjson(threads), encoding="utf-8")

    samples = sample_rotlk_stream(path, random_count=3, targeted_count=0, seed=7)

    assert len(samples) == 2
    assert len({sample.content_hash for sample in samples}) == 2
    ids = {sample.post_id for sample in samples}
    assert "12" in ids
    assert ids & {"10", "11"}


def test_stream_redistributes_monthly_shortfall(tmp_path):
    threads = [_thread(20, _epoch(2021, 6, 1), "only june post")]
    for index in range(5):
        threads.append(
            _thread(30 + index, _epoch(2021, 7, 1 + index), f"july unique {index}")
        )
    path = tmp_path / "threads.ndjson"
    path.write_text(_ndjson(threads), encoding="utf-8")

    samples = sample_rotlk_stream(path, random_count=5, targeted_count=0, seed=7)

    assert len(samples) == 5
    assert len({sample.post_id for sample in samples}) == 5
    assert {"2021-06", "2021-07"} == {
        sample.stratum["month"] for sample in samples
    }
