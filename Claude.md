# Project idea

A tool that helps Viladecans city planners decide where to spend a limited budget to make summer cycling comfortable, and on which fixes (VAS-R1 challenge).

The planner enters a **budget** and picks a **metric**. The map shows the **worst point** for that metric. Clicking it shows the recommended fixes from the cost catalogue. Accepting a fix deducts its cost and recalculates everything, and the next worst point appears. Undo reverts the last accepted fix.

## Metrics (0 = fine, 1 = worst)
- **Water access**: straight-line distance to the nearest water point (real fountain or accepted oasis). Within 100 m counts as a short detour; 300 m or more scores 1.
- **Sun exposure**: real solar index per segment (`solar_mean_positive`; the raster states no unit, it looks like annual irradiation). Scored between the 5th and 95th percentile of the **whole built network**, so it doesn't move with the trails in scope. At junctions it is the mean of that and the unshaded share of the waiting box (how long riders wait there is the junction's exposure time, not part of the score).
- **Temperature**: UTCI at 14:00 on a hot summer afternoon, **computed by us** (`services/heat_model.py`) for every street piece and station from real inputs:
  - weather: the July–August 2023–2025 days at or above the 90th percentile of 14:00 air temperature, averaged (ERA5 via Open-Meteo, table `weather_hour`): ~32.4 °C, 47 % humidity, 3.2 m/s wind, solar radiation
  - share of direct sun = the sun score of the real solar index
  - ground temperature = Landsat surface temperature − air temperature at the ~10:30 overpass + air temperature at 14:00
  - mean radiant temperature with the ERA5-HEAT formula, then the official UTCI polynomial (both from ECMWF `thermofeel`, Apache 2.0)
  - result: 34.6–37.8 °C over the network. **Junctions keep the synthetic VAS-R1 value** (trail UTCI plus their local anomaly, 39.7–44.6 °C)
- **Combined**: weighted mean, heat 0.5 / sun 0.25 / water 0.25 (`weight_*` in assumptions.yaml). Heat already includes local sun, so equal weights would count sun twice.

