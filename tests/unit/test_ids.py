from __future__ import annotations

import pytest
from atlas.domain.ids import is_valid_id, new_id, new_ulid


def test_new_ulid_shape_and_sortability() -> None:
    earlier = new_ulid(timestamp_ms=1_700_000_000_000, random_bytes=b"\x00" * 10)
    later = new_ulid(timestamp_ms=1_700_000_001_000, random_bytes=b"\x00" * 10)
    assert len(earlier) == 26
    assert earlier < later


def test_prefixed_ids_are_valid_and_unique() -> None:
    values = {new_id("cmp") for _ in range(2_000)}
    assert len(values) == 2_000
    assert all(is_valid_id(value, prefix="cmp") for value in values)
    assert all(not is_valid_id(value, prefix="evt") for value in values)


def test_invalid_ulid_inputs_rejected() -> None:
    with pytest.raises(ValueError):
        new_ulid(timestamp_ms=-1)
    with pytest.raises(ValueError):
        new_ulid(random_bytes=b"too-short")
    with pytest.raises(ValueError):
        new_id("Bad Prefix")
