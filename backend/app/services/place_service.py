from app.schemas.place import Place

# Mock data. Replace with DB queries (e.g. a PostGIS table) when ready.
_MOCK_PLACES: list[Place] = [
    Place(id=1, name="Neptune's Fountain", city="Gdańsk", category="landmark", latitude=54.3486, longitude=18.6532),
    Place(id=2, name="European Solidarity Centre", city="Gdańsk", category="museum", latitude=54.3610, longitude=18.6490),
    Place(id=3, name="Sopot Pier", city="Sopot", category="landmark", latitude=54.4461, longitude=18.5726),
    Place(id=4, name="ORP Błyskawica", city="Gdynia", category="museum", latitude=54.5181, longitude=18.5527),
    Place(id=5, name="Kamienna Góra", city="Gdynia", category="viewpoint", latitude=54.5135, longitude=18.5446),
]


class PlaceService:
    def list_places(self, city: str | None = None) -> list[Place]:
        if city is None:
            return list(_MOCK_PLACES)
        return [place for place in _MOCK_PLACES if place.city.casefold() == city.casefold()]

    def get_place(self, place_id: int) -> Place | None:
        return next((place for place in _MOCK_PLACES if place.id == place_id), None)


def get_place_service() -> PlaceService:
    """FastAPI dependency. Override in tests with app.dependency_overrides."""
    return PlaceService()
