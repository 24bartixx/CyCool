# Hackathon App

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
| API      | http://localhost:8000/api/health, /api/places            |
| Database | `postgresql://postgres:postgres@localhost:5432/app`      |

Code changes hot-reload in both the client and the backend. Add or change dependencies with `docker compose up --build`. To reset the database, run `docker compose down -v`.

## Structure

```
backend/app/
  main.py                    FastAPI app, CORS, mounts routers under /api
  core/config.py             settings from env vars
  db/session.py              SQLAlchemy engine + get_db dependency
  routers/                   HTTP layer (places = mock endpoint, health = DB/PostGIS check)
  services/                  business logic (place_service = mock data)
  schemas/                   Pydantic request/response models
client/src/
  theme/colors.css           app colors, the only place to change them
  App.tsx                    routes (React Router)
  components/Layout.tsx      nav + <Outlet />
  pages/                     HomePage (Vite default), PlacesPage, NotFoundPage
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
