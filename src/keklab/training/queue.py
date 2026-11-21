"""Persistent directory queue with atomic claims, retries and dependency gates."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from keklab.common.paths import DATA_DIR, PROJECT_ROOT

QUEUE_DIR = Path(os.environ.get("KEKLAB_QUEUE_DIR", DATA_DIR / "classification" / "queue"))
STATES = ("pending", "running", "done", "failed", "blocked")
TERMINAL = {"done", "failed", "blocked"}
TRANSIENT_MARKERS = (
    "temporary failure",
    "connection reset",
    "connection aborted",
    "timed out",
    "timeout",
    "network is unreachable",
    "cuda out of memory",
    "out of memory",
    "http 502",
    "http 503",
    "http 504",
    "rate limit",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_queue(root: Path = QUEUE_DIR) -> Path:
    root = Path(root).expanduser()
    for name in STATES:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"job is not an object: {path}")
    return value


def submit_job(
    job_type: str,
    *,
    params: dict[str, Any] | None = None,
    depends_on: list[str] | None = None,
    name: str | None = None,
    max_retries: int = 1,
    timeout_s: int = 86400,
    queue_dir: Path = QUEUE_DIR,
) -> str:
    root = ensure_queue(queue_dir)
    job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}-{job_type}"
    job = {
        "id": job_id,
        "type": job_type,
        "name": name or job_id,
        "params": params or {},
        "depends_on": list(depends_on or []),
        "max_retries": int(max_retries),
        "timeout_s": int(timeout_s),
        "attempts": 0,
        "created_utc": now(),
        "updated_utc": now(),
        "state": "pending",
    }
    _write(root / "pending" / f"{job_id}.json", job)
    return job_id


def _jobs(root: Path, state: str) -> list[Path]:
    directory = root / state
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def all_jobs(root: Path = QUEUE_DIR) -> dict[str, dict[str, Any]]:
    root = ensure_queue(root)
    result: dict[str, dict[str, Any]] = {}
    for state in STATES:
        for path in _jobs(root, state):
            try:
                job = _read(path)
                job["state"] = state
                result[str(job["id"])] = job
            except Exception:
                continue
    return result


def status(root: Path = QUEUE_DIR) -> dict[str, Any]:
    root = ensure_queue(root)
    jobs = all_jobs(root)
    counts = {state: 0 for state in STATES}
    for job in jobs.values():
        counts[job["state"]] = counts.get(job["state"], 0) + 1
    latest = sorted(jobs.values(), key=lambda item: item.get("updated_utc", ""))[-5:]
    return {"counts": counts, "total": len(jobs), "latest": latest, "queue_dir": str(root)}


def _claim_one(root: Path, pending: Path) -> Path | None:
    running = root / "running" / pending.name
    try:
        os.replace(pending, running)
    except FileNotFoundError:
        return None
    job = _read(running)
    job["state"] = "running"
    job["started_utc"] = now()
    job["updated_utc"] = now()
    job["attempts"] = int(job.get("attempts", 0)) + 1
    job["pid"] = os.getpid()
    _write(running, job)
    return running


def _move(src: Path, root: Path, state: str, **updates: Any) -> Path:
    job = _read(src)
    job.update(updates)
    job["state"] = state
    job["updated_utc"] = now()
    dst = root / state / src.name
    _write(src, job)
    os.replace(src, dst)
    return dst


def _dependencies_ok(job: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
    pending = False
    for dep in job.get("depends_on", []):
        state = jobs.get(str(dep), {}).get("state")
        if state == "done":
            continue
        if state in {"failed", "blocked"}:
            return False, False
        pending = True
    return not pending, pending


def _is_transient(log_path: Path, returncode: int) -> bool:
    if returncode == 0:
        return False
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False
    return any(marker in text for marker in TRANSIENT_MARKERS)


def _run_job(root: Path, running: Path) -> None:
    job = _read(running)
    job_id = str(job["id"])
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job_id}.log"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["KEKLAB_ROOT"] = str(PROJECT_ROOT)
    cmd = [sys.executable, "-m", "keklab.training.jobs", "--job", str(running)]
    started = time.time()
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"=== {now()} start {job['type']} attempt {job.get('attempts')} ===\n")
        log.flush()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=int(job.get("timeout_s", 86400)),
            )
            code = int(result.returncode)
        except subprocess.TimeoutExpired:
            code = 124
            log.write(f"\n=== timeout after {job.get('timeout_s')}s ===\n")
        except Exception as exc:
            code = 1
            log.write(f"\n=== runner error: {type(exc).__name__}: {exc} ===\n")
        elapsed = round(time.time() - started, 1)
        log.write(f"=== {now()} exit {code} in {elapsed}s ===\n")

    job = _read(running)
    job["finished_utc"] = now()
    job["seconds"] = elapsed
    job["returncode"] = code
    job["log"] = str(log_path)
    if code == 0:
        _move(running, root, "done", **{key: value for key, value in job.items() if key != "state"})
        return
    attempts = int(job.get("attempts", 1))
    if _is_transient(log_path, code) and attempts <= int(job.get("max_retries", 1)):
        job["last_error"] = f"transient failure; retry {attempts}/{job.get('max_retries')}"
        job["state"] = "pending"
        job["updated_utc"] = now()
        _write(running, job)
        os.replace(running, root / "pending" / running.name)
        return
    job["last_error"] = "transient failure" if _is_transient(log_path, code) else "job failed"
    _move(running, root, "failed", **{key: value for key, value in job.items() if key != "state"})


def worker(*, once: bool = False, poll_s: float = 10.0, queue_dir: Path = QUEUE_DIR) -> int:
    root = ensure_queue(queue_dir)
    lock_path = root / ".worker.lock"
    lock = lock_path.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("worker already running", flush=True)
        return 0

    for orphan in _jobs(root, "running"):
        job = _read(orphan)
        job["state"] = "pending"
        job["last_error"] = "requeued after worker restart"
        job["updated_utc"] = now()
        _write(orphan, job)
        os.replace(orphan, root / "pending" / orphan.name)

    print(f"worker started queue={root} pid={os.getpid()}", flush=True)
    while True:
        jobs = all_jobs(root)
        progressed = False
        for pending_path in _jobs(root, "pending"):
            job = _read(pending_path)
            ready, waiting = _dependencies_ok(job, jobs)
            if not ready and waiting:
                continue
            if not ready:
                _move(pending_path, root, "blocked", last_error="dependency failed")
                progressed = True
                continue
            running = _claim_one(root, pending_path)
            if running is None:
                break
            _run_job(root, running)
            progressed = True
            break
        if once and not progressed and not _jobs(root, "pending"):
            break
        if once:
            break
        if not progressed:
            time.sleep(max(1.0, poll_s))
    print("worker stopped", flush=True)
    return 0


def enqueue_default(*, queue_dir: Path = QUEUE_DIR) -> list[str]:
    setup = submit_job("setup", name="environment", timeout_s=7200, max_retries=3, queue_dir=queue_dir)
    export = submit_job("export", name="export-data", depends_on=[setup], queue_dir=queue_dir)
    laya_soft = submit_job(
        "laya",
        name="laya-frozen-softce",
        params={"run": "laya-frozen-softce", "loss": "soft-ce", "freeze_encoder": True, "epochs": 4},
        depends_on=[export],
        timeout_s=43200,
        max_retries=1,
        queue_dir=queue_dir,
    )
    laya_rlcd = submit_job(
        "laya",
        name="laya-frozen-rlcd",
        params={"run": "laya-frozen-rlcd", "loss": "rlcd", "freeze_encoder": True, "epochs": 4, "optional": True},
        depends_on=[export],
        timeout_s=43200,
        max_retries=0,
        queue_dir=queue_dir,
    )
    laya_full = submit_job(
        "laya",
        name="laya-full-attempt",
        params={"run": "laya-full", "loss": "soft-ce", "freeze_encoder": False, "epochs": 3, "micro_batch": 1, "optional": True},
        depends_on=[laya_soft],
        timeout_s=43200,
        max_retries=0,
        queue_dir=queue_dir,
    )
    gliner = submit_job(
        "gliner",
        name="gliner-finetune",
        depends_on=[export, setup],
        timeout_s=28800,
        max_retries=1,
        queue_dir=queue_dir,
    )
    baselines = submit_job(
        "baselines",
        name="classical-baselines",
        depends_on=[export],
        timeout_s=7200,
        max_retries=0,
        queue_dir=queue_dir,
    )
    evaluate_dev = submit_job(
        "evaluate",
        name="evaluate-dev",
        params={"split": "dev"},
        depends_on=[laya_soft, gliner, baselines],
        timeout_s=3600,
        max_retries=0,
        queue_dir=queue_dir,
    )
    evaluate_test = submit_job(
        "evaluate",
        name="evaluate-test-once",
        params={"split": "test"},
        depends_on=[evaluate_dev],
        timeout_s=3600,
        max_retries=0,
        queue_dir=queue_dir,
    )
    report = submit_job(
        "report",
        name="comparison-report",
        depends_on=[evaluate_dev, evaluate_test],
        timeout_s=1800,
        max_retries=0,
        queue_dir=queue_dir,
    )
    return [setup, export, laya_soft, laya_rlcd, laya_full, gliner, baselines, evaluate_dev, evaluate_test, report]


def launch(*, queue_dir: Path = QUEUE_DIR) -> dict[str, Any]:
    root = ensure_queue(queue_dir)
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "worker.log"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    cmd = [sys.executable, "-m", "keklab.training.queue", "--queue-dir", str(root), "worker"]
    unit = f"keklab-training-{uuid.uuid4().hex[:8]}"
    systemd = shutil.which("systemd-run")
    if systemd:
        result = subprocess.run(
            [systemd, "--user", "--collect", "--unit", unit, "--working-directory", str(PROJECT_ROOT),
             "--setenv", f"PYTHONPATH={env['PYTHONPATH']}", *cmd],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {"mode": "systemd", "unit": unit, "log": str(log_path), "pid": None}
    handle = subprocess.Popen(
        cmd, cwd=str(PROJECT_ROOT), env=env, stdout=log_path.open("a"), stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {"mode": "setsid", "unit": None, "log": str(log_path), "pid": handle.pid}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="keklab-training-queue")
    parser.add_argument("--queue-dir", default=str(QUEUE_DIR))
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init")
    p_init.set_defaults(func=lambda _: print(ensure_queue(Path(_.queue_dir))))
    p_submit = sub.add_parser("submit")
    p_submit.add_argument("type")
    p_submit.add_argument("--param", action="append", default=[])
    p_submit.add_argument("--dep", action="append", default=[])
    p_submit.add_argument("--name")
    p_submit.add_argument("--timeout", type=int, default=86400)
    p_submit.add_argument("--retries", type=int, default=1)
    p_status = sub.add_parser("status")
    p_status.add_argument("--json", action="store_true")
    p_worker = sub.add_parser("worker")
    p_worker.add_argument("--once", action="store_true")
    p_worker.add_argument("--poll", type=float, default=10.0)
    p_default = sub.add_parser("enqueue-default")
    p_launch = sub.add_parser("launch")
    args = parser.parse_args(argv)

    if args.command == "init":
        print(ensure_queue(Path(args.queue_dir)))
        return 0
    if args.command == "submit":
        params: dict[str, Any] = {}
        for item in args.param:
            key, _, value = item.partition("=")
            if not _:
                raise ValueError(f"expected KEY=VALUE, got {item!r}")
            params[key] = value
        print(submit_job(args.type, params=params, depends_on=args.dep, name=args.name,
                         max_retries=args.retries, timeout_s=args.timeout,
                         queue_dir=Path(args.queue_dir)))
        return 0
    if args.command == "status":
        value = status(Path(args.queue_dir))
        if args.json:
            print(json.dumps(value, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(value["counts"], sort_keys=True))
            for job in value["latest"]:
                print(f"{job['id']}  {job['state']:<8} {job.get('name', '')}  {job.get('log', '')}")
        return 0
    if args.command == "worker":
        return worker(once=args.once, poll_s=args.poll, queue_dir=Path(args.queue_dir))
    if args.command == "enqueue-default":
        for job_id in enqueue_default(queue_dir=Path(args.queue_dir)):
            print(job_id)
        return 0
    if args.command == "launch":
        print(json.dumps(launch(queue_dir=Path(args.queue_dir)), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