**Riders are in the data** (synthetic `daily_cyclists_spring/summer` per trail, and an hourly profile). They are used:
- **Worst list** = score × riders/day at the point (severity per person; piece length doesn't change the order). Riders are the trail's spring riders, except at a station: 150 users/day (assumption). A piece off the trails takes the median summer riders of the matched trail streets of its cycle class (seeded into `segment_metrics`) × the trails' spring/summer ratio (1.44).
- **Burden** (what a plan reduces) = Σ score × riders × seconds spent at the point, in rider-hours/day: piece length ÷ 4.2 m/s (on a trail scaled so the trail's total ride time matches its VAS-R1 length, synthetic ÷ real length), a junction's current red-light wait (a green wave shortens it), 60 s at a station.

## Fixes (catalogue INT-01 to INT-06)
| ID | Fix | Where |
|---|---|---|
| INT-01 | Shade trees (12 trees per 100 m) | along the whole real street segment, priced per 100 m |
| INT-02 | Shade sail at traffic-light waiting box | junctions |
| INT-03 | Cyclist Oasis (pergola + chilled fountain + mist + bench) | street pieces and stations (not junctions). **The only water fix.** It is a rest stop beside the route: it adds water only (its cooling is for people who stop at it, not riders passing or waiting at a red light) |
| INT-04 | Cool pavement coating | along the whole real street segment, priced per 100 m |
| INT-05 | Heat-triggered green-wave traffic lights | junctions. Cuts the red-light wait to 15 s (less time in the heat); no UTCI change |
| INT-06 | Solar canopy at bike station | the 17 AMBici stations |

- Fix effects are the catalogue's UTCI cuts, applied on top of the computed baseline (not re-simulated through the heat model).
- Several fixes at one place don't add up linearly: the largest UTCI cut counts fully, the others at 50%.
- INT-08 is not a fix: its CO₂ (0.72 kg) and € (1.15) per replaced 3.8 km trip feed the rider KPIs.
- INT-07 (app) is city-wide and has no location. There is no standalone drinking fountain.
- "Fill the rest of the budget" runs a lazy greedy (CELF) over all (fix, place) candidates by burden reduction per €, then keeps the single best affordable fix instead if that alone reduces more. It is a heuristic, not a proven optimum.

# Rules

1. **Scope is the whole built real network** (1034 segments, 83.5 km). Every street segment is simulated and can be fixed, not only the VAS-R1 trails. UTCI is computed the same way everywhere; off the trails the riders are an assumption (see Riders above). The VAS-R1 trails are mapped onto real streets and keep their synthetic riders, ride time, risk level and summer drop. A trail is the cycle-lane segments ("odcinki", `is_cycle_candidate`) on its matched streets; a matched street with no cycle-lane segment at all (Doctor Reig pedestrian zone, Torrent Ballester park, camí de la Roureda) is taken whole. The mapping is in `scripts/trail_mapping.yaml`.
   - 13 trails.
   - TRM-13 Agrarian Path is dropped because there is no real street match.
   - TRM-03 is Passeig de la Marina only.
   - The 3 "Carril Bici_En Projecte DIBA" lines are excluded (planned, not built).
2. **Clickable points:**
   - each segment of the network, with segments over 100 m split into ~50 m pieces
   - the 5 CRU traffic-light junctions. Their synthetic coordinates are 140–850 m off, so each is placed at the real feature its name refers to (`backend/app/config/point_anchors.yaml`): a trail crossing or a municipal facility. Each point says how it was placed.
   - all 17 real AMBici stations at their real location, also the ones off the trails. Each gets a computed UTCI from the solar index and Landsat temperature of the nearest street segment, and its riders are capped at the nearest trail's. The 2 VAS-R1 stations (EST-B01/B02) are matched to real stations (`vas_station_match` in `assumptions.yaml`) and carry their synthetic notes and shade
3. **Data sources:**
   - **Real (municipal):** segment geometry, length, solar index, fountain locations, AMBici stations, facilities (`scripts/data/`, EPSG:25831, seeded into PostGIS). Cemetery fountains are excluded.
   - **External (OpenStreetMap, ODbL):** park outlines (`leisure=park`), fetched once by `scripts/fetch_osm_parks.py` into `scripts/data/osm_parks.geojson` and seeded into `osm_park`.
   - **External (Landsat 8/9, USGS, public domain):** summer land surface temperature (ST_B10, per-pixel median of clear July–August 2023–2025 scenes at ~10:30, via Microsoft Planetary Computer), sampled per real segment by `scripts/fetch_landsat_lst.py` into `scripts/data/landsat_lst_segments.json` and seeded into `segment_metrics.lst_summer_c`. It is ground surface temperature, not air temperature or UTCI; it is an input of the UTCI model (the ground's heat radiation). Not shown on the map; `/api/map-data` also returns it as `surface_temp`.
   - **External (ERA5 reanalysis via Open-Meteo, CC BY 4.0):** hourly July–August 2023–2025 weather at Viladecans (air temperature, humidity, 10 m wind, solar radiation), fetched once by `scripts/fetch_summer_weather.py` into `scripts/data/summer_weather.json` and seeded into `weather_hour`. Input of the UTCI model.
   - **Display-only map layers** (they never change scores or KPIs): parks (OSM), the 10 Bicibox bike parkings (municipal facilities `Transport / Estacions Bicibox`).
   - **Synthetic (VAS-R1):** junction UTCI, rider counts, hourly profile, junctions, shelters, risk levels, catalogue costs and effects. The trails' synthetic UTCI is used only at the junctions.
4. **The VAS-R1 dataset is synthetic.** Never present it as real Viladecans data, and show a "synthetic/demo data" label in the UI.
5. **Every assumption lives in `backend/app/config/assumptions.yaml`** with a short justification, so the KPIs recalculate when an assumption changes. Current assumptions:
   - the solar index has no unit; sun is scored on network percentiles 5–95, and that score is the share of direct sun in the UTCI model
   - the UTCI model: hot afternoon = days at or above the 90th percentile of 14:00 air temperature; Landsat overpass at 10–11 h; ground albedo 0.15, emissivity 0.95; stations take the nearest street's sun and ground temperature
   - off-trail riders: class median of the matched trail streets × the trails' spring/summer ratio; they win back no riders
   - trees cut the solar index by 50%, a station canopy by 50%; the oasis adds water only; the green wave shortens the wait only
   - a second fix at the same place cools at 50%
   - cycling speed 4.2 m/s, 60 s at a station
   - "comfortable" means UTCI < 32 °C
   - "out of very strong heat" means UTCI < 38 °C
   - combined score weights: heat 0.5, sun 0.25, water 0.25; a station serves 150 users/day
   - removing a trail's heat dose above the comfortable threshold (32 °C) wins back all its summer rider drop, proportionally in between; 122 summer days, 2 trips per cyclist; 50% of won-back trips replace a car
6. **All KPI numbers come from code**, recalculated live from the accepted fixes, never hard-coded. The challenge KPIs:
   - comfortable km (of the whole network)
   - km out of very strong heat (UTCI < 38 °C; the whole network already is on the model's hot afternoon)
   - °C reduction at critical points (the CRU junctions and every point on a trail rated "Critical"), averaged over all of them (uncooled count 0); also shown: average where cooled, max, count
   - tCO₂e avoided: replaced car trips (INT-08 × car share), tree/oasis sequestration and station-canopy PV avoidance, shown separately
   - € per km adapted (trees and cool pavement capex ÷ km they cover)
   - € per new summer cyclist (riders won back → trips ÷ 3.8 km → ÷ 2 trips per cyclist), plus opex per cyclist per year. Riders are won back from the heat dose on pieces, junctions and stations, so junction and station fixes count too
   - € saved per user per year (car share × 2 trips × €1.15 × 122 days)
7. **Credit generative AI tools and open-source licences** (a hackathon rule). Keep a work log of who did what.

# Prototype architecture

- `scripts/export_to_db.py` seeds PostGIS from `scripts/data` (the GeoPackage, the solar GeoJSON, Landsat and weather JSON): real network, fountains, weather, VAS-R1 trails/points/catalogue, and the trail→street links from `scripts/trail_mapping.yaml`. Re-run it when the data or the mapping changes, then restart the backend. Schema changes go through Alembic (`backend/alembic`).
- The backend keeps all domain logic in memory: `services/{dataset,heat_model,effect_service,metric_service,kpi_service,planner_service}.py`. **The API is stateless**: the client sends the list of accepted fixes and the server recomputes from the baseline, so undo is just dropping the last item. `services/dataset.py` loads the dataset from PostGIS once per process: splitting into ~50 m pieces, snapping junctions, placing stations, fountain distances and WGS84 transforms happen in SQL.
- Endpoints:
  - `GET /api/map-data`
  - `POST /api/evaluate`
  - `POST /api/recommend`
  - `POST /api/auto-plan`
- Tests: `cd backend && pip install -r requirements-dev.txt && python -m pytest`. They need the seeded database running (`docker compose up db`).
