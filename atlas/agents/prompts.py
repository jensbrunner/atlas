from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"missing prompt template: {path}")
    return path.read_text(encoding="utf-8")
