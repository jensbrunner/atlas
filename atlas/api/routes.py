from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from atlas.agents.campaign import CampaignRequest
from atlas.api.schemas import CreateCampaignBody, PlayTurnBody, WorldTurnBody
from atlas.game import CampaignService
from atlas.state.render import player_view
from atlas.state.schemas import CampaignMeta


def service_from(request: Request) -> CampaignService:
    service: CampaignService = request.app.state.service
    return service


router = APIRouter(prefix="/api")


def _meta(meta: CampaignMeta) -> dict[str, Any]:
    return meta.model_dump(mode="json")


@router.get("/config")
def config(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "provider": settings.provider,
        "live": settings.live,
        "models": {
            "campaign": settings.campaign_model,
            "narrator": settings.narrator_model,
            "world": settings.world_model,
            "auditor": settings.auditor_model,
        },
        "max_tool_iterations": settings.max_tool_iterations,
    }


@router.get("/campaigns")
def list_campaigns(request: Request) -> dict[str, Any]:
    service = service_from(request)
    return {"campaigns": [_meta(item) for item in service.list_campaigns()]}


@router.post("/campaigns", status_code=201)
def create_campaign(request: Request, body: CreateCampaignBody) -> dict[str, Any]:
    service = service_from(request)
    state, usage = service.create_campaign(
        CampaignRequest(
            title=body.title,
            prompt=body.prompt,
            genre=body.genre,
            tone=body.tone,
        )
    )
    return {
        "campaign": _meta(state.meta),
        "player": player_view(state),
        "usage": usage.model_dump(mode="json"),
    }


@router.get("/campaigns/{campaign_id}")
def get_campaign(request: Request, campaign_id: str) -> dict[str, Any]:
    state = service_from(request).get(campaign_id)
    return {"campaign": _meta(state.meta)}


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(request: Request, campaign_id: str) -> dict[str, Any]:
    service_from(request).delete(campaign_id)
    return {"deleted": campaign_id}


@router.get("/campaigns/{campaign_id}/player")
def get_player(request: Request, campaign_id: str) -> dict[str, Any]:
    return service_from(request).player(campaign_id)


@router.get("/campaigns/{campaign_id}/gm")
def get_gm(request: Request, campaign_id: str) -> dict[str, Any]:
    return service_from(request).gm(campaign_id)


@router.get("/campaigns/{campaign_id}/turns")
def get_turns(
    request: Request,
    campaign_id: str,
    after: int = Query(default=-1, ge=-1),
    limit: int = Query(default=50, ge=1, le=200),
    include_world: bool = Query(default=False),
) -> dict[str, Any]:
    state = service_from(request).get(campaign_id)
    allowed = {"opening", "player", "world"} if include_world else {"opening", "player"}
    turns = [turn for turn in state.turns if turn.kind in allowed and turn.turn > after][:limit]
    payload = [
        {
            "turn": turn.turn,
            "kind": turn.kind,
            "action": turn.action,
            "narration": turn.narration,
            "world_time": turn.world_time_after,
            "rolls": [roll.model_dump(mode="json") for roll in turn.rolls],
            "changes": turn.changes,
        }
        for turn in turns
    ]
    next_cursor = turns[-1].turn if len(turns) == limit else None
    return {"turns": payload, "next_cursor": next_cursor}


@router.post("/campaigns/{campaign_id}/turns")
def play_turn(request: Request, campaign_id: str, body: PlayTurnBody) -> dict[str, Any]:
    result = service_from(request).play_turn(campaign_id, body.action)
    return result.as_dict()


@router.post("/campaigns/{campaign_id}/world-turn")
def world_turn(request: Request, campaign_id: str, body: WorldTurnBody) -> dict[str, Any]:
    return service_from(request).world_turn(campaign_id, body.reason)


@router.post("/campaigns/{campaign_id}/audit")
def audit(request: Request, campaign_id: str) -> dict[str, Any]:
    return service_from(request).audit(campaign_id)
