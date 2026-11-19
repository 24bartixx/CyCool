from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import health, places

app = FastAPI(title="Hackathon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All endpoints live under /api (the client's dev server proxies /api here).
api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(places.router)

app.include_router(api_router)
