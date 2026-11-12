# Role: semantic validation of one LLM payload against the annotation contract.
# Connects to: annotation/labels, annotation/proposal, classification/batch.

from __future__ import annotations

from typing import Any

from keklab.annotation.labels import EXCLUSIVE_LABELS, FRAME_LABELS
from keklab.annotation.proposal import TaskRecord, evidence_in_text

SPECIFIC_PREJUDICE_FRAMES: frozenset[str] = frozenset(
    {
        "antisemitism",
        "islamophobia",
        "rusophobia",
        "sinophobia",
        "misogyny",
        "transphobia",
        "homophobia",
    }
)
GENERIC_PREJUDICE_FRAMES: frozenset[str] = frozenset(
    {"ethnonationalism", "racism"}
)


def validate_payload(payload: dict[str, Any], task: TaskRecord) -> list[str]:
    """Return the contract violations of one payload, empty when it is valid.

    The checks mirror the annotation contract: known frame slugs, `none` and
    `unclear` exclusivity, ordinal toxicity 0-3, confidence in [0, 1], the
    right `post_id` and verbatim evidence.
    """
    issues: list[str] = []

    response_post_id = payload.get("post_id")
    if response_post_id is not None and str(response_post_id) != task.post_id:
        issues.append(f"post_id must be {task.post_id!r}")

    labels = payload.get("frame_labels")
    if isinstance(labels, str):
        labels = [labels]
    if not isinstance(labels, list) or not labels:
        issues.append("frame_labels must be a non-empty list")
    else:
        normalized = [str(label).strip().lower() for label in labels]
        unknown = sorted(
            {label for label in normalized if label not in FRAME_LABELS}
        )
        if unknown:
            issues.append(
                f"unknown frame labels {unknown}; allowed: {list(FRAME_LABELS)}"
            )
        exclusive = [
            label for label in normalized if label in EXCLUSIVE_LABELS
        ]
        if exclusive and len(normalized) > 1:
            issues.append(
                f"{exclusive[0]!r} cannot be combined with other frame labels"
            )

    toxicity = payload.get("toxicity")
    if isinstance(toxicity, bool) or not isinstance(toxicity, int):
        issues.append("toxicity must be an integer between 0 and 3")
    elif not 0 <= toxicity <= 3:
        issues.append("toxicity must be between 0 and 3")

    confidence = payload.get("confidence")
    if confidence is not None:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            issues.append("confidence must be a number between 0 and 1")
        elif not 0.0 <= float(confidence) <= 1.0:
            issues.append("confidence must be between 0 and 1")

    evidence = payload.get("evidence")
    if evidence is None:
        evidence_items: list[str] = []
    elif isinstance(evidence, str):
        evidence_items = [evidence]
    elif isinstance(evidence, list):
        evidence_items = [str(item) for item in evidence]
    else:
        evidence_items = []
        issues.append("evidence must be a list of strings")

    not_verbatim = [
        item.strip()
        for item in evidence_items
        if item.strip()
        and not evidence_in_text(item, [task.text_raw, task.text_clean])
    ]
    if not_verbatim:
        issues.append(
            f"{len(not_verbatim)} evidence fragment(s) are not verbatim "
            "in the post text"
        )

    return issues


def rule_violations(frame_labels: list[str]) -> list[str]:
    """Return the codebook rules broken by a frame set.

    `none` and `unclear` are exclusive, and specific prejudice frames
    supersede the generic `ethnonationalism` and `racism` labels.
    """
    violations: list[str] = []
    selected = {str(label).strip().lower() for label in frame_labels}

    exclusive = sorted(selected & EXCLUSIVE_LABELS)
    if exclusive and len(selected) > 1:
        violations.append(f"{exclusive[0]} combined with other frames")

    if selected & SPECIFIC_PREJUDICE_FRAMES and selected & GENERIC_PREJUDICE_FRAMES:
        violations.append("specific prejudice combined with generic prejudice")

    return violations


def repair_prompt(
    prompt: str,
    raw_text: str,
    issues: list[str],
    *,
    max_previous_chars: int = 800,
) -> str:
    """Build the follow-up prompt used to repair an invalid answer."""
    detail = "; ".join(issues) if issues else "invalid output"
    previous = str(raw_text or "").strip()[:max_previous_chars]
    return (
        prompt.rstrip()
        + "\n\nYour previous answer was rejected: "
        + detail
        + ". Previous answer:\n"
        + previous
        + "\n\nReturn only the corrected JSON object with the same fields, "
        "using only the allowed frame slugs and verbatim evidence copied "
        "from the post text. Do not add any commentary."
    )
