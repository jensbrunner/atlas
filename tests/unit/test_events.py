from __future__ import annotations

import pytest
from atlas.domain.events import (
    EntityCreatedPayload,
    EventDraft,
    EventEnvelope,
    EventType,
    EventValidationError,
    Provenance,
    parse_event_payload,
)
from atlas.domain.models import EntityKind
from pydantic import ValidationError


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(EventValidationError, match="unknown event type"):
        parse_event_payload("entity.teleported", {})


def test_invalid_payload_is_rejected() -> None:
    with pytest.raises(EventValidationError, match="invalid payload"):
        parse_event_payload(EventType.ENTITY_CREATED, {"slug": "missing-fields"})


def test_unknown_payload_field_is_rejected() -> None:
    with pytest.raises(EventValidationError):
        parse_event_payload(
            EventType.ENTITY_CREATED,
            {
                "kind": "npc",
                "slug": "guard",
                "display_name": "Guard",
                "static": {},
                "state": {},
                "unexpected": True,
            },
        )


def test_envelope_requires_known_schema_version() -> None:
    with pytest.raises(ValidationError):
        EventEnvelope(
            schema_version=2,
            event_id="evt_x",
            campaign_id="cmp_x",
            sequence=1,
            event_type=EventType.TIME_ADVANCED,
            world_time=0,
            payload={},
            provenance={"authority": "system"},
        )


def test_draft_round_trips_through_envelope() -> None:
    draft = EventDraft(
        event_type=EventType.ENTITY_CREATED,
        payload=EntityCreatedPayload(
            kind=EntityKind.LOCATION,
            slug="room",
            display_name="Room",
            static={},
            state={},
        ),
        world_time=0,
        subject_id="ent_room",
    )
    envelope = draft.to_envelope(
        event_id="evt_1",
        campaign_id="cmp_1",
        sequence=1,
        turn_id=None,
        provenance=Provenance(authority="seed"),
    )
    assert envelope.sequence == 1
    parsed = envelope.parsed_payload()
    assert isinstance(parsed, EntityCreatedPayload)
    assert parsed.slug == "room"
