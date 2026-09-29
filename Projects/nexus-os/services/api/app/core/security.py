"""Security primitives shared across layers: secret-pattern detection, redaction, safe comparison."""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

REDACTED = "[REDACTED]"

# (kind, compiled pattern). Order matters: specific formats before generic ones.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    ),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}=*")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|"
            r"password|passwd|pwd|secret|token)\b\s*[:=]\s*[\"']?[^\s\"',;]{6,}"
        ),
    ),
]

_SENSITIVE_KEY = re.compile(
    r"(?i)^(?:.*[_\-])?(?:api[_-]?key|apikey|secret|token|password|passwd|authorization|"
    r"x-api-key|private[_-]?key|cookie|set-cookie)(?:[_\-].*)?$"
)


@dataclass(frozen=True)
class SecretMatch:
    kind: str
    start: int
    end: int


_GENERIC_KINDS = frozenset({"credential_assignment"})


def find_secrets(text: str, *, generic: bool = True) -> list[SecretMatch]:
    """Locate secret-looking substrings. Overlapping matches are merged, earliest pattern wins.

    ``generic=False`` keeps only specific key formats (used when scanning source code, where
    ``token: string`` is an identifier, not a credential).
    """
    found: list[SecretMatch] = []
    for kind, pattern in _SECRET_PATTERNS:
        if not generic and kind in _GENERIC_KINDS:
            continue
        for hit in pattern.finditer(text):
            found.append(SecretMatch(kind, hit.start(), hit.end()))
    found.sort(key=lambda m: (m.start, -(m.end - m.start)))
    merged: list[SecretMatch] = []
    for m in found:
        if merged and m.start < merged[-1].end:
            continue
        merged.append(m)
    return merged


def redact_text(text: str) -> str:
    matches = find_secrets(text)
    if not matches:
        return text
    out: list[str] = []
    pos = 0
    for m in matches:
        out.append(text[pos : m.start])
        out.append(f"{REDACTED[:-1]}:{m.kind}]")
        pos = m.end
    out.append(text[pos:])
    return "".join(out)


def redact(value: Any) -> Any:
    """Recursively redact secrets in strings, and any value stored under a sensitive-looking key."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SENSITIVE_KEY.match(key) and item not in (None, "", False):
                result[key] = REDACTED
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def mask_secret(value: str) -> str:
    """Never reveal more than the last four characters of a secret."""
    if len(value) <= 8:
        return "••••"
    return f"••••{value[-4:]}"
