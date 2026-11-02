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

    1. Genera `content_hash` si no existe.
    2. Elimina duplicados por `content_hash` **solo entre posts con texto**:
       los posts vacíos comparten `SHA256("")` y no deben colapsarse.
    3. Elimina duplicados por la clave natural `(thread_id, post_id)`.
    """
    before = len(df)
    df = df.copy()

    has_text_col = "text_clean" in df.columns
    if "content_hash" not in df.columns and has_text_col:
        df["content_hash"] = df["text_clean"].apply(
            lambda x: content_hash(x) if isinstance(x, str) and x else None
        )

    if "content_hash" in df.columns:
        if has_text_col:
            has_text = df["text_clean"].fillna("").astype(str).str.len() > 0
        else:
            has_text = df["content_hash"].notna()

        duplicate_hash = has_text & df["content_hash"].duplicated(keep="first")
        df = df.loc[~duplicate_hash]

    if "thread_id" in df.columns and "post_id" in df.columns:
        df = df.drop_duplicates(subset=["thread_id", "post_id"])

    after = len(df)
    log.info(f"Deduplicación: {before} -> {after} (-{before - after})")
    return df

