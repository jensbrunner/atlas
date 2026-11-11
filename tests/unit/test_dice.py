from __future__ import annotations

import pytest
from atlas.domain.dice import RNG_ALGORITHM, SeededRandom, resolve_roll
from atlas.domain.rules import (
    ResolutionBand,
    RollRequest,
    RollResult,
    band_for_total,
    total_from,
)
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError


def test_fixed_seed_sequences_are_stable() -> None:
    seed = bytes.fromhex("00" * 32)
    dice_rng = SeededRandom(seed)
    assert [dice_rng.roll_die(6) for _ in range(12)] == [5, 1, 6, 3, 2, 4, 4, 3, 4, 6, 4, 3]

    below_rng = SeededRandom(seed)
    assert [below_rng.randbelow(1_000) for _ in range(8)] == [
        354,
        380,
        667,
        314,
        621,
        749,
        317,
        42,
    ]


def test_same_seed_and_request_reproduce_exactly() -> None:
    seed = bytes.fromhex("ab" * 32)
    request = RollRequest(label="climb", modifier=2, difficulty=1)
    first = resolve_roll(request, seed)
    second = resolve_roll(request, seed)
    assert first == second
    assert first.rng_algorithm == RNG_ALGORITHM
    assert first.seed_ref == seed.hex()


def test_resolution_bands_and_total() -> None:
    request = RollRequest(label="test", modifier=3, difficulty=2)
    result = resolve_roll(request, bytes.fromhex("00" * 32))
    assert result.dice == [5, 1]
    assert result.total == total_from((5, 1), 3, 2) == 7
    assert result.outcome is ResolutionBand.MIXED_SUCCESS


@pytest.mark.parametrize(
    ("total", "band"),
    [
        (2, ResolutionBand.FAILURE),
        (6, ResolutionBand.FAILURE),
        (7, ResolutionBand.MIXED_SUCCESS),
        (9, ResolutionBand.MIXED_SUCCESS),
        (10, ResolutionBand.SUCCESS),
        (12, ResolutionBand.SUCCESS),
    ],
)
def test_band_boundaries(total: int, band: ResolutionBand) -> None:
    assert band_for_total(total) is band


def test_roll_result_rejects_inconsistent_arithmetic() -> None:
    with pytest.raises(ValidationError):
        RollResult(
            label="bad",
            dice=[1, 1],
            modifier=5,
            difficulty=0,
            total=99,
            outcome=ResolutionBand.SUCCESS,
            rng_algorithm=RNG_ALGORITHM,
            seed_ref="00",
        )


def test_roll_request_rejects_out_of_design_bounds() -> None:
    with pytest.raises(ValidationError):
        RollRequest(label="too strong", modifier=5)
    with pytest.raises(ValidationError):
        RollRequest(label="too hard", difficulty=4)


def test_distribution_is_sane_over_many_rolls() -> None:
    rng = SeededRandom(bytes.fromhex("11" * 32))
    counts = {face: 0 for face in range(1, 7)}
    for _ in range(60_000):
        counts[rng.roll_die(6)] += 1
    assert all(9_000 <= count <= 11_000 for count in counts.values()), counts


@given(st.binary(min_size=16, max_size=64))
def test_seeded_sequences_are_deterministic(seed: bytes) -> None:
    first = SeededRandom(seed)
    second = SeededRandom(seed)
    assert [first.randbelow(1_000) for _ in range(20)] == [
        second.randbelow(1_000) for _ in range(20)
    ]


@given(st.integers(min_value=1, max_value=1_000_000))
def test_randbelow_stays_in_range(n: int) -> None:
    value = SeededRandom(bytes.fromhex("22" * 32)).randbelow(n)
    assert 0 <= value < n


@given(
    st.binary(min_size=16, max_size=32),
    st.integers(min_value=-1, max_value=4),
    st.integers(min_value=0, max_value=3),
)
def test_resolved_total_and_band_always_consistent(
    seed: bytes, modifier: int, difficulty: int
) -> None:
    request = RollRequest(label="property", modifier=modifier, difficulty=difficulty)
    result = resolve_roll(request, seed)
    assert result.total == sum(result.dice) + modifier - difficulty
    assert result.outcome is band_for_total(result.total)
