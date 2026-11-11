from __future__ import annotations

from fastapi import APIRouter

from atlas.api.dependencies import SessionDep
from atlas.api.schemas import (
    CampaignCreateRequest,
    CampaignListResponse,
    CampaignResponse,
)
from atlas.persistence.repositories import campaign_model, get_campaign, list_campaigns
from atlas.seed.broken_span import CAMPAIGN_SEED, DEFAULT_TITLE, seed_broken_span

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


def _response(row: object) -> CampaignResponse:
    model = campaign_model(row)  # type: ignore[arg-type]
    return CampaignResponse(
        id=model.id,
        title=model.title,
        rules_version=model.rules_version,
        status=model.status.value,
        state_version=model.state_version,
        current_time=model.current_time,
        seed=model.seed,
        created_at=model.created_at,
    )


@router.post("", response_model=CampaignResponse, status_code=201)
def create_campaign(request: CampaignCreateRequest, session: SessionDep) -> CampaignResponse:
    result = seed_broken_span(
        session,
        title=request.title or DEFAULT_TITLE,
        seed=request.seed if request.seed is not None else CAMPAIGN_SEED,
    )
    session.commit()
    return _response(result.campaign)


@router.get("", response_model=CampaignListResponse)
def get_campaigns(session: SessionDep) -> CampaignListResponse:
    return CampaignListResponse(campaigns=[_response(row) for row in list_campaigns(session)])


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign_by_id(campaign_id: str, session: SessionDep) -> CampaignResponse:
    return _response(get_campaign(session, campaign_id))
