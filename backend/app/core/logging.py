"""
logging.py — Structured JSON logging setup for the application.
Call configure_logging() once at startup (in main.py).
"""

import logging
import sys


def configure_logging() -> None:
    """Configure root logger to emit structured log lines to stdout."""
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Quieten noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
