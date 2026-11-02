# Role: canonical schemas (Post, Thread, Annotation, Entity).
# Connects to: ingest, formal/cleaning, formal/features, ner/entity_schema, analysis/*.
# Unidad de análisis: POST (agrupado por thread_id)

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Post(BaseModel):
    """Post canónico. Unidad de análisis."""
    post_id: str
    thread_id: str
    board: str = "pol"
    timestamp_utc: datetime | None = None
    is_op: bool = False
    subject: str | None = None
    raw_html: str | None = None
    text_clean: str | None = None
    quotes: list[str] = Field(default_factory=list)
    country: str | None = None
    media_refs: list[str] = Field(default_factory=list)
    source: Literal["kek", "fourplebs"] = "kek"
    content_hash: str
    period: Literal["hist_2016_2019", "recent_2020_plus"] | None = None
    lang: str | None = None
    # Thread-level features
    thread_depth: int | None = None
    thread_cite_count: int | None = None
    thread_greentext_count: int | None = None
    thread_link_count: int | None = None
    # Post-level structural features
    greentext_count: int | None = None
    quote_count: int | None = None


class Thread(BaseModel):
    """Hilo con posts. Unidad de agrupación."""
    thread_id: str
    board: str = "pol"
    posts: list[Post] = Field(default_factory=list)
    created_utc: datetime | None = None
    archived: bool | None = None
    depth: int = 0
    cite_count: int = 0
    greentext_count: int = 0


class Annotation(BaseModel):
    """Anotación. Oro = un solo anotador."""
    post_id: str
    thread_id: str | None = None
    source: Literal["kek", "fourplebs"] | None = None
    period: Literal["hist_2016_2019", "recent_2020_plus"] | None = None
    content_hash: str | None = None
    frame_labels: list[str] = Field(default_factory=list)
    toxicity: int | None = Field(default=None, ge=0, le=3)
    annotator: str
    round: int = 1
    tier: Literal["gold", "silver"] = "gold"
    guideline_version: str
    annotated_utc: datetime | None = None
    notes: str | None = None

    @field_validator("frame_labels")
    @classmethod
    def _validate_frame_labels(cls, value: list[str]) -> list[str]:
        if not value:
            return value
        # Local import keeps the canonical vocabulary in the annotation layer.
        from keklab.annotation.labels import normalize_frame_labels

        return normalize_frame_labels(value)


class Entity(BaseModel):
    """Entidad extraída."""
    post_id: str
    text_span: str
    type: str
    canonical_id: str | None = None
    method: Literal["gliner", "spacy", "rules"] = "gliner"
    confidence: float | None = None
