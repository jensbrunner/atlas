from __future__ import annotations

import pytest

from atlas.state.markdown import (
    build_document,
    extract_gm_block_text,
    gm_block,
    parse_document,
    strip_gm_blocks,
)


def test_frontmatter_round_trip() -> None:
    document = build_document({"id": "cmp_1", "turn_count": 3}, "A short body.")
    frontmatter, body = parse_document(document)
    assert frontmatter == {"id": "cmp_1", "turn_count": 3}
    assert body.strip() == "A short body."


def test_document_without_frontmatter_is_body() -> None:
    frontmatter, body = parse_document("# plain markdown")
    assert frontmatter == {}
    assert body == "# plain markdown"


def test_gm_blocks_are_stripped_from_player_text() -> None:
    text = "Visible.\n\n" + gm_block("Hidden truth.") + "\n\nAlso visible."
    stripped = strip_gm_blocks(text)
    assert "Hidden truth" not in stripped
    assert "Visible." in stripped
    assert "Also visible." in stripped


def test_gm_block_is_extractable_for_gm_view() -> None:
    text = "Visible.\n\n" + gm_block("Only the GM sees this.")
    extracted = extract_gm_block_text(text)
    assert "Only the GM sees this." in extracted


def test_invalid_frontmatter_raises() -> None:
    with pytest.raises(ValueError):
        parse_document("---\n- a list\n---\nbody")
