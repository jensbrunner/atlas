"""Deterministic, auditable randomness.

Algorithm (versioned as ``hmac-sha256-ctr-v1``):

1. A fresh 32-byte seed is generated with the OS CSPRNG per turn.
2. Block *i* is ``HMAC-SHA256(seed, uint64_be(i))``.
3. Each 32-bit chunk is accepted only below ``floor(2**32 / n) * n`` (rejection
   sampling), so ``randbelow(n)`` is unbiased.

The seed is stored with the turn so a committed result can be reproduced, but it
must not be exposed in player-facing endpoints before an explicit reveal.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
from typing import Final

from atlas.domain.rules import RollRequest, RollResult, band_for_total

RNG_ALGORITHM: Final = "hmac-sha256-ctr-v1"
SEED_BYTES: Final = 32
_UINT32_SPACE: Final = 1 << 32


class SeededRandom:
    """Versioned reproducible RNG used for every mechanical roll."""

    def __init__(self, seed: bytes, *, algorithm: str = RNG_ALGORITHM) -> None:
        if algorithm != RNG_ALGORITHM:
            raise ValueError(f"unsupported RNG algorithm: {algorithm!r}")
        if len(seed) < 16:
            raise ValueError("seed must contain at least 16 bytes")
        self._seed = seed
        self._counter = 0
        self._chunks: list[int] = []
        self.algorithm = algorithm

    def _next_uint32(self) -> int:
        if not self._chunks:
            digest = hmac.new(self._seed, struct.pack(">Q", self._counter), hashlib.sha256).digest()
            self._counter += 1
            self._chunks = list(struct.unpack(">8I", digest))
        return self._chunks.pop(0)

    def randbelow(self, n: int) -> int:
        if n <= 0:
            raise ValueError("n must be positive")
        if n > _UINT32_SPACE:
            raise ValueError("n must fit in 32 bits")
        limit = (_UINT32_SPACE // n) * n
        while True:
            value = self._next_uint32()
            if value < limit:
                return value % n

    def roll_die(self, sides: int = 6) -> int:
        if sides < 2:
            raise ValueError("a die needs at least two sides")
        return 1 + self.randbelow(sides)

    def roll_2d6(self) -> tuple[int, int]:
        return self.roll_die(6), self.roll_die(6)


def generate_seed() -> bytes:
    return secrets.token_bytes(SEED_BYTES)


def resolve_roll(request: RollRequest, seed: bytes) -> RollResult:
    rng = SeededRandom(seed)
    dice = rng.roll_2d6()
    total = dice[0] + dice[1] + request.modifier - request.difficulty
    return RollResult(
        label=request.label,
        dice=[dice[0], dice[1]],
        modifier=request.modifier,
        difficulty=request.difficulty,
        total=total,
        outcome=band_for_total(total),
        rng_algorithm=rng.algorithm,
        seed_ref=seed.hex(),
    )
