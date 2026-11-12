# Role: annotation label vocabulary and validation rules.
# Connects to: annotation/schema, annotation/cli, docs/annotation_guidelines.

from __future__ import annotations

from typing import Iterable

# Order is also the numeric order shown by the interactive CLI.
FRAME_LABELS: tuple[str, ...] = (
    "conspiracy",
    "ethnonationalism",
    "racism",
    "antisemitism",
    "islamophobia",
    "rusophobia",
    "sinophobia",
    "misogyny",
    "transphobia",
    "homophobia",
    "institutional_distrust",
    "violence_glorification",
    "accelerationism",
    "meta_topic",
    "none",
    "unclear",
)

EXCLUSIVE_LABELS: frozenset[str] = frozenset({"none", "unclear"})

# Spanish display names for the web UI. The English identifiers stay canonical
# everywhere else (files, SQL, predictions); only the presentation layer uses
# these.
FRAME_LABELS_ES: dict[str, str] = {
    "conspiracy": "Conspiración",
    "ethnonationalism": "Etnonacionalismo",
    "racism": "Racismo",
    "antisemitism": "Antisemitismo",
    "islamophobia": "Islamofobia",
    "rusophobia": "Rusofobia",
    "sinophobia": "Sinofobia",
    "misogyny": "Misoginia",
    "transphobia": "Transfobia",
    "homophobia": "Homofobia",
    "institutional_distrust": "Desconfianza institucional",
    "violence_glorification": "Glorificación de la violencia",
    "accelerationism": "Aceleracionismo",
    "meta_topic": "Meta del board",
    "none": "Ninguno",
    "unclear": "Incierto",
}

TOXICITY_LABELS_ES: dict[int, str] = {
    0: "Neutro",
    1: "Leve",
    2: "Explícita",
    3: "Amenaza o incitación",
}

# Frames retired after the 200-post pilot (09-11-2026). Historical artifacts
# still contain them; the loader drops them for backward compatibility. A set
# that only contained retired labels collapses to `none`. Interactive editing
# rejects them because `apply_frame_toggle` validates against `FRAME_LABELS`.
RETIRED_FRAME_LABELS: frozenset[str] = frozenset({"eugenics", "ableism"})

# Previous vocabulary names that still appear in annotations or external data.
# They are rewritten on load so old files remain readable.
FRAME_ALIASES: dict[str, str] = {
    "antifeminism": "misogyny",
}

FRAME_DESCRIPTIONS: dict[str, str] = {
    "conspiracy": "Explicit secret plot or coordination by elites/groups.",
    "ethnonationalism": "Generic national/ethnic purity or hierarchy not covered by a more specific label.",
    "racism": "Racial/ethnic prejudice, slurs, segregation or hierarchy not covered by a specific group label.",
    "antisemitism": "Hostility, tropes or prejudice targeting Jews.",
    "islamophobia": "Hostility or prejudice targeting Muslims/Islam.",
    "rusophobia": "Hostility or prejudice targeting Russians/Russia.",
    "sinophobia": "Hostility or prejudice targeting Chinese/China.",
    "misogyny": "Hostility, contempt or objectification toward women as a class; female inferiority or opposition to women's rights.",
    "transphobia": "Hostility, mockery or prejudice targeting trans people or denying their identity.",
    "homophobia": "Hostility, mockery or prejudice targeting gay or lesbian people.",
    "institutional_distrust": "Generalized distrust of state/media/academia/elections without an explicit conspiracy.",
    "violence_glorification": "Praise, celebration or encouragement of violence (not mere discussion).",
    "accelerationism": "Desire to accelerate collapse, conflict or destabilization.",
    "meta_topic": "Board meta, moderation, raids, online culture.",
    "none": "No recognizable frame.",
    "unclear": "Insufficient context, truncation or genuine ambiguity.",
}

TOXICITY_DESCRIPTIONS: dict[int, str] = {
    0: "Neutral / no toxicity.",
    1: "Mild insult, hostility or edginess.",
    2: "Explicit dehumanization, slur, harassment or group-targeted hate.",
    3: "Threat, incitement or celebration of violence against real people.",
}

