from typing import Literal

from pydantic import BaseModel, Field

Metric = Literal["water", "sun", "heat", "combined"]


class AcceptedFix(BaseModel):
    fix_id: str
    point_id: str


class PlanRequest(BaseModel):
    metric: Metric = "combined"
    budget: float = Field(ge=0, le=100_000_000)
    accepted: list[AcceptedFix] = Field(default_factory=list, max_length=500)


class RecommendRequest(PlanRequest):
    point_id: str
