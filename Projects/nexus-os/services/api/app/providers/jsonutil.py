"""Extract and describe JSON produced by models."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

_FENCE = re.compile(r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in ``text`` (tolerates code fences and leading prose)."""
    stripped = text.strip()
    fenced = _FENCE.match(stripped)
    if fenced:
        stripped = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for start, ch in enumerate(stripped):
        if ch in "{[":
            try:
                value, _ = decoder.raw_decode(stripped[start:])
                return value
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON object found in the reply")


def describe_validation_error(exc: Exception, limit: int = 800) -> str:
    """A short, input-free description of why parsing/validation failed (safe to send back)."""
    if isinstance(exc, ValidationError):
        parts = [
            f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False, include_context=False)
        ]
        text = "; ".join(parts)
    else:
        text = str(exc)
    return text[:limit]
