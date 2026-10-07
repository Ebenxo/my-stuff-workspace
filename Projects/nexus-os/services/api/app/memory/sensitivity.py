"""SensitivityGuard: things that must never be remembered.

A memory outlives the run that wrote it and is shown to future agents, so credentials and personal
identifiers are refused outright rather than redacted: a half-redacted secret is still a leak, and
the person can always write the non-sensitive part themselves. Only the *category* is ever reported;
the matched text never leaves this module.
"""

from __future__ import annotations

import re

from app.core.security import find_secrets

_SECRET_CATEGORY = {
    "private_key": "private key",
    "anthropic_key": "API key",
    "openai_key": "API key",
    "google_api_key": "API key",
    "github_token": "access token",
    "slack_token": "access token",
    "aws_access_key": "cloud credential",
    "jwt": "access token",
    "bearer_token": "access token",
    "credential_assignment": "password or secret",
}

_CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
_US_SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_UK_NINO = re.compile(
    r"\b(?![DFIQUV])[A-CEGHJ-PR-TW-Z](?![DFIQUVO])[A-CEGHJ-NPR-TW-Z] ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b"
)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
_CLOUD = re.compile(
    r"(?i)\b(?:AccountKey|SharedAccessKey|aws_secret_access_key)\s*[=:]\s*[A-Za-z0-9+/=]{20,}"
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _iban_ok(candidate: str) -> bool:
    s = candidate.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    moved = s[4:] + s[:4]
    number = "".join(str(int(c, 36)) for c in moved)
    return int(number) % 97 == 1


def scan(text: str) -> list[str]:
    """Categories of sensitive data found in ``text`` (empty when it is safe to remember)."""
    found: list[str] = []

    def add(category: str) -> None:
        if category not in found:
            found.append(category)

    for m in find_secrets(text):
        add(_SECRET_CATEGORY.get(m.kind, "secret"))
    if _CLOUD.search(text):
        add("cloud credential")
    for card in _CARD.finditer(text):
        digits = re.sub(r"\D", "", card.group(0))
        # Major networks start with 2-6; a run of one digit (all zeros) passes Luhn but is a placeholder.
        if 13 <= len(digits) <= 19 and digits[0] in "23456" and len(set(digits)) > 1 and _luhn_ok(digits):
            add("payment card number")
            break
    if _US_SSN.search(text) or _UK_NINO.search(text):
        add("national identity number")
    if any(_iban_ok(hit.group(0)) for hit in _IBAN.finditer(text)):
        add("bank account number")
    return found


def explain(categories: list[str]) -> str:
    joined = ", ".join(categories)
    return (
        f"Not remembered: it looks like it contains sensitive data ({joined}). "
        "Memories are kept and shown to future agents, so credentials and personal identifiers are never stored. "
        "Remember the non-sensitive part instead."
    )
