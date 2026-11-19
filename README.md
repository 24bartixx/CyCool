# Hackathon App

React + Tailwind client, FastAPI backend, PostgreSQL + PostGIS, all run with Docker Compose.

## Setup

### 1. Prerequisites

- Docker Desktop (running)
- Python 3.11+ (for the seed script)
- The input data in `scripts/data/` (not in git, get it from the team):

| File                                | Contents                                         |
| ----------------------------------- | ------------------------------------------------ |
| `CoolCycle_Viladecans.gpkg`         | Municipal layers and the synthetic VAS-R1 tables |
| `bike_solar_screen_geojson.geojson` | Solar statistics for each cycle segment          |
| `osm_parks.geojson`                 | Park outlines from OpenStreetMap (see below)     |
| `landsat_lst_segments.json`         | Landsat summer surface temperature per segment   |
| `summer_weather.json`               | Hourly July–August weather (ERA5, Open-Meteo)    |

`osm_parks.geojson` holds the `leisure=park` polygons inside the Viladecans boundary, taken from the Overpass API. To refresh it, run `python scripts/fetch_osm_parks.py`. You don't need this for a normal setup. Park data © OpenStreetMap contributors, licensed under the [ODbL](https://www.openstreetmap.org/copyright).

`landsat_lst_segments.json` holds the summer land surface temperature of every network segment: the per-pixel median of clear July–August 2023–2025 Landsat 8/9 Collection 2 Level-2 scenes (ST_B10, ~10:30 overpass), sampled every 10 m along each segment. To refresh it, run `python scripts/fetch_landsat_lst.py` (reads from Microsoft Planetary Computer, no account needed). It is ground surface temperature, not UTCI; the backend's UTCI model uses it for the heat the ground radiates (the API also returns it as `surface_temp`; it is not drawn on the map). Landsat data courtesy of the U.S. Geological Survey (public domain).

`summer_weather.json` holds every hour of July and August 2023–2025 at Viladecans: air temperature, humidity, 10 m wind and solar radiation from the ECMWF ERA5 / ERA5-Land reanalysis. To refresh it, run `python scripts/fetch_summer_weather.py` (Open-Meteo historical weather API, no account needed). The backend averages the hottest afternoons and computes UTCI per street with ECMWF's [thermofeel](https://github.com/ecmwf/thermofeel) library (Apache 2.0). Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); it contains modified Copernicus Climate Change Service information.

### 2. Create `.env` and pick a free database port

```bash
cp .env.example .env
```

The database is exposed on `POSTGRES_PORT` (default `5432`). If PostgreSQL is also installed directly on your machine, it already uses 5432, and the seed script and database tools will silently connect to _that_ server instead of the Docker one. Check before starting:

```bash
# Windows (PowerShell)
netstat -ano | findstr :5432
# macOS / Linux
lsof -i :5432
```

If anything is listening, set another port in `.env`, for example:

```
POSTGRES_PORT=5433
```

The backend container is not affected; it always reaches the database inside Docker on 5432.

### 3. Start the stack

```bash
docker compose up -d --build
```

The backend applies the database migrations (`alembic upgrade head`) every time it starts, so the tables are created automatically. Check it worked:

```bash
docker compose logs backend             # look for "Running upgrade" (first start) and "Application startup complete"
curl http://localhost:8000/api/health   # {"status":"ok","database":true,"postgis":"3.6.1"}
```

| Service  | URL                                                               |
| -------- | ----------------------------------------------------------------- |
| Client   | http://localhost:5173                                             |
| API docs | http://localhost:8000/docs                                        |
| API      | http://localhost:8000/api/map-data, /api/evaluate, /api/recommend |
| Database | `postgresql://postgres:postgres@localhost:<POSTGRES_PORT>/app`    |

### 4. Seed the database

The seed script runs on your machine and connects using the `POSTGRES_*` values from `.env`. Run it from the repo root, in a virtual environment:

```bash
# Windows (PowerShell)
python -m venv scripts/.venv
scripts\.venv\Scripts\Activate.ps1

# macOS / Linux
python -m venv scripts/.venv
source scripts/.venv/bin/activate

# both
python -m pip install -r scripts/requirements.txt
python scripts/export_to_db.py
```

A successful run ends with `Done` and loads 1037 segments, 129 fountains, 17 AMBici stations, 188 facilities, 41 OSM parks, Landsat surface temperature for all 1037 segments, 4464 weather hours and the synthetic tables, with the 13 mapped synthetic routes linked (TRM-13 has no real street match; see `scripts/trail_mapping.yaml`). Restart the backend afterwards (`docker compose restart backend`): it loads the planner dataset from the database once at startup. After pulling a change to `backend/requirements.txt`, rebuild it instead (`docker compose up -d --build backend`).

