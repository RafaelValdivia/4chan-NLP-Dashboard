# Role: load ROTLK/Kek dump (ndjson/json). Map to canonical Post schema.
# Connects to: formal/schema, formal/cleaning, formal/features, common/io, common/paths.
# Historical: 2016–2019. Source: Raiders of the Lost Kek.
#
# CRÍTICO: NUNCA cargar el dump entero a memoria.
# Usa formal.cleaning para distinguir kek vs fourplebs.

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

from keklab.common.io import _con, _src_ndjson, write_parquet
from keklab.common.logging import get_logger
from keklab.formal.cleaning import clean_post
from keklab.formal.features import post_structural_features, thread_features
from keklab.formal.schema import Post

log = get_logger(__name__)


def _content_hash(text: str) -> str:
    """SHA256 hash del texto limpio para deduplicación."""
    h = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return h


def load_kek_ndjson(path: str | Path, *, limit_threads: int | None = None) -> pd.DataFrame:
    """
    DEPRECATED para corpus completo.
    Usa solo para inspección/debug con limit_threads.
    """
    if limit_threads is not None:
        src_sql = _src_ndjson(path)
        sql = f"SELECT * FROM {src_sql} LIMIT {limit_threads}"
        return _con(None).execute(sql).df()
    raise RuntimeError(
        "load_kek_ndjson NO debe usarse para cargar el dump completo de ROTLK. "
        "Usa ndjson_expand_to_parquet() o iter_kek_posts_chunked()."
    )


