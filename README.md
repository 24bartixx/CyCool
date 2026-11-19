# CyCool: heat-comfort planner for Viladecans cycle trails

Pick a budget and a metric (water, sun, heat or combined). The map shows the worst point. Click it to see the catalogue fixes ranked by improvement per euro, then accept one: the cost is deducted, everything is recalculated and the next worst point appears. Synthetic VAS-R1 data is labelled as such in the UI. Rules and assumptions are in `Claude.md` and `backend/app/config/assumptions.yaml`.

## Run the prototype

```bash
# 1. (only when the data changes) rebuild backend/app/data from ../Data
pip install -r scripts/requirements.txt
python scripts/build_dataset.py

# 2a. with Docker
docker compose up --build            # then open http://localhost:5173

# 2b. without Docker (no database needed for the planner)
cd backend && pip install -r requirements-dev.txt && python -m uvicorn app.main:app --port 8000
cd client && npm install && npm run dev
```

Backend tests: `cd backend && python -m pytest`.

---

## Template notes

React + Tailwind client, FastAPI backend, PostgreSQL + PostGIS, all run with Docker Compose.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

| Service  | URL                                                      |
| -------- | -------------------------------------------------------- |
| Client   | http://localhost:5173                                    |
| API docs | http://localhost:8000/docs                               |
| API      | http://localhost:8000/api/map-data, /api/evaluate, /api/recommend |
| Database | `postgresql://postgres:postgres@localhost:5432/app`      |

Code changes hot-reload in both the client and the backend. Add or change dependencies with `docker compose up --build`. To reset the database, run `docker compose down -v`.

## Structure

```
backend/app/
  main.py                    FastAPI app, CORS, mounts routers under /api
  core/config.py             settings from env vars
  db/session.py              SQLAlchemy engine + get_db dependency
  routers/                   HTTP layer (planner = map-data/evaluate/recommend, health = DB/PostGIS check)
  services/                  planner logic (dataset, effects, metrics, KPIs)
  schemas/                   Pydantic request/response models
client/src/
  theme/colors.css           app colors, the only place to change them
  App.tsx                    routes (React Router)
  components/Layout.tsx      nav + <Outlet />
  pages/                     PlannerPage (the app), NotFoundPage
  api/client.ts              fetch helper, useApi hook, API types
```

## Common tasks

**Change colors:** edit `client/src/theme/colors.css`. Each `--color-<name>` token becomes a Tailwind utility (`bg-<name>`, `text-<name>`, `border-<name>/50`, …).

**Add an endpoint:** create a schema in `schemas/`, logic in `services/`, and a router in `routers/`. Then register the router in `main.py` with `api_router.include_router(...)`.

**Add a page:** create it in `client/src/pages/`, add a `<Route>` in `App.tsx` and a `<NavLink>` in `Layout.tsx`.

**Call the API from the client:** use the relative path `/api/...`. In development, Vite proxies it to the backend, so the browser never needs a backend URL.

## Running without Docker

```bash
docker compose up db                     # database only

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload            # reads ../.env

cd client
npm install
npm run dev                              # proxies /api to localhost:8000
```
