#!/usr/bin/env python3
"""Reproducible M0 offline demonstration.

Runs migrations, seeds The Broken Span, commits one deterministic action,
verifies event replay, reopens the database, and checks idempotent replay.
No network or model API is used.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atlas.domain.commands import (
    AdjustResourceCommand,
    AdvanceTimeCommand,
    MoveEntityCommand,
)
from atlas.domain.models import EntityKind, ResourceName
from atlas.domain.rules import RollRequest
from atlas.game.turn_service import OfflineTurnService, ScriptedTurnPlan
from atlas.persistence.db import create_db_engine, create_session_factory
from atlas.persistence.migrations import upgrade_database
from atlas.persistence.repositories import (
    create_checkpoint,
    get_campaign,
    list_campaigns,
    load_projection,
    verify_replay,
)
from atlas.seed.broken_span import seed_broken_span
from sqlalchemy.orm import Session, sessionmaker

DEMO_CLIENT_ID = "8f1f5f8e-43e0-4f7e-9f5b-0e7d5b3a7a10"
DEMO_PLAYER_TEXT = "I head to the quarry and search for usable replacement stone."


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"


def _reset_database(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{path}{suffix}")
        if candidate.exists():
            candidate.unlink()


def _find_campaign_id(session_factory: sessionmaker[Session]) -> tuple[str, bool]:
    with session_factory() as session:
        campaigns = list_campaigns(session)
        if campaigns:
            return campaigns[0].id, False
    with session_factory() as session:
        seeded = seed_broken_span(session)
        session.commit()
        return seeded.campaign.id, True


def _build_plan(session_factory: sessionmaker[Session], campaign_id: str) -> ScriptedTurnPlan:
    with session_factory() as session:
        projection = load_projection(session, campaign_id)
    pc = projection.entity_by_slug("rowan")
    quarry = projection.entity_by_slug("quarry")
    if pc is None or quarry is None:
        raise SystemExit("seed is missing Rowan or the quarry")
    if pc.kind is not EntityKind.PLAYER_CHARACTER:
        raise SystemExit("seed Rowan is not a player character")
    if quarry.kind is not EntityKind.LOCATION:
        raise SystemExit("seed quarry is not a location")

    attributes = pc.static.get("attributes", {})
    training = pc.static.get("training", {})
    modifier = int(attributes.get("insight", 0)) + int(training.get("insight", 0))
    return ScriptedTurnPlan(
        commands=(
            MoveEntityCommand(
                entity_id=pc.id,
                to_location_id=quarry.id,
                reason="travel to the quarry",
            ),
            AdjustResourceCommand(
                entity_id=pc.id,
                resource=ResourceName.SUPPLIES,
                delta=-1,
                reason="rations for a half-day search",
            ),
            AdvanceTimeCommand(minutes=240, reason="travel and quarry search"),
        ),
        roll_request=RollRequest(
            label="search the quarry for replacement stone",
            modifier=modifier,
            difficulty=2,
        ),
        narration_template=(
            "Rowan reaches the quarry and searches the scree for replacement stone. "
            "Outcome: {outcome} ({total} against difficulty {difficulty}); "
            "the search consumes {elapsed_minutes} world minutes."
        ),
    )


def run(database_path: Path, *, reset: bool) -> dict[str, object]:
    if reset:
        _reset_database(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    url = _database_url(database_path)
    upgrade_database(url)

    engine = create_db_engine(url)
    factory = create_session_factory(engine)
    campaign_id, created = _find_campaign_id(factory)
    plan = _build_plan(factory, campaign_id)
    service = OfflineTurnService(factory)

    with factory() as session:
        campaign = get_campaign(session, campaign_id)
        expected_version = campaign.state_version

    result = service.submit(
        campaign_id,
        client_action_id=DEMO_CLIENT_ID,
        player_text=DEMO_PLAYER_TEXT,
        plan=plan,
        expected_version=expected_version,
    )

    with factory() as session:
        projection = load_projection(session, campaign_id)
        report = verify_replay(session, campaign_id)
        if not report.matched:
            raise SystemExit(
                f"replay mismatch: live={report.live_hash} replay={report.replay_hash}"
            )
        checkpoint = create_checkpoint(session, campaign_id)
        checkpoint_hash = checkpoint.state_hash
        checkpoint_seq = checkpoint.event_seq
        session.commit()

        pc = projection.entity_by_slug("rowan")
        location = (
            projection.entities.get(pc.state.get("location_id", "")) if pc is not None else None
        )
        player_view = {
            "entity_id": pc.id if pc else None,
            "name": pc.display_name if pc else None,
            "location": location.display_name if location else None,
            "supplies": pc.state.get("supplies") if pc else None,
            "health": pc.state.get("health") if pc else None,
            "world_minutes": projection.current_time,
            "state_version": projection.state_version,
        }
        live_hash = report.live_hash
        event_seq = report.event_seq

    engine.dispose()

    # Reopen from disk and prove the committed state and idempotency survive.
    reopened_engine = create_db_engine(url)
    reopened_factory = create_session_factory(reopened_engine)
    reopened_service = OfflineTurnService(reopened_factory)
    repeated = reopened_service.submit(
        campaign_id,
        client_action_id=DEMO_CLIENT_ID,
        player_text=DEMO_PLAYER_TEXT,
        plan=plan,
    )
    with reopened_factory() as session:
        replay_after_restart = verify_replay(session, campaign_id)
        campaign_after = get_campaign(session, campaign_id)
        if not replay_after_restart.matched:
            raise SystemExit("replay mismatch after restart")
        restart_state = {
            "state_version": campaign_after.state_version,
            "current_time": campaign_after.current_time,
            "replay_hash": replay_after_restart.live_hash,
        }
    reopened_engine.dispose()

    idempotent = (
        repeated.turn_id == result.turn_id
        and repeated.campaign_version == result.campaign_version
        and repeated.narration == result.narration
    )
    if not idempotent:
        raise SystemExit("duplicate client action was not returned idempotently")

    return {
        "database": str(database_path),
        "campaign_id": campaign_id,
        "campaign_seeded": created,
        "turn_id": result.turn_id,
        "campaign_version": result.campaign_version,
        "narration": result.narration,
        "mechanics": result.mechanics,
        "player_state": player_view,
        "replay": {
            "matched": report.matched,
            "state_hash": live_hash,
            "event_seq": event_seq,
        },
        "checkpoint": {
            "event_seq": checkpoint_seq,
            "state_hash": checkpoint_hash,
        },
        "restart": restart_state,
        "restart_persistence": True,
        "idempotent_replay": idempotent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/m0_demo.db"))
    parser.add_argument("--reset", action="store_true", help="delete the demo database first")
    parser.add_argument("--json", action="store_true", help="print the full JSON summary")
    args = parser.parse_args()

    summary = run(args.db, reset=args.reset)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"database: {summary['database']}")
        print(f"campaign: {summary['campaign_id']} (seeded={summary['campaign_seeded']})")
        print(f"turn: {summary['turn_id']}  version: {summary['campaign_version']}")
        print(f"narration: {summary['narration']}")
        print(f"mechanics: {json.dumps(summary['mechanics'], sort_keys=True)}")
        print(f"player: {json.dumps(summary['player_state'], sort_keys=True)}")
        print(f"replay: {json.dumps(summary['replay'], sort_keys=True)}")
        print(f"checkpoint: {json.dumps(summary['checkpoint'], sort_keys=True)}")
        print(f"restart: {json.dumps(summary['restart'], sort_keys=True)}")
        print(f"restart_persistence: {summary['restart_persistence']}")
        print(f"idempotent_replay: {summary['idempotent_replay']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
