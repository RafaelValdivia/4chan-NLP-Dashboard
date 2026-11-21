"""Job handlers executed by the queue worker."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from keklab.classification.manifest import git_commit, write_manifest
from keklab.training import baselines_runner, data, evaluate, gliner_runner, laya_runner

PROTOCOL_DOC = data.PROJECT_ROOT / "docs" / "finetuning_protocol.md"
TEST_LOCK = data.REPORTS_DIR / ".test_evaluated.lock"


def _log(message: str) -> None:
    print(message, flush=True)


def _run(command: list[str], *, timeout: int = 3600) -> None:
    _log("$ " + " ".join(command))
    result = subprocess.run(command, text=True, timeout=timeout)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command)


def _pip_install(args: list[str], *, index_url: str | None = None, timeout: int = 3600) -> None:
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *args]
    if index_url:
        command.extend(["--index-url", index_url])
    _run(command, timeout=timeout)


WHEELHOUSE = Path(os.environ.get("KEKLAB_WHEELHOUSE", "/home/flynn/keklab-wheels"))
SETUP_CONSTRAINTS = (
    "transformers==4.57.6",
    "tokenizers==0.22.2",
    "huggingface-hub==0.36.2",
    "datasets==5.0.1",
    "accelerate==1.15.0",
    "numpy==2.5.4",
    "pyarrow==26.0.1",
    "sentencepiece==0.2.3",
    "safetensors==0.8.0",
    "scikit-learn==1.9.1",
    "tqdm==4.70.1",
    "pytest==9.2.0",
    "laya==0.4.31",
    "gliner==0.2.30",
    "vegaml==0.16.1",
)
SETUP_PACKAGES = (
    "torch==2.5.1+cu121",
    "transformers==4.57.6",
    "tokenizers==0.22.2",
    "huggingface-hub==0.36.2",
    "datasets==5.0.1",
    "accelerate==1.15.0",
    "numpy==2.5.4",
    "pyarrow==26.0.1",
    "sentencepiece==0.2.3",
    "safetensors==0.8.0",
    "scikit-learn==1.9.1",
    "tqdm==4.70.1",
    "pytest==9.2.0",
)
SETUP_MODEL_PACKAGES = (
    "laya==0.4.31",
    "gliner==0.2.30",
    "vegaml==0.16.1",
)


def setup(params: dict[str, Any]) -> dict[str, Any]:
    wheelhouse = Path(params.get("wheelhouse", WHEELHOUSE)).expanduser()
    if not wheelhouse.is_dir():
        raise FileNotFoundError(f"wheelhouse not found: {wheelhouse}")
    missing = [
        name
        for name in (
            "torch-2.5.1+cu121-cp312-cp312-linux_x86_64.whl",
            "transformers-4.57.6-py3-none-any.whl",
            "laya-0.4.31-py3-none-any.whl",
            "gliner-0.2.30-py3-none-any.whl",
            "vegaml-0.16.1-py3-none-any.whl",
        )
        if not (wheelhouse / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(f"missing wheelhouse files: {missing}")
    free = shutil.disk_usage(data.PROJECT_ROOT).free
    if free < 3 * 1024**3:
        raise RuntimeError(f"insufficient free disk for CUDA wheels: {free / 1024**3:.1f} GiB")
    constraints = Path(tempfile.mkstemp(prefix="keklab-constraints-", suffix=".txt")[1])
    constraints.write_text("\n".join(SETUP_CONSTRAINTS) + "\n", encoding="utf-8")
    base_install = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--find-links",
        str(wheelhouse),
        "-c",
        str(constraints),
        *SETUP_PACKAGES,
    ]
    model_install = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-deps",
        "--find-links",
        str(wheelhouse),
        *SETUP_MODEL_PACKAGES,
    ]
    installs = (base_install, model_install)

    def install_all(*, offline: bool) -> None:
        for command in installs:
            index_args = ["--no-index"] if offline else []
            _run([*command[:5], *index_args, *command[5:]], timeout=7200)

    try:
        install_all(offline=True)
        mode = "offline"
    except subprocess.CalledProcessError:
        _log("offline install failed; retrying with package indexes")
        install_all(offline=False)
        mode = "online-fallback"
    constraints.unlink(missing_ok=True)
    verify = (
        "import torch, laya, gliner, transformers\n"
        "print('torch', torch.__version__, 'cuda', torch.cuda.is_available())\n"
        "assert torch.__version__.startswith('2.5.1'), torch.__version__\n"
        "assert torch.cuda.is_available(), 'CUDA unavailable'\n"
        "x = torch.randn(64, 64, device='cuda')\n"
        "y = x @ x\n"
        "torch.cuda.synchronize()\n"
        "assert bool(torch.isfinite(y).all()), 'CUDA matmul smoke test failed'\n"
        "print('device', torch.cuda.get_device_name(0), 'capability', torch.cuda.get_device_capability(0))\n"
        "print('arch', torch.cuda.get_arch_list())\n"
        "assert transformers.__version__.startswith('4.57.'), transformers.__version__\n"
        "print('transformers', transformers.__version__, 'laya', getattr(laya, '__version__', '?'), "
        "'gliner', getattr(gliner, '__version__', '?'))\n"
    )
    _run([sys.executable, "-c", verify], timeout=300)
    manifest = {
        "kind": "environment_setup",
        "python": sys.executable,
        "wheelhouse": str(wheelhouse),
        "install_mode": mode,
        "constraints": list(SETUP_CONSTRAINTS),
        "packages": list(SETUP_PACKAGES),
        "model_packages": list(SETUP_MODEL_PACKAGES),
        "git_commit": git_commit(),
    }
    write_manifest(data.MANIFESTS_DIR / "environment-setup.json", manifest)
    return manifest


def export(params: dict[str, Any]) -> dict[str, Any]:
    manifest = data.export_all()
    _log(json.dumps(manifest, indent=2, ensure_ascii=False)[:4000])
    return manifest


def laya(params: dict[str, Any]) -> dict[str, Any]:
    run = str(params.get("run", "laya-frozen-softce"))
    optional = bool(params.get("optional", False))
    try:
        manifest = laya_runner.train(params)
    except Exception as exc:
        if not optional:
            raise
        manifest = {
            "kind": "laya_finetune",
            "run": run,
            "status": "skipped",
            "reason": f"{type(exc).__name__}: {exc}",
        }
        write_manifest(data.MANIFESTS_DIR / f"{run}.json", manifest)
        _log(f"optional run skipped: {manifest['reason']}")
        return manifest
    counts = laya_runner.predict(data.MODELS_DIR / "laya" / run, params)
    manifest["predictions"] = counts
    write_manifest(data.MANIFESTS_DIR / f"{run}.json", manifest)
    return manifest


def gliner(params: dict[str, Any]) -> dict[str, Any]:
    manifest = gliner_runner.train(params)
    manifest["predictions"] = gliner_runner.predict(params)
    write_manifest(data.MANIFESTS_DIR / "gliner-finetune.json", manifest)
    return manifest


def baselines(params: dict[str, Any]) -> dict[str, Any]:
    return baselines_runner.run()


def evaluate_job(params: dict[str, Any]) -> dict[str, Any]:
    split = str(params.get("split", "dev"))
    if split == "test":
        if not PROTOCOL_DOC.exists():
            raise FileNotFoundError(f"test locked: create {PROTOCOL_DOC} before scoring test")
        if not data.paths()["test_hash"].exists():
            raise FileNotFoundError("test locked: missing frozen test hash")
        data.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(TEST_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            _log("test was already evaluated; refusing a second run")
            return {"kind": "evaluation_test", "skipped": True, "reason": "one-shot test lock exists"}
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"started_utc={git_commit()}\n")
    report = evaluate.evaluate_split(split)
    if split == "test":
        lock_text = TEST_LOCK.read_text(encoding="utf-8") if TEST_LOCK.exists() else ""
        TEST_LOCK.write_text(lock_text + "completed\n", encoding="utf-8")
    return report


def report(params: dict[str, Any]) -> dict[str, Any]:
    dev_path = data.REPORTS_DIR / "evaluation-dev.json"
    test_path = data.REPORTS_DIR / "evaluation-test.json"
    if not dev_path.exists():
        raise FileNotFoundError(dev_path)
    dev = json.loads(dev_path.read_text(encoding="utf-8"))
    test = json.loads(test_path.read_text(encoding="utf-8")) if test_path.exists() else None
    path = evaluate.write_comparison(dev, test)
    manifest = {
        "kind": "comparison_report",
        "output": str(path),
        "dev_models": sorted(dev.get("models", {})),
        "test_models": sorted((test or {}).get("models", {})),
        "git_commit": git_commit(),
    }
    write_manifest(data.MANIFESTS_DIR / "comparison-report.json", manifest)
    return manifest


HANDLERS = {
    "setup": setup,
    "export": export,
    "laya": laya,
    "gliner": gliner,
    "baselines": baselines,
    "evaluate": evaluate_job,
    "report": report,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args(argv)
    path = Path(args.job)
    job = json.loads(path.read_text(encoding="utf-8"))
    handler = HANDLERS.get(str(job.get("type")))
    if handler is None:
        raise SystemExit(f"unknown job type: {job.get('type')}")
    _log(f"job={job.get('id')} type={job.get('type')} params={json.dumps(job.get('params', {}), sort_keys=True)}")
    result = handler(job.get("params") or {})
    _log(json.dumps(result, indent=2, ensure_ascii=False, default=str)[:8000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
