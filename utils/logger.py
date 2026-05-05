"""Structured logging setup for telegram-user-api.

Configures the Python root logger with console + optional rotating file output.
All modules use `logging.getLogger("modulename")` for consistent formatting.

Env vars:
    LOG_LEVEL — one of DEBUG, INFO, WARNING, ERROR (default: DEBUG)
    LOG_FILE  — path to rotating log file (default: none, console only)
"""
from __future__ import annotations
import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def configure_logging() -> None:
    """Set up root logger. Idempotent — safe to call from every entry point."""
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    level_name = os.getenv("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.DEBUG)
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    log_file = os.getenv("LOG_FILE", "")
    if log_file:
        fh = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Silence noisy third-party loggers
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.internal").setLevel(logging.WARNING)
