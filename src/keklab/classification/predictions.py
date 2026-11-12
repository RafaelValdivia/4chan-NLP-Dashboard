# Role: store for L1 predictions over the corpus.
# Connects to: analytics/service, classification/dataset, ingest/l0.
#
# L1 is the bridge between the classifier and the dashboard: one row per
# post, with the frames and the ordinal toxicity the model assigned. The
# analytics service reads this shape, so the schema is a contract.

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from keklab.annotation.labels import FRAME_LABELS, normalize_frame_labels
from keklab.annotation.taxonomy import COARSE_HEADS, collapse_frames
from keklab.common.logging import get_logger

log = get_logger(__name__)

SCHEMA_VERSION = 1
MANIFEST_NAME = "_l1_manifest.json"

PREDICTION_COLUMNS: tuple[str, ...] = (
    "post_id",
    "frame_labels",
    "coarse_heads",
    "toxicity",
    "model",
    "run_id",
    "predicted_utc",
)


def _quote_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve()).replace("'", "''")


def normalize_prediction(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Validate one raw prediction and return it in canonical shape.

    Returns None when the payload cannot be used: a prediction without a
    usable label is worse than a missing one.
    """
    post_id = str(payload.get("post_id", "")).strip()
    if not post_id:
        return None

    try:
        frames = normalize_frame_labels(payload.get("frame_labels") or ["none"])
    except ValueError:
        return None

    toxicity = payload.get("toxicity")
    if toxicity is None:
        return None
    try:
        toxicity = int(toxicity)
    except (TypeError, ValueError):
        return None
    if not 0 <= toxicity <= 3:
        return None

    return {
        "post_id": post_id,
        "frame_labels": frames,
        "coarse_heads": collapse_frames(frames),
        "toxicity": toxicity,
        "model": str(payload.get("model", "")),
        "run_id": str(payload.get("run_id", "")),
        "predicted_utc": str(
            payload.get("predicted_utc") or datetime.now(timezone.utc).isoformat()
        ),
    }


def _month_of(row: dict[str, Any]) -> str | None:
    timestamp = row.get("timestamp_utc") or row.get("predicted_utc")
    if not timestamp:
        return None
    text = str(timestamp)
    if len(text) >= 7 and text[4] == "-":
        return text[:7]
    return None


def write_predictions(
    rows: Iterable[dict[str, Any]],
    out_dir: str | Path,
    *,
    month_of: Any = None,
    model: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Write predictions as Parquet partitioned by month.

    `month_of` receives one canonical row and returns its `YYYY-MM` key, or
    None to skip the row. Rows without a month land in `month=unknown`.
    """
    import pandas as pd

    target = Path(out_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)

    buckets: dict[str, list[dict[str, Any]]] = {}
    kept = 0
    skipped = 0
    for raw in rows:
        row = normalize_prediction(raw)
        if row is None:
            skipped += 1
            continue
        if not row["model"]:
            row["model"] = model
        if not row["run_id"]:
            row["run_id"] = run_id
        key = month_of(raw) if month_of is not None else _month_of(raw)
        buckets.setdefault(key or "unknown", []).append(row)
        kept += 1

    parts: list[str] = []
    for month, month_rows in sorted(buckets.items()):
        frame = pd.DataFrame.from_records(month_rows, columns=list(PREDICTION_COLUMNS))
        frame["frame_labels"] = [
            list(labels) for labels in frame["frame_labels"]
        ]
        frame["coarse_heads"] = [
            list(heads) for heads in frame["coarse_heads"]
        ]
        path = target / f"month={month}" / "part-00000.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        import duckdb

        connection = duckdb.connect()
        try:
            connection.execute(
                """
                CREATE TABLE predictions (
                    post_id BIGINT,
                    frame_labels VARCHAR[],
                    coarse_heads VARCHAR[],
                    toxicity SMALLINT,
                    model VARCHAR,
                    run_id VARCHAR,
                    predicted_utc VARCHAR
                )
                """
            )
            connection.execute("INSERT INTO predictions SELECT * FROM frame")
            connection.execute(
                f"COPY (SELECT * FROM predictions) TO '{_quote_path(path)}' "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
        finally:
            connection.close()
        parts.append(str(path))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model": model,
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "rows": kept,
        "rows_skipped": skipped,
        "months": sorted(buckets),
        "parts": parts,
        "labels": list(FRAME_LABELS),
        "coarse_heads": list(COARSE_HEADS),
    }
    tmp = target / f"{MANIFEST_NAME}.tmp.{os.getpid()}"
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target / MANIFEST_NAME)
    return manifest


def load_predictions(path: str | Path) -> list[dict[str, Any]]:
    """Read a predictions parquet (single file) or a partitioned directory."""
    import duckdb

    source = Path(path).expanduser()
    if source.is_dir():
        pattern = _quote_path(source / "month=*" / "*.parquet")
    else:
        pattern = _quote_path(source)
    rows = duckdb.sql(
        f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true)"
    ).fetchall()
    columns = [
        column[0]
        for column in duckdb.sql(
            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true) LIMIT 0"
        ).description
    ]
    return [dict(zip(columns, row)) for row in rows]
