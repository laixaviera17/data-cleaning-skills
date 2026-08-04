"""Runtime correlation identifiers and structured application logging."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def new_run_id(configured: Any = None) -> str:
    """Return a caller-supplied correlation id or generate a portable one."""
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return uuid4().hex


class JsonLogFormatter(logging.Formatter):
    """Format standard LogRecords as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("run_id", "skill", "action", "affected_rows", "result"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_json_logging(level: int | str = logging.INFO) -> logging.Handler:
    """Attach and return one JSON stderr handler on the package logger."""
    logger = logging.getLogger("data_cleaning_skills")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return handler
