#!/usr/bin/env python3
"""M1 demo: deterministic multi-turn text play, no model or network.

The script uses the real lifecycle-aware turn service with the deterministic
parser, adjudicator, and fake narrator. It is safe to re-run: each request has a
stable client action id, so duplicate turns are returned from storage instead of
being applied again.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from atlas.domain.projection import hash_projection, player_scene_view
from atlas.game.turn_service import TurnService
from atlas.persistence.db import create_db_engine, create_session_factory
from atlas.persistence.migrations import upgrade_database
from atlas.persistence.orm import CampaignRow
from atlas.persistence.repositories import (
    get_campaign,
    load_projection,
    verify_replay,
)
from atlas.seed.broken_span import seed_broken_span
from sqlalchemy import select

SCRIPT = [
    "look around",
    "go to north quarry",
    "search the quarry",
    "wait 15 minutes",
    "go to market square",
    "talk to the magistrate",
    "look around",
    "wait 1 hour",
]


def _client_id(campaign_id: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"atlas-m1-demo:{campaign_id}:{index}"))


def _reset(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def run(database: Path, *, reset: bool, turn_count: int) -> dict[str, Any]:
    if reset:
        _reset(database)
    database_url = f"sqlite:///{database}"
    upgrade_database(database_url)
    engine = create_db_engine(database_url)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            campaign = session.scalar(select(CampaignRow).limit(1))
            if campaign is None:
                seeded = seed_broken_span(session)
                session.commit()
                campaign_id = seeded.campaign.id
                campaign_seeded = True
            else:
                campaign_id = campaign.id
                campaign_seeded = False

        service = TurnService(session_factory)
        turns: list[dict[str, Any]] = []
        for index in range(turn_count):
            text = SCRIPT[index % len(SCRIPT)]
            client_id = _client_id(campaign_id, index)
            result = service.submit_text(
                campaign_id,
                client_action_id=client_id,
                player_text=text,
            )
            turns.append(
                {
                    "ordinal": result.ordinal,
                    "turn_id": result.turn_id,
                    "player_text": text,
                    "status": result.status.value,
                    "campaign_version": result.campaign_version,
                    "narration": result.narration,
                }
            )

        with session_factory() as session:
            seeded_campaign = get_campaign(session, campaign_id)
            projection = load_projection(session, campaign_id)
            report = verify_replay(session, campaign_id)
            scene = player_scene_view(projection)
            observations = len(projection.observations)
            state_hash = hash_projection(projection)
            final_version = seeded_campaign.state_version
            world_minutes = seeded_campaign.current_time
            replay_matched = report.matched
            replay_event_seq = report.event_seq

        # A second identical request batch must return stored turns, not apply
        # any effects twice. This is the explicit duplicate-request check.
        repeated = service.submit_text(
            campaign_id,
            client_action_id=_client_id(campaign_id, 0),
            player_text=SCRIPT[0],
        )
        with session_factory() as session:
            after_version = get_campaign(session, campaign_id).state_version
        idempotent = repeated.turn_id == turns[0]["turn_id"] and after_version == final_version

        return {
            "campaign_id": campaign_id,
            "campaign_seeded": campaign_seeded,
            "turns_requested": turn_count,
            "turns": turns,
            "final_version": final_version,
            "world_minutes": world_minutes,
            "observations": observations,
            "state_hash": state_hash,
            "replay": {
                "matched": replay_matched,
                "event_seq": replay_event_seq,
            },
            "idempotent_replay": idempotent,
            "player_state": {
                "actor": scene.get("actor", {}).get("slug"),
                "location": (scene.get("location") or {}).get("slug"),
            },
        }
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/m1_demo.db"),
        help="SQLite database path (default: data/m1_demo.db)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the demo database before running",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=12,
        help="number of text turns to play (default: 12)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args(argv)

    result = run(args.db, reset=args.reset, turn_count=args.turns)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print(f"campaign: {result['campaign_id']} (new seed: {result['campaign_seeded']})")
    for turn in result["turns"]:
        print(
            f"{turn['ordinal']:>3}. {turn['player_text']:<24} "
            f"v{turn['campaign_version']:<3} {turn['narration']}"
        )
    print(
        f"final version: {result['final_version']} | "
        f"world minutes: {result['world_minutes']} | "
        f"observations: {result['observations']}"
    )
    print(
        f"replay: {'matched' if result['replay']['matched'] else 'MISMATCH'} "
        f"at event {result['replay']['event_seq']} | "
        f"duplicate request idempotent: {result['idempotent_replay']}"
    )
    print(f"state hash: {result['state_hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
