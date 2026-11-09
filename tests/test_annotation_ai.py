from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from keklab.annotation.ai import (
    build_tasks,
    import_proposals,
    proposal_agreement,
    proposal_stats,
)
from keklab.annotation.proposal import TaskRecord, build_proposal, build_review
from keklab.annotation.review import pending_proposals, render_review, run_review
from keklab.annotation.schema import AnnotationRecord, ContextPost, SampleContext, SamplePost
from keklab.annotation.store import (
    load_annotations,
    load_proposals,
    load_reviews,
    load_tasks,
    write_annotations,
    write_samples,
)
from keklab.common.cli import build_parser, main

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def make_sample(post_id: str, *, text_raw: str = "hello world") -> SamplePost:
    return SamplePost(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="kek",
        period="hist_2016_2019",
        timestamp_utc=NOW,
        subject=None,
        text_raw=text_raw,
        text_clean=text_raw,
        quotes=[],
        content_hash=f"hash-{post_id}",
        is_op=False,
        stratum={"reason": "random", "month": "2018-01"},
        context=SampleContext(
            op=ContextPost(post_id="op", text_raw="OP text", is_op=True)
        ),
    )


def make_gold(
    post_id: str,
    frames: tuple[str, ...] = ("conspiracy",),
    toxicity: int = 1,
) -> AnnotationRecord:
    return AnnotationRecord(
        post_id=post_id,
        thread_id=f"t-{post_id}",
        source="kek",
        period="hist_2016_2019",
        content_hash=f"hash-{post_id}",
        frame_labels=list(frames),
        toxicity=toxicity,
        annotator="flynnso",
        round=1,
        tier="gold",
        guideline_version="v0.1",
        annotated_utc=NOW,
        notes='stratum={"reason": "random"}',
    )


def make_tasks(*post_ids: str) -> list[TaskRecord]:
    samples = [make_sample(post_id) for post_id in post_ids]
    tasks, _ = build_tasks(
        samples,
        gold=[],
        guideline_version="v0.1",
        prompt_version="v1",
        created_utc=NOW,
    )
    return tasks


def make_proposal(task: TaskRecord, **overrides):
    values = dict(
        frame_labels=["conspiracy"],
        toxicity=1,
        confidence=0.8,
        rationale="A secret plot is described.",
        evidence=["hello world"],
        model="big-pickle",
        provider="opencode",
        created_utc=NOW,
    )
    values.update(overrides)
    return build_proposal(task, **values)


# ---------------------------------------------------------------------------
# Task building
# ---------------------------------------------------------------------------
def test_build_tasks_excludes_gold_and_dedupes():
    samples = [
        make_sample("1"),
        make_sample("2"),
        make_sample("2"),
        make_sample("3"),
    ]
    tasks, report = build_tasks(
        samples,
        gold=[make_gold("1")],
        guideline_version="v0.1",
        prompt_version="v1",
        created_utc=NOW,
    )

    assert [task.post_id for task in tasks] == ["2", "3"]
    assert report["samples"] == 4
    assert report["unique_samples"] == 3
    assert report["excluded_by_gold"] == 1
    assert report["pending"] == 2
    assert report["selected"] == 2


def test_build_tasks_start_limit_and_include_annotated():
    samples = [make_sample(str(index)) for index in range(1, 5)]
    gold = [make_gold("1")]

    tasks, _ = build_tasks(
        samples,
        gold=gold,
        guideline_version="v0.1",
        prompt_version="v1",
        start=2,
        limit=1,
        created_utc=NOW,
    )
    assert [task.post_id for task in tasks] == ["3"]

    tasks, report = build_tasks(
        samples,
        gold=gold,
        guideline_version="v0.1",
        prompt_version="v1",
        include_annotated=True,
        created_utc=NOW,
    )
    assert [task.post_id for task in tasks] == ["1", "2", "3", "4"]
    assert report["excluded_by_gold"] == 0


def test_build_tasks_rejects_invalid_offsets():
    samples = [make_sample("1")]
    with pytest.raises(ValueError):
        build_tasks(
            samples,
            guideline_version="v0.1",
            prompt_version="v1",
            start=0,
        )
    with pytest.raises(ValueError):
        build_tasks(
            samples,
            guideline_version="v0.1",
            prompt_version="v1",
            limit=-1,
        )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
