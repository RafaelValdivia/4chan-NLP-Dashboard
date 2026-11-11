# Role: JSON contract for the local LLM silver annotator.
# Connects to: annotation/labels, annotation/schema, classification/backends.

from __future__ import annotations

from typing import Any

from keklab.annotation.labels import FRAME_LABELS


def output_json_schema() -> dict[str, Any]:
    """JSON Schema the model should follow.

    `post_id`, `frame_labels` and `toxicity` are required because they are the
    minimum needed to build a silver annotation. Confidence, rationale and
    evidence are optional at the grammar level: a model that omits them still
    produces a usable annotation, while a missing label does not.
    """
    return {
        "type": "object",
        "properties": {
            "post_id": {"type": "string"},
            "frame_labels": {
                "type": "array",
                "items": {"type": "string", "enum": list(FRAME_LABELS)},
                "minItems": 1,
                "uniqueItems": True,
            },
            "toxicity": {"type": "integer", "enum": [0, 1, 2, 3]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "rationale": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["post_id", "frame_labels", "toxicity"],
        "additionalProperties": False,
    }


def response_format() -> dict[str, Any]:
    """llama-cpp-python `response_format` payload."""
    return {
        "type": "json_object",
        "schema": output_json_schema(),
    }
