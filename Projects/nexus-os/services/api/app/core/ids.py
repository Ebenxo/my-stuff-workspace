"""Prefixed, time-sortable identifiers (ULID-style, Crockford base32, lower case)."""

from __future__ import annotations

import os
import threading
import time

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
_lock = threading.Lock()
_last_ms = -1
_last_rand = 0


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    """Return ``<prefix>_<26 char ulid>``. IDs sort by creation time and are monotonic per process."""
    global _last_ms, _last_rand
    with _lock:
        now_ms = time.time_ns() // 1_000_000
        if now_ms <= _last_ms:
            now_ms = _last_ms
            _last_rand += 1
            if _last_rand >= 1 << 80:  # pragma: no cover - astronomically unlikely
                now_ms += 1
                _last_rand = int.from_bytes(os.urandom(10), "big")
        else:
            _last_rand = int.from_bytes(os.urandom(10), "big")
        _last_ms = now_ms
        rand = _last_rand
    return f"{prefix}_{_encode(now_ms, 10)}{_encode(rand, 16)}"


def id_prefix(value: str) -> str:
    """Return the prefix of an id produced by :func:`new_id`."""
    return value.split("_", 1)[0]
