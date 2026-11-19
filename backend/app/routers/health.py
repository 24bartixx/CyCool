from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    """Checks the database connection and reports the installed PostGIS version."""
    try:
        postgis = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
        ).scalar()
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="error", database=False, postgis=None)

    return HealthResponse(status="ok" if postgis else "degraded", database=True, postgis=postgis)
