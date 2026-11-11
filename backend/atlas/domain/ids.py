"""Stable, prefixed identifiers (ULID-based).

Names are never primary keys. IDs are lexicographically sortable by creation
time and carry an explicit type prefix for logs and audits.
"""

from __future__ import annotations

import re
import secrets
import time
from typing import Final

_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_RE: Final = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_PREFIX_RE: Final = re.compile(r"^[a-z][a-z0-9]{1,15}$")

MAX_ULID_TIMESTAMP_MS: Final = (1 << 48) - 1


def new_ulid(*, timestamp_ms: int | None = None, random_bytes: bytes | None = None) -> str:
    """Return a 26-character ULID.

    ``timestamp_ms`` and ``random_bytes`` are injectable for deterministic
    tests; production callers should use the defaults.
    """
    ms = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    if not 0 <= ms <= MAX_ULID_TIMESTAMP_MS:
        raise ValueError("timestamp_ms is outside the 48-bit ULID range")

    entropy = secrets.token_bytes(10) if random_bytes is None else random_bytes
    if len(entropy) != 10:
        raise ValueError("random_bytes must be exactly 10 bytes")

    value = (ms << 80) | int.from_bytes(entropy, "big")
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def new_id(prefix: str, *, timestamp_ms: int | None = None) -> str:
    """Create an ID such as ``cmp_01J...``."""
    if not _PREFIX_RE.fullmatch(prefix):
        raise ValueError(f"invalid ID prefix: {prefix!r}")
    return f"{prefix}_{new_ulid(timestamp_ms=timestamp_ms)}"


def is_valid_id(value: str, *, prefix: str | None = None) -> bool:
    if prefix is not None:
        marker = f"{prefix}_"
        if not value.startswith(marker):
            return False
        value = value[len(marker) :]
    return bool(_ULID_RE.fullmatch(value))
