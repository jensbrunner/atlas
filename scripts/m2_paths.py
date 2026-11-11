#!/usr/bin/env python3
"""M2 demo: play three divergent Broken Span paths offline.

Each path runs on its own campaign with the deterministic parser, adjudicator,
and fake narrator. A scripted seed provider makes challenges reproducible, so
every campaign can be replayed exactly from its event ledger. No model, network,
key, or cloud account is involved.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from atlas.game.turn_service import TurnService
from atlas.persistence.db import create_db_engine, create_session_factory
from atlas.persistence.migrations import upgrade_database
from atlas.persistence.repositories import (
    campaign_model,
    get_campaign,
    load_projection,
    verify_replay,
)
from atlas.seed.broken_span import seed_broken_span

PATHS: dict[str, dict[str, Any]] = {
    "negotiation": {
        "template": "town_advocate",
        "seeds": [2, 4],
        "actions": [
            "negotiate with Brannoc",
            "negotiate with Magistrate Elin",
        ],
    },
    "engineering": {
        "template": "river_fixer",
        "seeds": [0, 0, 9, 2013, 2014, 0, 3002, 3004, 0, 9],
        "actions": [
            "talk to Durn",
            "go to the quarry",
            "search the quarry",
            "gather replacement stones",
            "gather replacement stones",
            "go to the workshop",
            "gather timber",
            "gather iron fittings",
            "go to the flood gate",
            "repair the flood gate",
        ],
    },
    "confrontation": {
        "template": "stone_warden",
        "seeds": [1007],
        "actions": ["confront Brannoc"],
    },
}


class SeedSequence:
    def __init__(self, seeds: list[int]) -> None:
        self._seeds = [value.to_bytes(32, "big") for value in seeds]
        self._index = 0

    def __call__(self) -> bytes:
        if self._index >= len(self._seeds):
            raise RuntimeError("scripted path used more turns than seeds")
        seed = self._seeds[self._index]
        self._index += 1
        return seed


def _client_id(campaign_id: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"atlas-m2-demo:{campaign_id}:{index}"))


def _reset(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def run(database: Path, *, reset: bool) -> dict[str, Any]:
    if reset:
        _reset(database)
    database_url = f"sqlite:///{database}"
    upgrade_database(database_url)
    engine = create_db_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        results: dict[str, Any] = {}
        for name, path in PATHS.items():
            with session_factory() as session:
                seeded = seed_broken_span(session, template_slug=path["template"])
                session.commit()
                campaign_id = seeded.campaign.id

            service = TurnService(
                session_factory,
                seed_provider=SeedSequence(list(path["seeds"])),
            )
            turns = []
            for index, action in enumerate(path["actions"]):
                result = service.submit_text(
                    campaign_id,
                    client_action_id=_client_id(campaign_id, index),
                    player_text=action,
                )
                turns.append(
                    {
                        "ordinal": result.ordinal,
                        "player_text": action,
                        "status": result.status.value,
                        "narration": result.narration,
                    }
                )

            with session_factory() as session:
                campaign = campaign_model(get_campaign(session, campaign_id))
                projection = load_projection(session, campaign_id)
                report = verify_replay(session, campaign_id)
                results[name] = {
                    "campaign_id": campaign_id,
                    "template": path["template"],
                    "turns": turns,
                    "status": campaign.status.value,
                    "ending": campaign.ending,
                    "final_version": campaign.state_version,
                    "world_minutes": campaign.current_time,
                    "observations": len(projection.observations),
                    "replay": {"matched": report.matched, "event_seq": report.event_seq},
                }
        return results
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/m2_demo.db"),
        help="SQLite database path (default: data/m2_demo.db)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the demo database before running",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args(argv)

    results = run(args.db, reset=args.reset)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0

    for name, result in results.items():
        print(f"== {name} ({result['template']}) ==")
        for turn in result["turns"]:
            print(f"  {turn['ordinal']:>3}. {turn['player_text']:<28} {turn['narration']}")
        ending = result["ending"] or {}
        print(
            f"  status: {result['status']} | ending: {ending.get('outcome', 'none')} | "
            f"version: {result['final_version']} | world minutes: {result['world_minutes']}"
        )
        print(
            f"  replay: {'matched' if result['replay']['matched'] else 'MISMATCH'} "
            f"at event {result['replay']['event_seq']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
