"""Optimiser plans (optional persistence of budget scenarios)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.geo import PointGeometry
from app.schemas.network import OrmModel

PlanGoal = Literal["comfort_km", "temp_reduction", "cyclists"]


class PlanItemCreate(BaseModel):
    intervention_id: str
    segment_id: int | None = None
    ambici_station_id: int | None = None
    quantity: float = Field(1, gt=0, description="e.g. 3 for 3 x 100 m")
    capex_eur: float = Field(ge=0)
    geometry: PointGeometry | None = Field(None, description="Site of a new fountain/shelter")

    @model_validator(mode="after")
    def needs_a_target(self) -> "PlanItemCreate":
        if self.segment_id is None and self.ambici_station_id is None and self.geometry is None:
            raise ValueError("a plan item needs a segment_id, ambici_station_id or geometry")
        return self


class PlanItem(PlanItemCreate, OrmModel):
    id: int
    plan_id: int


class PlanCreate(BaseModel):
    name: str
    budget_eur: float = Field(ge=0)
    goal: PlanGoal
    params: dict[str, Any] = Field(default_factory=dict)
    items: list[PlanItemCreate] = Field(default_factory=list)


class Plan(OrmModel):
    id: int
    name: str
    budget_eur: float
    goal: PlanGoal
    params: dict[str, Any]
    total_capex_eur: float | None = None
    created_at: datetime
    items: list[PlanItem] = Field(default_factory=list)
