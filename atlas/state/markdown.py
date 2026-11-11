from __future__ import annotations

import re
from typing import Any

import yaml

_FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_GM_BLOCK = re.compile(r"<!--\s*gm\s*-->.*?<!--\s*/gm\s*-->", re.DOTALL | re.IGNORECASE)
_GM_OPEN = "<!-- gm -->"
_GM_CLOSE = "<!-- /gm -->"


def parse_document(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown document into YAML frontmatter and body."""

    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    raw = yaml.safe_load(match.group(1)) or {}
    if not isinstance(raw, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return raw, text[match.end() :]


def build_document(frontmatter: dict[str, Any], body: str) -> str:
    header = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    body = body.strip()
    if body:
        return f"---\n{header}\n---\n\n{body}\n"
    return f"---\n{header}\n---\n"


def strip_gm_blocks(text: str) -> str:
    """Remove GM-only prose blocks from a player-facing document."""

    cleaned = _GM_BLOCK.sub("", text)
    # Collapse whitespace left by removed blocks without destroying paragraphs.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def gm_block(text: str) -> str:
    cleaned = text.strip()
    return f"{_GM_OPEN}\n{cleaned}\n{_GM_CLOSE}"


def extract_gm_block_text(text: str) -> str:
    parts = _GM_BLOCK.findall(text)
    return "\n".join(part for part in parts)
