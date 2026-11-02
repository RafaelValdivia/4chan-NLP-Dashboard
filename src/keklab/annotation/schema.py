# Role: annotation records and candidate-post schema.
# Connects to: formal/schema, annotation/labels, annotation/store, annotation/sampler.

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from keklab.annotation.labels import normalize_frame_labels
from keklab.formal.schema import Annotation


class ContextPost(BaseModel):
    """A nearby post shown to the annotator for context."""

    model_config = ConfigDict(extra="forbid")

    post_id: str
    text_raw: str = ""
    is_op: bool = False


class SampleContext(BaseModel):
    """Thread context for one candidate post."""

    model_config = ConfigDict(extra="forbid")

    op: ContextPost | None = None
    parents: list[ContextPost] = Field(default_factory=list)


class SamplePost(BaseModel):
    """A post selected for human annotation, with enough context to label it."""

    model_config = ConfigDict(extra="forbid")

    post_id: str
    thread_id: str
    source: Literal["kek", "fourplebs"]
    period: Literal["hist_2016_2019", "recent_2020_plus"] | None = None
    timestamp_utc: datetime | None = None
    subject: str | None = None
    text_raw: str = ""
    text_clean: str = ""
    quotes: list[str] = Field(default_factory=list)
    content_hash: str
    is_op: bool = False
    country: str | None = None
    stratum: dict[str, Any] = Field(default_factory=dict)
    context: SampleContext = Field(default_factory=SampleContext)

    @field_validator("post_id", "thread_id", "content_hash")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("value must not be empty")
        return str(value)


class AnnotationRecord(Annotation):
    """Validated annotation written by the terminal CLI."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("frame_labels", mode="before")
    @classmethod
    def _validate_frames(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        return normalize_frame_labels(value or [])

    @model_validator(mode="after")
    def _validate_toxicity_present(self) -> AnnotationRecord:
        if self.toxicity is None:
            raise ValueError("toxicity is required (0-3)")
        return self


def annotation_key(record: Annotation) -> tuple[str, str | None, str | None, int, str]:
    """Stable key for resuming/updating one annotation."""
    return (
        record.post_id,
        record.thread_id,
        record.source,
        record.round,
        record.annotator,
    )


def sample_key(sample: SamplePost) -> tuple[str, str, str]:
    return (sample.post_id, sample.thread_id, sample.source)


def annotation_sample_key(record: Annotation) -> tuple[str, str | None, str | None]:
    """Link an annotation back to its candidate sample."""
    return (record.post_id, record.thread_id, record.source)
