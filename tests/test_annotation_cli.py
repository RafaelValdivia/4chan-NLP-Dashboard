from __future__ import annotations

import json

import pytest

from keklab.annotation.cli import HELP_TEXT, render_sample, run_session
from keklab.annotation.labels import format_frame_menu
from keklab.annotation.schema import (
    AnnotationRecord,
    ContextPost,
    SampleContext,
    SamplePost,
)
from keklab.annotation.store import write_annotations
from keklab.common.cli import build_parser, main


def make_sample(post_id: str = "1") -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id="100",
        source="fourplebs",
        period="recent_2020_plus",
        subject="Test",
        text_raw=">>99 hello",
        text_clean="hello",
        quotes=["99"],
        content_hash=f"hash-{post_id}",
        stratum={"reason": "random"},
        context=SampleContext(
            op=ContextPost(post_id="99", text_raw="OP post", is_op=True)
        ),
    )


def test_render_sample_shows_context_and_prompts():
    sample = make_sample()
    text = render_sample(sample, 1, 10, ["conspiracy"], 2)

    assert "OP context" in text
    assert "OP post" in text
    assert "conspiracy" in text
    assert "toxicity" in text.lower()


def test_format_frame_menu_lists_all_frames():
    menu = format_frame_menu()
    assert "conspiracy" in menu
    assert "none" in menu
    assert "unclear" in menu


def test_run_session_saves_annotation_and_skips_completed(tmp_path):
    sample = make_sample()
    out = tmp_path / "annotations.jsonl"
    outputs: list[str] = []
    inputs = iter(["1", "t", "s", "q"])

    def prompt(_):
        return next(inputs)

    def emit(text: str):
        outputs.append(text)

    summary = run_session(
        [sample],
        out,
        annotator="tester",
        guideline="v0",
        round=1,
        prompt=prompt,
        emit=emit,
    )

    assert summary["saved"] == 1
    assert out.exists()

    data = json.loads(out.read_text().strip())
    record = AnnotationRecord.model_validate(data)
    assert record.frame_labels == ["conspiracy"]
    assert record.toxicity == 0
    assert record.annotator == "tester"

    # Resume skips completed
    summary2 = run_session(
        [sample],
        out,
        annotator="tester",
        guideline="v0",
        round=1,
        prompt=prompt,
        emit=emit,
    )
    assert summary2["saved"] == 0
    assert summary2["remaining"] == 0


def test_run_session_none_clears_other_frames(tmp_path):
    sample = make_sample()
    out = tmp_path / "annotations.jsonl"
    inputs = iter(["1 2", "n", "t", "s", "q"])

    summary = run_session(
        [sample],
        out,
        annotator="tester",
        guideline="v0",
        prompt=lambda _: next(inputs),
        emit=lambda _: None,
    )

    data = json.loads(out.read_text().strip())
    record = AnnotationRecord.model_validate(data)
    assert record.frame_labels == ["none"]
    assert summary["saved"] == 1


def test_run_session_requires_frames_and_toxicity(tmp_path):
    sample = make_sample()
    out = tmp_path / "annotations.jsonl"
    inputs = iter(["s", "1", "s", "t", "s", "q"])
    outputs: list[str] = []

    run_session(
        [sample],
        out,
        annotator="tester",
        guideline="v0",
        prompt=lambda _: next(inputs),
        emit=outputs.append,
    )

    assert any("Select at least one frame" in line for line in outputs)
    assert any("Set toxicity" in line for line in outputs)
    assert out.exists()


def test_help_text_mentions_controls():
    assert "none" in HELP_TEXT
    assert "toxicity" in HELP_TEXT
    assert "save" in HELP_TEXT


def make_record(post_id: str, round: int, frames: tuple[str, ...]) -> AnnotationRecord:
    return AnnotationRecord(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="fourplebs",
        content_hash=f"hash-{post_id}",
        frame_labels=list(frames),
        toxicity=1,
        annotator="tester",
        round=round,
        guideline_version="v0",
    )


def test_annotate_parser_is_registered():
    parser = build_parser()
    args = parser.parse_args(["annotate", "sample", "--out", "samples.jsonl"])
    assert args.annotate_command == "sample"
    assert args.random == 20
    assert args.targeted == 10


def test_annotate_stats_export_and_agreement_cli(tmp_path, capsys):
    round1 = tmp_path / "r1.jsonl"
    round2 = tmp_path / "r2.jsonl"
    write_annotations(
        [
            make_record("1", 1, ("conspiracy",)),
            make_record("2", 1, ("none",)),
        ],
        round1,
    )
    write_annotations(
        [
            make_record("1", 2, ("conspiracy",)),
            make_record("2", 2, ("none",)),
        ],
        round2,
    )

    assert main(["annotate", "stats", "--input", str(round1), "--json"]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["annotations"] == 2
    assert stats["frame_counts"]["conspiracy"] == 1

    csv_path = tmp_path / "annotations.csv"
    assert (
        main(
            [
                "annotate",
                "export",
                "--input",
                str(round1),
                "--format",
                "csv",
                "--output",
                str(csv_path),
            ]
        )
        == 0
    )
    assert "frame_labels" in csv_path.read_text()
    capsys.readouterr()

    assert (
        main(
            [
                "annotate",
                "agreement",
                "--a",
                str(round1),
                "--b",
                str(round2),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["n_posts"] == 2
    assert report["exact_frame_set_match"] == pytest.approx(1.0)


def test_annotate_stats_rejects_invalid_annotation(tmp_path, caplog):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"post_id": "1"}\n', encoding="utf-8")

    assert main(["annotate", "stats", "--input", str(path)]) == 1
    assert "invalid annotation" in caplog.text

