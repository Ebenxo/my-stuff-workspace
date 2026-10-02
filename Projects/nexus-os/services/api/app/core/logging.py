"""Logging with automatic secret redaction."""

from __future__ import annotations

import logging

from app.core.security import redact_text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not any(getattr(h, "_nexus", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler._nexus = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        handler.addFilter(RedactingFilter())
        root.addHandler(handler)
    # Third-party access logs can contain URLs with credentials; keep them at WARNING.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
