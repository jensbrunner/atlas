from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _run_demo(database: Path, *, reset: bool, turns: int = 12) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "m1_demo.py"),
        "--db",
        str(database),
        "--json",
        "--turns",
        str(turns),
    ]
    if reset:
        command.append("--reset")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_m1_text_demo_replays_and_is_idempotent_across_restarts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "m1_demo.db"
    first = _run_demo(database, reset=True)

    assert first["campaign_seeded"] is True
    assert first["turns_requested"] == 12
    assert [turn["ordinal"] for turn in first["turns"]] == list(range(1, 13))
    assert first["final_version"] == 12
    assert first["observations"] == 12
    assert first["replay"]["matched"] is True
    assert first["idempotent_replay"] is True
    assert first["turns"][0]["player_text"] == "look around"
    assert first["turns"][1]["player_text"] == "go to north quarry"
    assert "North Quarry" in first["turns"][1]["narration"]
    assert first["player_state"]["actor"] == "rowan"

    second = _run_demo(database, reset=False)
    assert second["campaign_seeded"] is False
    assert second["final_version"] == first["final_version"]
    assert second["world_minutes"] == first["world_minutes"]
    assert second["state_hash"] == first["state_hash"]
    assert second["replay"]["matched"] is True
    assert second["idempotent_replay"] is True
    assert [turn["turn_id"] for turn in second["turns"]] == [
        turn["turn_id"] for turn in first["turns"]
    ]
    assert [turn["narration"] for turn in second["turns"]] == [
        turn["narration"] for turn in first["turns"]
    ]
