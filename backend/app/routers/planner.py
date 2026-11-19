from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.planner import PlanRequest, RecommendRequest
from app.services.dataset import Dataset, get_dataset
from app.services.effect_service import PlanError
from app.services.planner_service import auto_plan, evaluate, recommend, static_map_data

router = APIRouter(tags=["planner"])

DatasetDep = Annotated[Dataset, Depends(get_dataset)]


def _pairs(req: PlanRequest) -> list[tuple[str, str]]:
    return [(a.fix_id, a.point_id) for a in req.accepted]


@router.get("/map-data")
def map_data(ds: DatasetDep) -> dict[str, Any]:
    """Static layers: trails, clickable points, fountains, parks, bike parkings, surface temperature, context network, catalogue, assumptions."""
    return static_map_data(ds)


@router.post("/evaluate")
def evaluate_plan(req: PlanRequest, ds: DatasetDep) -> dict[str, Any]:
    """Scores, worst points, budget and KPIs for the baseline plus the accepted fixes."""
    try:
        return evaluate(ds, req.metric, req.budget, _pairs(req))
    except PlanError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/recommend")
def recommend_fixes(req: RecommendRequest, ds: DatasetDep) -> dict[str, Any]:
    """Fixes allowed at one point, ranked by improvement of the chosen metric per euro."""
    try:
        return recommend(ds, req.metric, req.budget, _pairs(req), req.point_id)
    except PlanError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/auto-plan")
def auto_plan_fixes(req: PlanRequest, ds: DatasetDep) -> dict[str, Any]:
    """Adds fixes to the plan greedily by burden reduction per euro until the budget runs out."""
    try:
        return auto_plan(ds, req.metric, req.budget, _pairs(req))
    except PlanError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
