"""Structured logging + PII redaction.

Outputs JSON logs that can be ingested by SIEM. Redacts known sensitive
fields before they leave the process: passwords, tokens, secrets, hashes,
authorization headers, cookies."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from app.config import settings


# --- PII redaction ----------------------------------------------------------

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|pwd|passwd|secret|token|api[_-]?key|cookie|authorization|session|"
    r"bearer|jwt|hash|salt|private|otp|mfa|recovery)",
    re.IGNORECASE,
)

# Best-effort redaction in free-form strings (e.g. exception args)
_SENSITIVE_VALUE_PATTERNS = [
    (re.compile(r"(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"), "<jwt>"),
    (re.compile(r"(Bearer\s+\S+)", re.IGNORECASE), "Bearer <token>"),
    (re.compile(r"\$2[ayb]\$\d{2}\$[A-Za-z0-9./]{53}"), "<bcrypt>"),
]


def redact(value: Any) -> Any:
    """Recursively redact sensitive content from an arbitrary value."""
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if _SENSITIVE_KEY_PATTERN.search(str(k)) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        out = value
        for pattern, repl in _SENSITIVE_VALUE_PATTERNS:
            out = pattern.sub(repl, out)
        return out
    return value


# --- JSON formatter ---------------------------------------------------------

class JsonFormatter(logging.Formatter):
    """Emit a single-line JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts":      datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
            "env":     settings.ENVIRONMENT,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Pull through any structured extra fields
        for key, value in record.__dict__.items():
            if key in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "taskName",
            }:
                continue
            payload[key] = redact(value)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging() -> None:
    """Configure root logger from settings."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Tame noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
