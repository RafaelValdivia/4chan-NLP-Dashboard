# Role: deduplication by content_hash and (thread_id, post_id).
# Connects to: formal/schema, common/io.
# 
# Deduplicación defensiva:
# - Por content_hash (SHA256 de text_clean)
# - Por (thread_id, post_id)

from __future__ import annotations

import hashlib

import pandas as pd

from keklab.common.logging import get_logger

log = get_logger(__name__)


def content_hash(text: str) -> str:
    """Calcula hash SHA256 del texto."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def dedupe_posts_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplica posts.
    1. Genera content_hash si no existe
    2. Elimina duplicados por content_hash (ignora NaN)
    3. Elimina duplicados por (thread_id, post_id)
    """
    before = len(df)
    df = df.copy()
    if "content_hash" not in df.columns and "text_clean" in df.columns:
        df["content_hash"] = df["text_clean"].apply(lambda x: content_hash(x) if isinstance(x, str) and x else None)
    # por hash de contenido (no colapsar posts con hash None)
    if "content_hash" in df.columns:
        df = df.drop_duplicates(subset=["content_hash"], keep="first")
    # por clave natural
    if "thread_id" in df.columns and "post_id" in df.columns:
        df = df.drop_duplicates(subset=["thread_id", "post_id"])
    after = len(df)
    log.info(f"Deduplicación: {before} -> {after} (-{before - after})")
    return df

