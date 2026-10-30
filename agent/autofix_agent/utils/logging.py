"""
Logging configuration for AutoFix Agent.
"""
from __future__ import annotations

import logging
import os
import sys

_DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    name: str = "autofix_agent",
    level: str | int | None = None,
) -> logging.Logger:
    """
    Configure and return a standardized logger for AutoFix Agent.
    """
    if level is None:
        level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(_DEFAULT_LOG_FORMAT, datefmt=_DATE_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger configured with standard settings."""
    setup_logger("autofix_agent")
    return logging.getLogger(f"autofix_agent.{name}")
