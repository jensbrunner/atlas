from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.api.dependencies import SessionDep, TurnServiceDep
from atlas.api.schemas import (
    JournalResponse,
    ObservationResponse,
    RollResponse,
    StateResponse,
    TurnCreateRequest,
    TurnListResponse,
    TurnResponse,
)
from atlas.domain.models import TurnStatus
from atlas.domain.projection import (
    player_scene_view,
    public_observations,
    public_state_view,
)
from atlas.domain.rules import RollSummary
from atlas.persistence.orm import ObservationRow, RollRow, TurnRow
from atlas.persistence.repositories import (
    get_campaign,
    get_turn,
    list_turns,
    load_projection,
    observations_for_turn,
)

router = APIRouter(
    prefix="/api/v1/campaigns/{campaign_id}",
    tags=["turns"],
)


def _observation_response(row: ObservationRow) -> ObservationResponse:
    return ObservationResponse(
        event_id=row.id,
        sequence=row.seq,
        turn_id=row.turn_id,
        world_time=row.occurred_at_world,
        text=row.text,
        kind=row.kind,
        subject_ids=list(row.subject_ids_json),
        visibility=row.visibility,
    )


def _visible_turn_observations(
    session: Session, campaign_id: str, turn_id: str
) -> list[ObservationResponse]:
    projection = load_projection(session, campaign_id)
    gm_only = {entity.id for entity in projection.entities.values() if entity.static.get("gm_only")}
    responses: list[ObservationResponse] = []
    for row in observations_for_turn(session, campaign_id, turn_id):
        if row.visibility == "GM_ONLY":
            continue
        if gm_only.intersection(row.subject_ids_json):
            continue
        responses.append(_observation_response(row))
    return responses


def _public_roll(session: Session, turn_id: str) -> RollResponse | None:
    row = session.scalar(select(RollRow).where(RollRow.turn_id == turn_id))
    if row is None or row.visibility not in {"PUBLIC", "PLAYER_KNOWN"}:
        return None
    summary = RollSummary.model_validate(row.result_json)
    return RollResponse(
        label=summary.label,
        dice=list(summary.dice),
        modifier=summary.modifier,
        difficulty=summary.difficulty,
        total=summary.total,
        outcome=summary.outcome.value,
        rng_algorithm=summary.rng_algorithm,
    )


def _turn_response(session: Session, row: TurnRow) -> TurnResponse:
    return TurnResponse(
        id=row.id,
        campaign_id=row.campaign_id,
        client_action_id=row.client_action_id,
        ordinal=row.ordinal,
        player_text=row.player_text,
        status=row.status,
        snapshot_version=row.snapshot_version,
        campaign_version=(
            row.snapshot_version + 1
            if row.status == TurnStatus.COMMITTED.value
            else row.snapshot_version
        ),
        narration=row.narrator_text or "",
        mechanics=dict(row.mechanics_json),
        roll=_public_roll(session, row.id),
        observations=_visible_turn_observations(session, row.campaign_id, row.id),
        error_code=row.error_code,
        created_at=row.created_at,
        committed_at=row.committed_at,
    )


@router.post("/turns", response_model=TurnResponse)
def submit_turn(
    campaign_id: str,
    request: TurnCreateRequest,
    session: SessionDep,
    service: TurnServiceDep,
) -> TurnResponse:
    result = service.submit_text(
        campaign_id,
        client_action_id=request.client_action_id,
        player_text=request.player_text,
        expected_version=request.expected_version,
    )
    return _turn_response(session, get_turn(session, campaign_id, result.turn_id))


@router.get("/turns", response_model=TurnListResponse)
def get_turns(
    campaign_id: str,
    session: SessionDep,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TurnListResponse:
    get_campaign(session, campaign_id)
    rows = list_turns(session, campaign_id, after_ordinal=after, limit=limit)
    return TurnListResponse(
        turns=[_turn_response(session, row) for row in rows],
        next_cursor=rows[-1].ordinal if len(rows) == limit else None,
    )


@router.get("/turns/{turn_id}", response_model=TurnResponse)
def get_turn_by_id(campaign_id: str, turn_id: str, session: SessionDep) -> TurnResponse:
    return _turn_response(session, get_turn(session, campaign_id, turn_id))


@router.get("/state", response_model=StateResponse)
def get_state(campaign_id: str, session: SessionDep) -> StateResponse:
    projection = load_projection(session, campaign_id)
    public = public_state_view(projection)
    recent = public_observations(projection, limit=20)
    return StateResponse(
        campaign_id=campaign_id,
        current_time=projection.current_time,
        state_version=projection.state_version,
        scene=player_scene_view(projection),
        entities=public["entities"],
        recent_observations=[
            ObservationResponse(
                event_id=entry["event_id"],
                sequence=entry["sequence"],
                turn_id=entry["turn_id"],
                world_time=entry["world_time"],
                text=entry["text"],
                kind=entry["kind"],
                subject_ids=entry["subject_ids"],
                visibility=entry["visibility"],
            )
            for entry in recent
        ],
    )


@router.get("/journal", response_model=JournalResponse)
def get_journal(
    campaign_id: str,
    session: SessionDep,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> JournalResponse:
    projection = load_projection(session, campaign_id)
    entries = public_observations(projection, after_sequence=after_seq, limit=limit)
    return JournalResponse(
        entries=[
            ObservationResponse(
                event_id=entry["event_id"],
                sequence=entry["sequence"],
                turn_id=entry["turn_id"],
                world_time=entry["world_time"],
                text=entry["text"],
                kind=entry["kind"],
                subject_ids=entry["subject_ids"],
                visibility=entry["visibility"],
            )
            for entry in entries
        ],
        next_cursor=entries[-1]["sequence"] if len(entries) == limit else None,
    )
