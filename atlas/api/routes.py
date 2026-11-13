from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from queue import Queue
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from atlas.agents.campaign import CampaignRequest
from atlas.api.schemas import CreateCampaignBody, PlayTurnBody, WorldTurnBody
from atlas.game import CampaignService
from atlas.pricing import PRICING_SOURCES, PRICING_UPDATED
from atlas.state.render import canon_view, player_view, usage_view
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
        "auto_world_turns": settings.auto_world_turns,
        "world_turn_interval": settings.world_turn_interval,
        "world_turn_minutes": settings.world_turn_minutes,
        "creative_briefs": settings.creative_briefs,
        "narrative_lenses": settings.narrative_lenses,
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
            character=body.character,
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


@router.get("/campaigns/{campaign_id}/usage")
def get_usage(request: Request, campaign_id: str) -> dict[str, Any]:
    settings = request.app.state.settings
    view = usage_view(
        service_from(request).get(campaign_id),
        fallback_input=settings.input_usd_per_million,
        fallback_output=settings.output_usd_per_million,
    )
    view["tracking"] = {
        "provider": settings.provider,
        "live": settings.live,
        "models": {
            "campaign": settings.campaign_model,
            "narrator": settings.narrator_model,
            "world": settings.world_model,
            "auditor": settings.auditor_model,
        },
        "input_usd_per_million": settings.input_usd_per_million,
        "output_usd_per_million": settings.output_usd_per_million,
        "session_usd_limit": settings.session_usd_limit,
        "pricing_updated": PRICING_UPDATED,
        "pricing_sources": PRICING_SOURCES,
    }
    return view


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


@router.get("/campaigns/{campaign_id}/canon")
def get_canon(request: Request, campaign_id: str) -> dict[str, Any]:
    return canon_view(service_from(request).get(campaign_id))


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


@router.post("/campaigns/{campaign_id}/turns/stream")
def play_turn_stream(
    request: Request,
    campaign_id: str,
    body: PlayTurnBody,
) -> StreamingResponse:
    """Run a turn in a worker thread and stream progress events to the browser."""

    service = service_from(request)
    service.get(campaign_id)  # fail with the normal 404 before the stream starts
    events: Queue[dict[str, Any] | None] = Queue()

    def emit(event: dict[str, Any]) -> None:
        events.put(event)

    def run() -> None:
        try:
            result = service.play_turn(campaign_id, body.action, on_event=emit)
            events.put({"type": "done", "result": result.as_dict()})
        except Exception as exc:  # the stream may already have sent headers
            events.put(
                {
                    "type": "error",
                    "code": type(exc).__name__,
                    "message": str(exc),
                }
            )
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()

    def stream() -> Iterator[str]:
        while True:
            event = events.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/campaigns/{campaign_id}/world-turn")
def world_turn(request: Request, campaign_id: str, body: WorldTurnBody) -> dict[str, Any]:
    return service_from(request).world_turn(campaign_id, body.reason)


@router.post("/campaigns/{campaign_id}/audit")
def audit(request: Request, campaign_id: str) -> dict[str, Any]:
    return service_from(request).audit(campaign_id)