| Command                                         | What it does                                                 |
| ----------------------------------------------- | ------------------------------------------------------------ |
| `python scripts/export_to_db.py`                | Loads all data, updating existing rows. Keeps saved plans.   |
| `python scripts/export_to_db.py --reset`        | Empties all tables first. Deletes saved plans.               |
| `python scripts/export_to_db.py --data-dir DIR` | Reads the input files from `DIR` instead of `scripts/data/`. |

**Synthetic data:** `intervention_type`, `hourly_profile` and `syn_segment` (and the rider counts derived from them) come from the VAS-R1 challenge dataset. They are demo data, not real Viladecans data.

### 5. Connect with a database tool (DBeaver, pgAdmin)

| Field    | Value                              |
| -------- | ---------------------------------- |
| Host     | `localhost`                        |
| Port     | your `POSTGRES_PORT` (e.g. `5433`) |
| Database | `app` (not the default `postgres`) |
| Username | `postgres`                         |
| Password | `postgres`                         |

Tables are under `app` → Schemas → `public`.

### Day to day

Code changes hot-reload in both the client and the backend. Add or change dependencies with `docker compose up --build`.

| Task                                | Command                                                                   |
| ----------------------------------- | ------------------------------------------------------------------------- |
| Start / stop everything             | `docker compose up -d` / `docker compose down`                            |
| Reload data after the input changed | `python scripts/export_to_db.py`                                          |
| Wipe the database and start over    | `docker compose down -v`, `docker compose up -d --build`, then seed again |

### Troubleshooting

| Problem                                            | Cause and fix                                                                                                                          |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'psycopg'`   | The venv is not active, or packages went to another Python. Activate it and use `python -m pip install -r scripts/requirements.txt`.   |
| `database "app" does not exist` (any language)     | You reached a local PostgreSQL, not Docker. Change `POSTGRES_PORT` in `.env` (step 2), then `docker compose up -d`.                    |
| `Tables not found. Run the migrations first`       | The backend has not started yet or failed. Check `docker compose logs backend`.                                                        |
| Migration fails with `relation ... already exists` | Your database has tables from before Alembic was added. Wipe it: `docker compose down -v`, `docker compose up -d --build`, seed again. |
| No tables in DBeaver                               | Wrong port or database. Use your `POSTGRES_PORT` and database `app` (step 5), then refresh (F5).                                       |
| Port 5173 or 8000 already in use                   | Change `CLIENT_PORT` or `BACKEND_PORT` in `.env`.                                                                                      |

## Database migrations

The models in `backend/app/models/` define the schema. After changing a model, create and apply a migration from the `backend/` directory:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"  # writes alembic/versions/<date>_<rev>_<slug>.py
alembic upgrade head                                     # applies it
```

Always read the generated file before applying it. Autogenerate does not detect removed tables, so write `op.drop_table(...)` by hand when you delete a model.

| Command                | What it does                                |
| ---------------------- | ------------------------------------------- |
| `alembic upgrade head` | Applies all pending migrations              |
| `alembic downgrade -1` | Reverts the last migration                  |
| `alembic check`        | Fails if the models and the database differ |
| `alembic history`      | Lists all migrations                        |

Running Alembic outside Docker needs the backend dependencies: `pip install -r backend/requirements.txt`.

## Structure

```
backend/app/
  main.py                    FastAPI app, CORS, mounts routers under /api
  core/config.py             settings from env vars
  db/session.py              SQLAlchemy engine + get_db dependency
  routers/                   HTTP layer (planner = map-data/evaluate/recommend, health = DB/PostGIS check)
  services/                  planner logic (dataset, UTCI heat model, effects, metrics, KPIs)
  schemas/                   Pydantic request/response models
backend/alembic/
  env.py                     Alembic setup (uses app settings and models)
  versions/                  migration files
scripts/
  export_to_db.py            seeds the database and computes per-segment metrics
  fetch_osm_parks.py         one-off: OpenStreetMap park outlines -> data/osm_parks.geojson
  fetch_landsat_lst.py       one-off: Landsat summer surface temperature per segment -> data/landsat_lst_segments.json
  fetch_summer_weather.py    one-off: hourly July-August weather (ERA5 via Open-Meteo) -> data/summer_weather.json
  data/                      input data (GeoPackage, GeoJSON)
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

The database still runs in Docker; the backend and client run on your machine.

```bash
docker compose up -d db                  # database only

cd backend
python -m venv .venv                     # activate: .venv\Scripts\Activate.ps1 (Windows) or source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head                     # create/update tables (Docker does this for you otherwise)
uvicorn app.main:app --reload            # reads ../.env

cd client
npm install
npm run dev                              # proxies /api to localhost:8000
```

Then seed the database as in step 4.