def test_import_proposals_adds_and_replaces():
    tasks = make_tasks("1")
    proposal = make_proposal(tasks[0])

    merged, report = import_proposals(tasks, [proposal])
    assert report == {
        "tasks": 1,
        "incoming": 1,
        "added": 1,
        "replaced": 0,
        "total": 1,
    }
    assert merged[0].proposal_id == proposal.proposal_id

    with pytest.raises(ValueError, match="already exists"):
        import_proposals(tasks, [proposal], existing=[proposal])

    changed = make_proposal(
        tasks[0], rationale="Different rationale.", confidence=0.4
    )
    merged, report = import_proposals(
        tasks, [changed], existing=[proposal], replace=True
    )
    assert report["replaced"] == 1
    assert merged[0].rationale == "Different rationale."


def test_import_proposals_rejects_unknown_task_and_duplicates():
    tasks = make_tasks("1")
    orphan_task = make_tasks("2")[0]
    proposal = make_proposal(orphan_task)

    with pytest.raises(ValueError, match="unknown task"):
        import_proposals(tasks, [proposal])

    valid = make_proposal(tasks[0])
    with pytest.raises(ValueError, match="duplicate proposal"):
        import_proposals(tasks, [valid, valid])


def test_import_proposals_rejects_bad_evidence_and_hash():
    tasks = make_tasks("1")
    bad_evidence = make_proposal(tasks[0], evidence=["not in the post"])
    with pytest.raises(ValueError, match="evidence not found"):
        import_proposals(tasks, [bad_evidence])

    other_task = make_tasks("2")[0]
    proposal = make_proposal(tasks[0])
    # A proposal for task 1 cannot be imported when only task 2 is known.
    with pytest.raises(ValueError, match="unknown task"):
        import_proposals([other_task], [proposal])


# ---------------------------------------------------------------------------
# Stats and agreement
# ---------------------------------------------------------------------------
def test_proposal_stats_counts_decisions_and_calibration():
    tasks = make_tasks("1", "2", "3", "4")
    proposals = [
        make_proposal(tasks[0], confidence=0.9),
        make_proposal(tasks[1], confidence=0.6, frame_labels=["racism"]),
        make_proposal(tasks[2], confidence=0.4, frame_labels=["none"]),
        make_proposal(tasks[3], confidence=0.8),
    ]
    reviews = [
        build_review(
            proposals[0],
            reviewer="flynnso",
            decision="accept",
            final_frame_labels=proposals[0].frame_labels,
            final_toxicity=1,
            reviewed_utc=NOW,
        ),
        build_review(
            proposals[1],
            reviewer="flynnso",
            decision="edit",
            final_frame_labels=["racism", "misogyny"],
            final_toxicity=2,
            reviewed_utc=NOW,
        ),
        build_review(
            proposals[2],
            reviewer="flynnso",
            decision="reject",
            reviewed_utc=NOW,
        ),
        build_review(
            proposals[3],
            reviewer="flynnso",
            decision="skip",
            reviewed_utc=NOW,
        ),
    ]

    stats = proposal_stats(tasks, proposals, reviews)

    assert stats["tasks"] == 4
    assert stats["proposals"] == 4
    assert stats["coverage"] == 1.0
    assert stats["decisions"] == {
        "accept": 1,
        "edit": 1,
        "reject": 1,
        "skip": 1,
    }
    assert stats["resolved"] == 3
    assert stats["unresolved"] == 1
    assert stats["accept_rate"] == pytest.approx(1 / 3)
    assert stats["edit_rate"] == pytest.approx(1 / 3)
    assert stats["reject_rate"] == pytest.approx(1 / 3)
    # Accept keeps the full set; edit keeps 1 of 2 frames.
    assert stats["mean_jaccard"] == pytest.approx((1.0 + 1 / 2) / 2)
    assert stats["toxicity_exact_agreement"] == pytest.approx(1 / 2)
    assert stats["toxicity_mean_absolute_error"] == pytest.approx(0.5)

    buckets = {row["bucket"]: row for row in stats["calibration"]}
    assert buckets["0.85-1.00"]["proposals"] == 1
    assert buckets["0.85-1.00"]["accepted_without_edit"] == 1
    assert buckets["0.50-0.70"]["resolved"] == 1


