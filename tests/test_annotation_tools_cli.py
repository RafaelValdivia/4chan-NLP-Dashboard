from __future__ import annotations

import json
from datetime import datetime, timezone

from keklab.annotation.schema import SamplePost
from keklab.annotation.store import load_samples, write_samples
from keklab.common.cli import main


def make_sample(
    post_id: str,
    *,
    reason: str = "random",
    month: str = "2018-01",
) -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="kek",
        period="hist_2016_2019",
        timestamp_utc=datetime(2018, 1, 1, tzinfo=timezone.utc),
        text_raw=f"text {post_id}",
        text_clean=f"text {post_id}",
        content_hash=f"hash-{post_id}",
        stratum={"reason": reason, "month": month},
    )


def test_cli_merge_deduplicates_and_checks_expected_counts(tmp_path, capsys):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    out = tmp_path / "merged.jsonl"
    write_samples([make_sample("1"), make_sample("2")], first)
    write_samples([make_sample("2"), make_sample("3", reason="targeted")], second)

    code = main(
        [
            "annotate",
            "merge",
            "--input",
            str(first),
            str(second),
            "--out",
            str(out),
            "--expect-total",
            "3",
            "--expect-random",
            "2",
            "--expect-targeted",
            "1",
        ]
    )

    assert code == 0
    assert len(load_samples(out)) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["kept"] == 3
    assert report["duplicates"] == 1
    assert report["by_reason"] == {"random": 2, "targeted": 1}


def test_cli_merge_fails_on_unexpected_count(tmp_path):
    source = tmp_path / "source.jsonl"
    out = tmp_path / "merged.jsonl"
    write_samples([make_sample("1")], source)

    code = main(
        [
            "annotate",
            "merge",
            "--input",
            str(source),
            "--out",
            str(out),
            "--expect-total",
            "2",
        ]
    )

    assert code == 1
    assert not out.exists()


def test_cli_retest_writes_deterministic_subset(tmp_path, capsys):
    source = tmp_path / "sample.jsonl"
    out = tmp_path / "retest.jsonl"
    write_samples([make_sample(str(index)) for index in range(10)], source)

    code = main(
        [
            "annotate",
            "retest",
            "--input",
            str(source),
            "--out",
            str(out),
            "--fraction",
            "0.2",
            "--seed",
            "7",
        ]
    )

    assert code == 0
    assert len(load_samples(out)) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary["selected"] == 2
    assert summary["seed"] == 7


def test_cli_split_writes_thread_manifest(tmp_path, capsys):
    source = tmp_path / "sample.jsonl"
    out = tmp_path / "splits.jsonl"
    write_samples([make_sample(str(index)) for index in range(10)], source)

    code = main(
        [
            "annotate",
            "split",
            "--input",
            str(source),
            "--out",
            str(out),
            "--seed",
            "3",
        ]
    )

    assert code == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 10
    assert {row["split"] for row in rows} == {"train", "dev", "test"}
    summary = json.loads(capsys.readouterr().out)
    assert summary["counts"] == {"train": 6, "dev": 2, "test": 2}


def test_cli_audit_reports_sample_health(tmp_path, capsys):
    source = tmp_path / "sample.jsonl"
    write_samples(
        [make_sample("1"), make_sample("2", reason="targeted", month="2018-02")],
        source,
    )

    code = main(
        [
            "annotate",
            "audit",
            "--input",
            str(source),
            "--json",
            "--start",
            "2018-01-01T00:00:00Z",
            "--end",
            "2018-12-31T23:59:59Z",
        ]
    )

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["posts"] == 2
    assert report["unique_threads"] == 2
    assert report["outside_window"] == 0
    assert report["by_reason"] == {"random": 1, "targeted": 1}
