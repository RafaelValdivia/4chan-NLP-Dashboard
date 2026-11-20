# Role: error taxonomy for local LLM backends (transport vs systemic vs other).
# Connects to: classification/backends, classification/batch.

from __future__ import annotations

from typing import Any


class BackendError(RuntimeError):
    """Base class for local-LLM backend failures."""

    kind = "other"


class TransportError(BackendError):
    """The server is unreachable or the connection failed (retryable)."""

    kind = "transport"


class SystemicError(BackendError):
    """A server-side condition no retry can fix (context, memory, model)."""

    kind = "systemic"


SYSTEMIC_MARKERS: tuple[str, ...] = (
    "context size has been exceeded",
    "failed to find a memory slot",
    "failed to find free space in the kv cache",
    "out of memory",
    "failed to allocate",
    "unknown model architecture",
    "model is not loaded",
    "model failed to load",
)

TRANSPORT_MARKERS: tuple[str, ...] = (
    "unreachable",
    "connection refused",
    "connection reset",
    "remote end closed",
    "remote disconnected",
    "timed out",
    "timeout",
    "broken pipe",
)


def classify_message(message: str) -> str:
    """Return `systemic`, `transport` or `other` for a backend message."""
    text = str(message or "").lower()
    for marker in SYSTEMIC_MARKERS:
        if marker in text:
            return "systemic"
    for marker in TRANSPORT_MARKERS:
        if marker in text:
            return "transport"
    return "other"


def classify_exception(exc: BaseException) -> str:
    """Return the error kind of an exception raised while annotating."""
    kind = getattr(exc, "kind", None)
    if kind in {"systemic", "transport"}:
        return str(kind)
    return classify_message(str(exc))


def error_payload(exc: BaseException) -> dict[str, Any]:
    """Small JSON-friendly description used in raw rows and reports."""
    return {
        "kind": classify_exception(exc),
        "type": type(exc).__name__,
        "message": str(exc),
    }


__all__ = [
    "BackendError",
    "SystemicError",
    "TransportError",
    "classify_exception",
    "classify_message",
    "error_payload",
]
