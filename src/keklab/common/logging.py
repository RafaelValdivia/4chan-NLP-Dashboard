# Role: structured-ish logging shared by every layer.
# Connects to: ingest, formal, classic, generative, eval.

from __future__ import annotations

import logging
import os
import sys
from typing import IO

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_CONFIGURED = False


def configure_logging(
    level: str | int | None = None,
    *,
    stream: IO[str] | None = None,
) -> None:
    """Configure the `keklab` logger once."""
    global _CONFIGURED
    logger = logging.getLogger("keklab")

    if _CONFIGURED:
        if level is not None:
            logger.setLevel(level)
        return

    resolved = level or os.environ.get("KEKLAB_LOG_LEVEL", "INFO")
    logger.setLevel(resolved)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
        logger.addHandler(handler)

    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the `keklab` namespace."""
    configure_logging()
    if name is None:
        return logging.getLogger("keklab")
    if not name.startswith("keklab"):
        name = f"keklab.{name}"
    return logging.getLogger(name)
