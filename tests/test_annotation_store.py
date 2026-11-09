from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

import pytest

from keklab.annotation.schema import AnnotationRecord, SamplePost
from keklab.annotation.store import (
    AnnotationStore,
    annotation_stats,
    export_csv,
    export_jsonl,
    load_annotations,
    load_samples,
    pending_samples,
    write_annotations,
    write_samples,
)
from keklab.formal.schema import Annotation


def make_sample(post_id: str = "1", thread_id: str = "t1", source: str = "fourplebs") -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=thread_id,
        source=source,
        period="recent_2020_plus" if source == "fourplebs" else "hist_2016_2019",
        timestamp_utc=datetime(2026, 10, 1, tzinfo=timezone.utc),
        subject="subject",
        text_raw="<b>hello</b>",
        text_clean="hello",
        content_hash=f"hash-{post_id}",
        stratum={"reason": "random", "month": "2026-10"},
    )


def make_annotation(
    post_id: str = "1",
    thread_id: str = "t1",
    source: str = "fourplebs",
    *,
    round: int = 1,
    annotator: str = "tester",
    frames: tuple[str, ...] = ("conspiracy",),
    toxicity: int = 1,
) -> AnnotationRecord:
    return AnnotationRecord(
        post_id=post_id,
        thread_id=thread_id,
        source=source,
        period="recent_2020_plus" if source == "fourplebs" else "hist_2016_2019",
        content_hash=f"hash-{post_id}",
        frame_labels=list(frames),
        toxicity=toxicity,
        annotator=annotator,
        round=round,
        tier="gold",
        guideline_version="v0",
        annotated_utc=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def test_sample_roundtrip(tmp_path):
    path = tmp_path / "samples.jsonl"
    samples = [make_sample("1"), make_sample("2")]
    write_samples(samples, path)

    loaded = load_samples(path)
    assert [sample.post_id for sample in loaded] == ["1", "2"]
    assert loaded[0].stratum["reason"] == "random"


def test_annotation_requires_valid_frames_and_toxicity():
    with pytest.raises(ValueError, match="At least one frame"):
        make_annotation(frames=())
    with pytest.raises(ValueError, match="cannot be combined"):
        make_annotation(frames=("none", "misogyny"))

    with pytest.raises(ValueError, match="Unknown frame label"):
        Annotation(
            post_id="1",
            frame_labels=["not_a_frame"],
            annotator="tester",
            guideline_version="v0",
        )

    base = dict(
        post_id="1",
        thread_id="t1",
        source="fourplebs",
        content_hash="hash",
        frame_labels=["none"],
        annotator="tester",
        guideline_version="v0",
    )
    with pytest.raises(ValueError):
        AnnotationRecord(**base, toxicity=None)
    with pytest.raises(ValueError):
        AnnotationRecord(**base, toxicity=4)


def test_store_upsert_updates_same_key_and_keeps_rounds(tmp_path):
    path = tmp_path / "annotations.jsonl"
    store = AnnotationStore(path)

    first = make_annotation(frames=("conspiracy",), toxicity=1)
    store.upsert(first)

    updated = make_annotation(frames=("misogyny",), toxicity=2)
    store.upsert(updated)

    records = store.load()
    assert len(records) == 1
    assert records[0].frame_labels == ["misogyny"]
    assert records[0].toxicity == 2

    second_round = make_annotation(round=2, annotator="tester")
    store.upsert(second_round)
    assert len(store.load()) == 2


def test_pending_samples_respects_round_and_annotator(tmp_path):
    samples = [make_sample("1"), make_sample("2"), make_sample("3")]
    records = [make_annotation("1", round=1, annotator="tester")]

    pending = pending_samples(samples, records, round=1, annotator="tester")
    assert [sample.post_id for sample in pending] == ["2", "3"]

    pending_other = pending_samples(samples, records, round=2, annotator="tester")
    assert len(pending_other) == 3

    pending_other_annotator = pending_samples(samples, records, round=1, annotator="other")
    assert len(pending_other_annotator) == 3


def test_write_and_load_annotations(tmp_path):
    path = tmp_path / "annotations.jsonl"
    records = [
        make_annotation("2", thread_id="t2"),
        make_annotation("1", thread_id="t1"),
    ]
    write_annotations(records, path)

    loaded = load_annotations(path)
    assert [record.post_id for record in loaded] == ["1", "2"]


def test_load_annotations_aliases_legacy_antifeminism(tmp_path):
    path = tmp_path / "annotations.jsonl"
    row = make_annotation(frames=("conspiracy",)).model_dump(mode="json")
    row["frame_labels"] = ["conspiracy", "antifeminism"]
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    loaded = load_annotations(path)

    assert loaded[0].frame_labels == ["conspiracy", "misogyny"]


def test_load_annotations_migrates_retired_frames(tmp_path):
    path = tmp_path / "annotations.jsonl"
    row = make_annotation(frames=("conspiracy",)).model_dump(mode="json")
    row["frame_labels"] = ["conspiracy", "ableism"]
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    loaded = load_annotations(path)
    assert loaded[0].frame_labels == ["conspiracy"]

    row["frame_labels"] = ["ableism"]
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    loaded = load_annotations(path)
    assert loaded[0].frame_labels == ["none"]


def test_export_csv_has_base_and_one_hot_columns(tmp_path):
    records = [make_annotation(frames=("conspiracy", "misogyny"), toxicity=2)]
    text = export_csv(records)

    reader = csv.DictReader(io.StringIO(text))
    row = next(reader)
    assert row["post_id"] == "1"
    assert row["frame_labels"] == "conspiracy|misogyny"
    assert row["coarse_labels"] == "conspiracy|gender_sexuality_prejudice"
    assert row["conspiracy"] == "1"
    assert row["misogyny"] == "1"
    assert row["antisemitism"] == "0"
    assert row["coarse_conspiracy"] == "1"
    assert row["coarse_gender_sexuality_prejudice"] == "1"
    assert row["coarse_no_frame"] == "0"
    assert row["toxicity"] == "2"

    out = tmp_path / "annotations.csv"
    export_csv(records, out)
    assert out.exists()


def test_export_jsonl_roundtrips(tmp_path):
    records = [make_annotation()]
    text = export_jsonl(records)
    path = tmp_path / "annotations.jsonl"
    path.write_text(text, encoding="utf-8")

    loaded = load_annotations(path)
    assert loaded[0].frame_labels == ["conspiracy"]


def test_annotation_stats_summarizes_records():
    records = [
        make_annotation("1", frames=("conspiracy",), toxicity=0),
        make_annotation("2", frames=("conspiracy", "misogyny"), toxicity=2),
        make_annotation("1", round=2, frames=("none",), toxicity=1),
    ]

    stats = annotation_stats(records)
    assert stats["annotations"] == 3
    assert stats["unique_posts"] == 2
    assert stats["frame_counts"]["conspiracy"] == 2
    assert stats["frame_counts"]["none"] == 1
    assert stats["coarse_counts"]["conspiracy"] == 2
    assert stats["coarse_counts"]["gender_sexuality_prejudice"] == 1
    assert stats["coarse_counts"]["no_frame"] == 1
    assert stats["toxicity_counts"]["0"] == 1
    assert stats["toxicity_counts"]["2"] == 1
    assert stats["rounds"] == [1, 2]
    assert stats["by_annotator_round"]["tester#r1"] == 2
