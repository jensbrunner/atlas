from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from atlas.game.turn_service import TurnService


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_turn_service(request: Request) -> TurnService:
    service: TurnService = request.app.state.turn_service
    return service


SessionDep = Annotated[Session, Depends(get_session)]
TurnServiceDep = Annotated[TurnService, Depends(get_turn_service)]