def test_agreement_uses_shared_posts_only():
    tasks = make_tasks("1")
    proposals = [make_proposal(tasks[0])]
    gold = [make_gold("1"), make_gold("2", frames=("none",), toxicity=0)]

    report = proposal_agreement(proposals, gold)

    assert report["n_posts"] == 1
    assert report["only_b"] == 1
    assert report["exact_frame_set_match"] == 1.0
    assert report["toxicity"]["exact_agreement"] == 1.0


# ---------------------------------------------------------------------------
# Human review
# ---------------------------------------------------------------------------
def _scripted(answers: list[str]):
    pending = iter(answers)

    def prompt(_: str) -> str:
        return next(pending)

    return prompt


def test_review_accept_writes_gold_and_review_log(tmp_path):
    tasks = make_tasks("1")
    proposal = make_proposal(tasks[0])
    gold_path = tmp_path / "gold.jsonl"
    reviews_path = tmp_path / "reviews.jsonl"

    summary = run_review(
        tasks,
        [proposal],
        gold_path=gold_path,
        reviews_path=reviews_path,
        reviewer="flynnso",
        guideline_version="v0.1",
        prompt=_scripted(["a"]),
        emit=lambda _: None,
        now=lambda: NOW,
    )

    assert summary["accepted"] == 1
    assert summary["reviewed"] == 1

    gold = load_annotations(gold_path)
    assert len(gold) == 1
    assert gold[0].frame_labels == ["conspiracy"]
    assert gold[0].toxicity == 1
    assert gold[0].annotator == "flynnso"
    assert gold[0].tier == "gold"
    assert gold[0].guideline_version == "v0.1"
    # Provenance lives only in the review log.
    assert "proposal_id" not in gold[0].model_dump(mode="json")
    assert "frame" not in gold[0].notes

    reviews = load_reviews(reviews_path)
    assert len(reviews) == 1
    assert reviews[0].decision == "accept"
    assert reviews[0].proposal_id == proposal.proposal_id
    assert reviews[0].final_frame_labels == ["conspiracy"]


def test_review_edit_and_reject_and_skip(tmp_path):
    tasks = make_tasks("1", "2", "3")
    proposals = [
        make_proposal(tasks[0], frame_labels=["none"]),
        make_proposal(tasks[1]),
        make_proposal(tasks[2]),
    ]
    gold_path = tmp_path / "gold.jsonl"
    reviews_path = tmp_path / "reviews.jsonl"

    run_review(
        tasks,
        proposals,
        gold_path=gold_path,
        reviews_path=reviews_path,
        reviewer="flynnso",
        guideline_version="v0.1",
        prompt=_scripted(
            [
                "e",  # edit the first proposal
                "1",  # conspiracy
                "3",  # racism
                "t",  # toxicity 1 -> 2
                "s",  # save edit
                "r",  # reject the second
                "s",  # skip the third
            ]
        ),
        emit=lambda _: None,
        now=lambda: NOW,
    )

    gold = load_annotations(gold_path)
    assert len(gold) == 1
    assert gold[0].post_id == "1"
    assert gold[0].frame_labels == ["conspiracy", "racism"]
    assert gold[0].toxicity == 2

    reviews = {review.post_id: review for review in load_reviews(reviews_path)}
    assert reviews["1"].decision == "edit"
    assert reviews["2"].decision == "reject"
    assert reviews["3"].decision == "skip"

    # Skip stays unresolved, so it is still pending on resume.
    pending, orphans = pending_proposals(tasks, proposals, list(reviews.values()))
    assert orphans == 0
    assert [proposal.post_id for proposal in pending] == ["3"]


