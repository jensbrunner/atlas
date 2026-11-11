from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _run_script(database: Path, *, reset: bool) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "offline_turn.py"),
        "--db",
        str(database),
        "--json",
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


def test_offline_turn_is_reproducible_across_restarts(tmp_path: Path) -> None:
    database = tmp_path / "m0_e2e.db"
    first = _run_script(database, reset=True)

    assert first["campaign_version"] == 1
    assert first["replay"]["matched"] is True
    assert first["restart_persistence"] is True
    assert first["idempotent_replay"] is True
    assert first["player_state"]["location"] == "North Quarry"
    assert first["player_state"]["supplies"] == 1
    assert first["player_state"]["world_minutes"] == 240
    assert first["checkpoint"]["event_seq"] == first["replay"]["event_seq"]

    second = _run_script(database, reset=False)
    assert second["turn_id"] == first["turn_id"]
    assert second["campaign_version"] == 1
    assert second["replay"]["state_hash"] == first["replay"]["state_hash"]
    assert second["restart_persistence"] is True
    assert second["idempotent_replay"] is True
    assert second["campaign_seeded"] is False
