# Role: shared frame/toxicity editing used by human and AI-assisted sessions.
# Connects to: annotation/labels, annotation/cli, annotation/review.

from __future__ import annotations

from typing import Iterable

from keklab.annotation.labels import (
    TOXICITY_DESCRIPTIONS,
    apply_frame_toggle,
    parse_frame_numbers,
)


def apply_edit_command(
    frames: Iterable[str],
    toxicity: int | None,
    command: str,
) -> tuple[list[str], int | None, str] | None:
    """Apply a label/toxicity edit command.

    Returns `(frames, toxicity, message)` when the command edits state, or
    `None` when it is not an edit command. Raises `ValueError` for invalid
    frame numbers.
    """
    current = list(frames)
    lowered = command.strip().lower()

    if lowered in {"n", "none"}:
        return apply_frame_toggle(current, ["none"]), toxicity, "frames: none"

    if lowered in {"u", "unclear"}:
        return (
            apply_frame_toggle(current, ["unclear"]),
            toxicity,
            "frames: unclear",
        )

    if lowered in {"c", "clear"}:
        return [], toxicity, "frames: (none)"

    if lowered in {"t", "tox"}:
        updated = 0 if toxicity is None else (toxicity + 1) % 4
        return (
            current,
            updated,
            f"toxicity = {updated}: {TOXICITY_DESCRIPTIONS[updated]}",
        )

    if not command.strip():
        return None

    labels = parse_frame_numbers(command)
    updated_frames = apply_frame_toggle(current, labels)
    message = "frames: " + (", ".join(updated_frames) if updated_frames else "(none)")
    return updated_frames, toxicity, message


def format_state(frames: Iterable[str], toxicity: int | None) -> str:
    frames = list(frames)
    return (
        "Selected frames: "
        + (", ".join(frames) if frames else "(none)")
        + " | Toxicity: "
        + (
            f"{toxicity} — {TOXICITY_DESCRIPTIONS[toxicity]}"
            if toxicity is not None
            else "(unset)"
        )
    )
