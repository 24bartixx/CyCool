from pydantic import BaseModel


class Place(BaseModel):
    id: int
    name: str
    city: str
    category: str
    latitude: float
    longitude: float
