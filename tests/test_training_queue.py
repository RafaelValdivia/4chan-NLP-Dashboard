from __future__ import annotations

import json
from pathlib import Path

from keklab.training import queue


def test_queue_submit_and_status(tmp_path: Path) -> None:
    root = tmp_path / "queue"
    job_id = queue.submit_job("export", name="export", queue_dir=root)
    value = queue.status(root)
    assert value["counts"]["pending"] == 1
    assert value["latest"][0]["id"] == job_id
    assert (root / "pending" / f"{job_id}.json").exists()


def test_worker_respects_dependencies_and_claim_order(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "queue"
    dependency = queue.submit_job("setup", name="dependency", queue_dir=root)
    queue.submit_job("export", name="child", depends_on=[dependency], queue_dir=root)
    processed: list[str] = []

    def fake_run(queue_root: Path, running: Path) -> None:
        job = json.loads(running.read_text(encoding="utf-8"))
        processed.append(str(job["name"]))
        queue._move(running, queue_root, "done")

    monkeypatch.setattr(queue, "_run_job", fake_run)
    queue.worker(once=True, queue_dir=root)
    assert processed == ["dependency"]
    queue.worker(once=True, queue_dir=root)
    assert processed == ["dependency", "child"]
    assert queue.status(root)["counts"]["done"] == 2


def test_failed_dependency_blocks_child(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "queue"
    dependency = queue.submit_job("setup", name="dependency", queue_dir=root)
    queue.submit_job("export", name="child", depends_on=[dependency], queue_dir=root)

    def fail(queue_root: Path, running: Path) -> None:
        queue._move(running, queue_root, "failed")

    monkeypatch.setattr(queue, "_run_job", fail)
    queue.worker(once=True, queue_dir=root)
    queue.worker(once=True, queue_dir=root)
    assert queue.status(root)["counts"]["blocked"] == 1
