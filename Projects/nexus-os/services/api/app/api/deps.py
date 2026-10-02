"""FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.container import AppContainer


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


Container = Annotated[AppContainer, Depends(get_container)]
