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
        str(ROOT / "scripts" / "m2_paths.py"),
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


def test_m2_paths_reach_distinct_endings_and_replay_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "m2_e2e.db"
    first = _run_script(database, reset=True)

    assert set(first) == {"negotiation", "engineering", "confrontation"}
    endings = {
        name: result["ending"]["outcome"]
        for name, result in first.items()
        if result["ending"] is not None
    }
    assert endings == {
        "negotiation": "compromise_shared_guardianship",
        "engineering": "flood_gate_repaired",
        "confrontation": "giant_driven_off",
    }
    for result in first.values():
        assert result["status"] == "completed"
        assert result["replay"]["matched"] is True
        assert result["replay"]["event_seq"] > 0

    # A second run uses fresh campaigns in the same database; each replays too.
    second = _run_script(database, reset=False)
    for name, result in second.items():
        assert result["status"] == "completed"
        assert result["replay"]["matched"] is True
        assert result["ending"]["outcome"] == endings[name]
        assert result["campaign_id"] != first[name]["campaign_id"]