def ndjson_expand_to_parquet(
    src: str | Path,
    dst: str | Path,
    *,
    con=None,
) -> None:
    """
    Aplana hilos ROTLK: unnest posts -> un post por fila, SIN cargar todo en memoria.
    Usa DuckDB COPY.
    """
    c = _con(con)
    own = con is None
    try:
        src_sql = _src_ndjson(src)
        sql = f"""
        COPY (
          SELECT
            p.no::VARCHAR AS post_id,
            (t.posts[1]).no::VARCHAR AS thread_id,
            p.com AS raw_html,
            p.time AS time_unix,
            p.resto AS resto,
            p.sub AS subject,
            p.country AS country,
            p.filename AS filename,
            p.tim AS tim
          FROM {src_sql} t
          CROSS JOIN UNNEST(t.posts) AS p
        ) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        c.execute(sql)
        log.info(f"Expanded ROTLK ndjson -> parquet: {dst}")
    finally:
        if own:
            c.close()


def iter_kek_posts_chunked(
    expanded_parquet: str | Path,
    *,
    chunk_size: int = 50_000,
    con=None,
) -> Iterator[pd.DataFrame]:
    """
    Itera posts aplanados en chunks. Usa formal.cleaning para ROTLK.
    Nunca materializa todo el corpus.
    """
    c = _con(con)
    own = con is None
    try:
        sql = f"SELECT * FROM read_parquet('{expanded_parquet}', union_by_name = true)"
        cur = c.execute(sql)
        while True:
            chunk = cur.fetch_df_chunk(chunk_size)
            if chunk.empty:
                break
            # Agrupar por thread para calcular features de hilo
            out_rows = []
            # Procesar por thread en chunk
            for thread_id, thread_chunk in chunk.groupby("thread_id"):
                thread_htmls = [str(r.get("raw_html") or "") for _, r in thread_chunk.iterrows()]
                tfeat = thread_features(thread_htmls)
                for _, r in thread_chunk.iterrows():
                    raw_html = r.get("raw_html") or ""
                    text_clean, quotes, greentext_count = clean_post(raw_html, source="kek")
                    pfeat = post_structural_features(raw_html)
                    ph = _content_hash(text_clean)
                    timev = r.get("time_unix")
                    if isinstance(timev, (int, float)):
                        ts = datetime.fromtimestamp(timev, tz=timezone.utc)
                    else:
                        ts = datetime.now(timezone.utc)
                    post_id = str(r.get("post_id") or "")
                    resto = r.get("resto")
                    is_op = resto == 0
                    media_refs = []
                    if r.get("filename"):
                        media_refs.append(str(r.get("filename")))
                    if r.get("tim"):
                        media_refs.append(str(r.get("tim")))
                    out_rows.append(
                        Post(
                            post_id=post_id,
                            thread_id=str(thread_id),
                            board="pol",
                            timestamp_utc=ts,
                            is_op=is_op,
                            subject=r.get("subject"),
                            raw_html=raw_html,
                            text_clean=text_clean,
                            quotes=quotes,
                            country=r.get("country"),
                            media_refs=media_refs,
                            source="kek",
                            content_hash=ph,
                            period="hist_2016_2019",
                            thread_depth=tfeat.get("thread_depth"),
                            thread_cite_count=tfeat.get("thread_cite_count"),
                            thread_greentext_count=tfeat.get("thread_greentext_count"),
                            quote_count=pfeat.get("quote_count"),
                            greentext_count=greentext_count,
                        ).model_dump()
                    )
            yield pd.DataFrame(out_rows)
    finally:
        if own:
            c.close()


def canonicalize_kek_posts_chunked(
    expanded_parquet: str | Path,
    out_parquet: str | Path,
    *,
    chunk_size: int = 50_000,
    con=None,
) -> None:
    """Canonicaliza ROTLK a parquet canónico por chunks. Sin acumular todo en memoria."""
    first = True
    for chunk_df in iter_kek_posts_chunked(expanded_parquet, chunk_size=chunk_size, con=con):
        if chunk_df.empty:
            continue
        if first:
            write_parquet(chunk_df, out_parquet)
            first = False
        else:
            existing = pd.read_parquet(out_parquet)
            combined = pd.concat([existing, chunk_df], ignore_index=True)
            write_parquet(combined, out_parquet)
    log.info(f"Canonicalized ROTLK -> {out_parquet}")


def canonicalize_fourplebs_thread(thread: dict, source: str = "fourplebs") -> list[dict]:
    """Canonicaliza un thread obtenido desde API de 4plebs usando formal.cleaning."""
    posts = thread.get("posts") or []
    if not posts:
        return []
    thread_htmls = [str(p.get("com") or "") for p in posts]
    tfeat = thread_features(thread_htmls)
    out = []
    for p in posts:
        raw_html = p.get("com") or ""
        text_clean, quotes, greentext_count = clean_post(raw_html, source=source)
        pfeat = post_structural_features(raw_html)
        timev = p.get("time")
        if isinstance(timev, (int, float)):
            ts = datetime.fromtimestamp(timev, tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        post_id = str(p.get("no") or "")
        thread_id = str(posts[0].get("no") or post_id)
        resto = p.get("resto")
        is_op = resto == 0
        ph = _content_hash(text_clean)
        media_refs = []
        if p.get("filename"):
            media_refs.append(str(p.get("filename")))
        if p.get("tim"):
            media_refs.append(str(p.get("tim")))
        post = Post(
            post_id=post_id,
            thread_id=thread_id,
            board="pol",
            timestamp_utc=ts,
            is_op=is_op,
            subject=p.get("sub"),
            raw_html=raw_html,
            text_clean=text_clean,
            quotes=quotes,
            country=p.get("country"),
            media_refs=media_refs,
            source=source,
            content_hash=ph,
            period="recent_2020_plus" if source == "fourplebs" else "hist_2016_2019",
            thread_depth=tfeat.get("thread_depth"),
            thread_cite_count=tfeat.get("thread_cite_count"),
            thread_greentext_count=tfeat.get("thread_greentext_count"),
            quote_count=pfeat.get("quote_count"),
            greentext_count=greentext_count,
        )
        out.append(post.model_dump())
    return out


def save_canonical(posts_df: pd.DataFrame, out_path: str | Path) -> None:
    """Guarda posts canónicos a parquet."""
    write_parquet(posts_df, out_path)
    log.info(f"Saved {len(posts_df)} posts to {out_path}")