# Seed terms for targeted sampling of rare frames. These are not classifiers;
# they only prioritise candidate posts for human annotation.
TARGETED_SEARCH_TERMS: dict[str, tuple[str, ...]] = {
    "rusophobia": ("russia", "russian", "putin", "russo"),
    "sinophobia": ("china", "chinese", "ccp", "wuhan"),
    "accelerationism": ("accelerate", "accelerationism", "collapse", "boogaloo"),
    "racism": (
        "racism",
        "racist",
        "racial",
        "segregation",
        "white supremacy",
        "white nationalist",
        "white nationalism",
        "miscegenation",
    ),
    "transphobia": (
        "transphobia",
        "transphobic",
        "tranny",
        "transgender",
        "transsexual",
        "trans woman",
        "trans women",
        "troon",
    ),
    "homophobia": (
        "homophobia",
        "homophobic",
        "faggot",
        "fag",
        "homosexual",
        "gay",
        "lesbian",
        "sodomy",
        "dyke",
    ),
    "misogyny": (
        "misogyny",
        "misogynist",
        "feminism",
        "feminist",
        "femoid",
        "femoids",
        "suffragette",
        "misandry",
        "women's rights",
        "female privilege",
        "slut",
        "whore",
    ),
}

FRAME_INDEX: dict[int, str] = {
    index: label for index, label in enumerate(FRAME_LABELS, start=1)
}


def normalize_frame_labels(labels: Iterable[str]) -> list[str]:
    """Normalize, validate and de-duplicate frame labels (order-preserving).

    Labels retired after the pilot (`RETIRED_FRAME_LABELS`) are accepted for
    backward compatibility with historical files but are dropped. If nothing
    remains, the record collapses to `none`.
    """
    normalized: list[str] = []
    saw_retired = False
    for raw in labels:
        label = str(raw).strip().lower()
        label = FRAME_ALIASES.get(label, label)
        if not label:
            continue
        if label in RETIRED_FRAME_LABELS:
            saw_retired = True
            continue
        if label not in FRAME_LABELS:
            valid = ", ".join(FRAME_LABELS)
            raise ValueError(f"Unknown frame label {label!r}; expected one of: {valid}")
        if label not in normalized:
            normalized.append(label)

    if not normalized:
        if saw_retired:
            return ["none"]
        raise ValueError("At least one frame label is required (use 'none' if no frame applies).")

    exclusive = [label for label in normalized if label in EXCLUSIVE_LABELS]
    if exclusive and len(normalized) > 1:
        raise ValueError(
            f"{exclusive[0]!r} cannot be combined with other frame labels"
        )

    return normalized


def apply_frame_toggle(
    current: Iterable[str],
    labels: Iterable[str],
) -> list[str]:
    """Toggle labels while preserving the none/unclear exclusivity rule."""
    selected = list(dict.fromkeys(current))
    for label in labels:
        label = label.strip().lower()
        label = FRAME_ALIASES.get(label, label)
        if label not in FRAME_LABELS:
            raise ValueError(f"Unknown frame label: {label}")
        if label in EXCLUSIVE_LABELS:
            # Selecting none/unclear replaces everything else.
            selected = [label]
            continue
        selected = [item for item in selected if item not in EXCLUSIVE_LABELS]
        if label in selected:
            selected.remove(label)
        else:
            selected.append(label)
    return selected


def parse_frame_numbers(text: str) -> list[str]:
    """Parse space/comma-separated 1-based frame numbers into labels."""
    labels: list[str] = []
    for token in text.replace(",", " ").split():
        try:
            number = int(token)
        except ValueError as exc:
            raise ValueError(f"Invalid frame number: {token!r}") from exc
        if number not in FRAME_INDEX:
            raise ValueError(f"Frame number out of range: {number}")
        labels.append(FRAME_INDEX[number])
    return labels


def format_frame_menu() -> str:
    """Multi-line frame menu for the terminal."""
    lines = ["Frames:"]
    for number, label in FRAME_INDEX.items():
        lines.append(f"  {number:>2}. {label:<24} {FRAME_DESCRIPTIONS[label]}")
    return "\n".join(lines)
