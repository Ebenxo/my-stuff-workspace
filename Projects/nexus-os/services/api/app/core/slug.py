"""Slug helpers shared by stores (kept dependency-free to avoid import cycles)."""

from __future__ import annotations

import re
import unicodedata


def slugify_agent(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if not text or not text[0].isalpha():
        text = f"agent-{text}" if text else "agent"
    return text[:40]
