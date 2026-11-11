"""ATLAS Core v0.1 deterministic resolution rules."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atlas.domain.models import ResourceName, Visibility

# Provisional design bounds from VISION.md section 7.
ABILITY_MIN: Final = -1
ABILITY_MAX: Final = 2
TRAINING_MIN: Final = 0
TRAINING_MAX: Final = 2
DIFFICULTY_MIN: Final = 0
DIFFICULTY_MAX: Final = 3

DEFAULT_RESOURCE_BOUNDS: Final[dict[ResourceName, tuple[int, int]]] = {
    ResourceName.HEALTH: (0, 10),
    ResourceName.STRESS: (0, 10),
    ResourceName.SUPPLIES: (0, 99),
    ResourceName.CURRENCY: (0, 9999),
}


class ResolutionBand(StrEnum):
    FAILURE = "failure"
    MIXED_SUCCESS = "mixed_success"
    SUCCESS = "success"


class RollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    modifier: int = Field(default=0, ge=ABILITY_MIN + TRAINING_MIN, le=ABILITY_MAX + TRAINING_MAX)
    difficulty: int = Field(default=0, ge=DIFFICULTY_MIN, le=DIFFICULTY_MAX)
    visibility: Visibility = Visibility.PUBLIC


class RollResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    dice: list[int] = Field(min_length=2, max_length=2)
    modifier: int
    difficulty: int
    total: int
    outcome: ResolutionBand
    rng_algorithm: str
    seed_ref: str

    @model_validator(mode="after")
    def _consistent_total(self) -> RollResult:
        if self.total != sum(self.dice) + self.modifier - self.difficulty:
            raise ValueError("roll total does not match dice + modifier - difficulty")
        if self.outcome is not band_for_total(self.total):
            raise ValueError("roll outcome band does not match total")
        return self


def band_for_total(total: int) -> ResolutionBand:
    if total <= 6:
        return ResolutionBand.FAILURE
    if total <= 9:
        return ResolutionBand.MIXED_SUCCESS
    return ResolutionBand.SUCCESS


def total_from(dice: tuple[int, int], modifier: int, difficulty: int) -> int:
    return dice[0] + dice[1] + modifier - difficulty
