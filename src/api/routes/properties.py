from __future__ import annotations

from fastapi import APIRouter

from src.domain.properties import list_properties

router = APIRouter()


@router.get("/properties")
async def get_properties() -> list[dict]:
    """List all Oyster Collection properties."""
    return list_properties()
