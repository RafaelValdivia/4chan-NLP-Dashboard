# Role: shared I/O helpers (DuckDB connections, Parquet writes, streaming NDJSON).
# Connects to: ingest, classic, generative, eval.

from __future__ import annotations

import bz2
import gzip
import json
import shutil
import subprocess
import tarfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

from keklab.common.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------
def _con(con: Any = None) -> Any:
    """Return `con` if provided, otherwise open a new DuckDB connection."""
    if con is not None:
        return con

    import duckdb

    return duckdb.connect()


def _quote_path(path: str | Path) -> str:
    """Quote a filesystem path for use inside a DuckDB SQL string literal."""
    return str(Path(path).expanduser().resolve()).replace("'", "''")


def _src_ndjson(path: str | Path) -> str:
    """
    DuckDB scan expression for an NDJSON file.

    DuckDB performs schema inference over the file, so this is convenient for
    small/medium inputs but NOT a true streaming reader. For the full ROTLK
    corpus use `iter_ndjson()`.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(p)
    return (
        f"read_json_auto('{_quote_path(p)}', "
        "format='newline_delimited', ignore_errors=true)"
    )


def write_parquet(df: Any, path: str | Path, *, compression: str = "zstd") -> Path:
    """Write a DataFrame to Parquet using DuckDB (no pyarrow dependency)."""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    conn = _con()
    try:
        conn.register("_keklab_frame", df)
        conn.execute(
            f"COPY (SELECT * FROM _keklab_frame) TO '{_quote_path(out)}' "
            f"(FORMAT PARQUET, COMPRESSION {compression})"
        )
    finally:
        conn.close()

    log.debug("Wrote parquet: %s (%d rows)", out, len(df))
    return out


def consolidate_parquet(
    parts_dir: str | Path,
    dst: str | Path,
    *,
    con: Any = None,
    compression: str = "zstd",
) -> Path:
    """Merge every `part-*.parquet` in `parts_dir` into a single parquet file."""
    parts_dir = Path(parts_dir).expanduser()
    out = Path(dst).expanduser()

    if not any(parts_dir.glob("part-*.parquet")):
        raise FileNotFoundError(f"No parquet parts found in {parts_dir}")

    glob = str(parts_dir / "part-*.parquet").replace("'", "''")
    out.parent.mkdir(parents=True, exist_ok=True)

    conn = _con(con)
    own = con is None
    try:
        conn.execute(
            f"COPY (SELECT * FROM read_parquet('{glob}', union_by_name=true)) "
            f"TO '{_quote_path(out)}' (FORMAT PARQUET, COMPRESSION {compression})"
        )
    finally:
        if own:
            conn.close()

    return out


class ParquetPartWriter:
    """
    Write DataFrame batches to temporary Parquet parts and consolidate at the end.

    Avoids re-reading and rewriting the growing output file after every batch
    (which is O(n^2) in I/O for chunked pipelines).
    """

    def __init__(
        self,
        dst: str | Path,
        *,
        con: Any = None,
        compression: str = "zstd",
    ) -> None:
        self.dst = Path(dst).expanduser()
        self.parts_dir = self.dst.parent / f".{self.dst.name}.parts"
        self.con = con
        self.compression = compression
        self._parts = 0

        if self.parts_dir.exists():
            shutil.rmtree(self.parts_dir)
        self.parts_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_parts(self) -> bool:
        return self._parts > 0

    def write(self, df: Any) -> None:
        """Append a batch as a new part (no-op for empty batches)."""
        if df is None or len(df) == 0:
            return

        part = self.parts_dir / f"part-{self._parts:06d}.parquet"
        write_parquet(df, part, compression=self.compression)
        self._parts += 1

    def finish(self) -> Path | None:
        """Consolidate all parts into `dst`; returns None if nothing was written."""
        try:
            if not self.has_parts:
                return None
            return consolidate_parquet(
                self.parts_dir,
                self.dst,
                con=self.con,
                compression=self.compression,
            )
        finally:
            shutil.rmtree(self.parts_dir, ignore_errors=True)

    def abort(self) -> None:
        """Drop temporary parts without producing an output file."""
        shutil.rmtree(self.parts_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Streaming NDJSON
# ---------------------------------------------------------------------------
def _open_text(path: str | Path):
    p = Path(path).expanduser()
    suffix = p.suffix.lower()

    if suffix == ".gz":
        return gzip.open(p, "rt", encoding="utf-8")
    if suffix == ".bz2":
        return bz2.open(p, "rt", encoding="utf-8")
    return p.open("r", encoding="utf-8")


def _is_tar_zstd(path: Path) -> bool:
    """True for .tar.zst, .tar.zstd and .tzst archives."""
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes[-1:] == [".tzst"]:
        return True
    return (
        len(suffixes) >= 2
        and suffixes[-2] == ".tar"
        and suffixes[-1] in {".zst", ".zstd"}
    )


@contextmanager
def _open_zstd_binary(path: Path):
    """Open a zstd stream, preferring the Python 3.14 stdlib implementation."""
    try:
        from compression import zstd  # type: ignore[import-not-found]

        with zstd.open(path, "rb") as fh:
            yield fh
        return
    except ImportError:
        pass

    try:
        import zstandard  # type: ignore[import-not-found]
    except ImportError:
        zstandard = None

    if zstandard is not None:
        with path.open("rb") as raw:
            reader = zstandard.ZstdDecompressor().stream_reader(raw)
            try:
                yield reader
            finally:
                reader.close()
        return

    zstd_bin = shutil.which("zstd")
    if not zstd_bin:
        raise RuntimeError(
            f"Cannot read {path}: install zstandard or the zstd CLI, "
            "or use Python 3.14+."
        )

    proc = subprocess.Popen(
        [zstd_bin, "-dc", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    try:
        yield proc.stdout
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.terminate()
        try:
            _, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
        if proc.returncode not in (0, -13, 141) and stderr:
            log.warning(
                "zstd failed for %s: %s",
                path,
                stderr.decode("utf-8", "replace")[:300],
            )


def _iter_tar_zstd_lines(path: Path) -> Iterator[str]:
    """Yield decoded lines from every NDJSON/JSONL member of a .tar.zst."""
    found_member = False
    with _open_zstd_binary(path) as raw:
        with tarfile.open(fileobj=raw, mode="r|") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                name = member.name.lower()
                if not name.endswith((".ndjson", ".jsonl")):
                    continue
                found_member = True
                fh = archive.extractfile(member)
                if fh is None:
                    continue
                with fh:
                    for line in fh:
                        yield line.decode("utf-8", errors="replace")
    if not found_member:
        raise ValueError(f"No NDJSON/JSONL members found in {path}")


def _iter_text_lines(path: Path) -> Iterator[str]:
    """Yield text lines from plain, gzip/bz2, zstd or tar.zstd inputs."""
    if _is_tar_zstd(path):
        yield from _iter_tar_zstd_lines(path)
        return

    if path.suffix.lower() in {".zst", ".zstd"}:
        with _open_zstd_binary(path) as raw:
            for line in raw:
                yield line.decode("utf-8", errors="replace")
        return

    with _open_text(path) as fh:
        yield from fh


def iter_ndjson(
    path: str | Path,
    *,
    skip_errors: bool = True,
) -> Iterator[dict[str, Any]]:
    """
    Stream a newline-delimited JSON file object by object.

    Never materialises the full file. `.gz`, `.bz2`, `.zst`, `.tar.zst` and
    `.tar.zstd` are handled by suffix. Malformed lines are skipped with a
    warning when `skip_errors=True`.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(p)

    for lineno, line in enumerate(_iter_text_lines(p), 1):
        line = line.strip()
        if not line:
            continue

        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            if not skip_errors:
                raise ValueError(f"{p}:{lineno}: invalid JSON: {exc}") from exc
            log.warning("Skipping malformed NDJSON at %s:%d (%s)", p, lineno, exc)
            continue

        if isinstance(obj, dict):
            yield obj
        elif skip_errors:
            log.warning("Skipping non-object NDJSON value at %s:%d", p, lineno)
        else:
            raise ValueError(f"{p}:{lineno}: expected a JSON object")


def batched(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield lists of at most `size` items from `iterable`."""
    if size <= 0:
        raise ValueError("batch size must be > 0")

    batch: list[T] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def iter_ndjson_batches(
    path: str | Path,
    *,
    batch_size: int = 1_000,
    skip_errors: bool = True,
) -> Iterator[list[dict[str, Any]]]:
    """Stream NDJSON in fixed-size batches."""
    yield from batched(iter_ndjson(path, skip_errors=skip_errors), batch_size)


def count_ndjson_lines(path: str | Path) -> int:
    """Count non-empty lines in an NDJSON file without parsing them."""
    total = 0
    for line in _iter_text_lines(Path(path).expanduser()):
        if line.strip():
            total += 1
    return total
