"""
Centralized logging configuration for the desktop app.

Usage:
    from app.desktop.utils.log_config import logger
    logger.info("message")

Or for module-specific loggers:
    import logging
    log = logging.getLogger(__name__)
"""
from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """
    Configure the root logger once.
    Call this early in app startup (e.g. run.py).

    Levels: DEBUG, INFO, WARNING, ERROR
    Override with env var LOG_LEVEL.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    level_name = os.environ.get("LOG_LEVEL", level).upper()
    numeric = getattr(logging, level_name, logging.INFO)

    fmt = logging.Formatter(
        "[%(levelname).1s %(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(numeric)

    if not root.handlers:
        root.addHandler(handler)
    else:
        for h in root.handlers:
            h.setFormatter(fmt)

    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


setup_logging()

logger = logging.getLogger("nusic")
