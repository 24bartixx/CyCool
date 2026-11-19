from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.place import Place
from app.services.place_service import PlaceService, get_place_service

router = APIRouter(prefix="/places", tags=["places"])

PlaceServiceDep = Annotated[PlaceService, Depends(get_place_service)]


@router.get("")
def list_places(service: PlaceServiceDep, city: str | None = None) -> list[Place]:
    return service.list_places(city)


@router.get("/{place_id}")
def get_place(place_id: int, service: PlaceServiceDep) -> Place:
    place = service.get_place(place_id)
    if place is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return place