def test_review_resume_accepts_skipped_proposal(tmp_path):
    tasks = make_tasks("1")
    proposal = make_proposal(tasks[0])
    gold_path = tmp_path / "gold.jsonl"
    reviews_path = tmp_path / "reviews.jsonl"

    run_review(
        tasks,
        [proposal],
        gold_path=gold_path,
        reviews_path=reviews_path,
        reviewer="flynnso",
        guideline_version="v0.1",
        prompt=_scripted(["s"]),
        emit=lambda _: None,
        now=lambda: NOW,
    )
    assert load_annotations(gold_path) == []

    summary = run_review(
        tasks,
        [proposal],
        gold_path=gold_path,
        reviews_path=reviews_path,
        reviewer="flynnso",
        guideline_version="v0.1",
        prompt=_scripted(["a"]),
        emit=lambda _: None,
        now=lambda: NOW,
    )
    assert summary["accepted"] == 1
    assert len(load_annotations(gold_path)) == 1


def test_review_blind_hides_rationale_and_confidence():
    tasks = make_tasks("1")
    proposal = make_proposal(tasks[0], rationale="SECRET RATIONALE")
    text = render_review(
        tasks[0],
        proposal,
        1,
        1,
        frames=proposal.frame_labels,
        toxicity=proposal.toxicity,
        blind=True,
    )
    assert "SECRET RATIONALE" not in text
    assert "Confidence" not in text
    assert "Proposal: conspiracy" in text
    # Text-only review: thread context is never rendered.
    assert "OP text" not in text
    assert "OP context" not in text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_ai_subcommands_are_registered():
    parser = build_parser()
    args = parser.parse_args(
        ["annotate", "ai", "task", "--input", "s.jsonl", "--out", "t.jsonl"]
    )
    assert args.ai_command == "task"
    assert args.guideline == "v0.2"

    args = parser.parse_args(
        [
            "annotate",
            "ai",
            "review",
            "--tasks",
            "t.jsonl",
            "--proposals",
            "p.jsonl",
            "--gold",
            "g.jsonl",
            "--reviews",
            "r.jsonl",
            "--reviewer",
            "flynnso",
        ]
    )
    assert args.ai_command == "review"
    assert args.blind is False

    assert parser.parse_args(
        [
            "annotate",
            "ai",
            "import",
            "--tasks",
            "t.jsonl",
            "--input",
            "p.jsonl",
            "--out",
            "o.jsonl",
        ]
    ).ai_command == "import"
    assert parser.parse_args(
        [
            "annotate",
            "ai",
            "stats",
            "--tasks",
            "t.jsonl",
            "--proposals",
            "p.jsonl",
            "--reviews",
            "r.jsonl",
        ]
    ).ai_command == "stats"
    assert parser.parse_args(
        [
            "annotate",
            "ai",
            "agreement",
            "--proposals",
            "p.jsonl",
            "--gold",
            "g.jsonl",
        ]
    ).ai_command == "agreement"


def test_ai_task_and_import_cli(tmp_path, capsys):
    samples_path = tmp_path / "samples.jsonl"
    gold_path = tmp_path / "gold.jsonl"
    tasks_path = tmp_path / "tasks.jsonl"
    proposals_path = tmp_path / "proposals.jsonl"
    merged_path = tmp_path / "merged.jsonl"

    write_samples([make_sample("1"), make_sample("2")], samples_path)
    write_annotations([make_gold("1")], gold_path)

    assert (
        main(
            [
                "annotate",
                "ai",
                "task",
                "--input",
                str(samples_path),
                "--gold",
                str(gold_path),
                "--out",
                str(tasks_path),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["selected"] == 1
    assert report["excluded_by_gold"] == 1

    tasks = load_tasks(tasks_path)
    assert [task.post_id for task in tasks] == ["2"]
    proposal = make_proposal(tasks[0])
    proposals_path.write_text(
        json.dumps(proposal.model_dump(mode="json")) + "\n", encoding="utf-8"
    )

    assert (
        main(
            [
                "annotate",
                "ai",
                "import",
                "--tasks",
                str(tasks_path),
                "--input",
                str(proposals_path),
                "--out",
                str(merged_path),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["added"] == 1
    assert len(load_proposals(merged_path)) == 1
