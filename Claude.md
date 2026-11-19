# Project idea

A tool that helps Viladecans city planners decide where to spend a limited budget to make summer cycling comfortable, and on which fixes (VAS-R1 challenge).

The planner enters a **budget** and picks a **metric**. The map shows the **worst point** for that metric. Clicking it shows the recommended fixes from the cost catalogue. Accepting a fix deducts its cost and recalculates everything, and the next worst point appears. Undo reverts the last accepted fix.

## Metrics (0 = fine, 1 = worst)
- **Water access**: straight-line distance to the nearest water point (real fountain or accepted oasis). Within 100 m counts as a short detour; 300 m or more scores 1.
- **Sun exposure**: real solar index per segment (`solar_mean_positive`; the raster states no unit, it looks like annual irradiation). Scored between the 5th and 95th percentile of the **whole built network**, so it doesn't move with the trails in scope. At junctions it is the mean of that and the unshaded share of the waiting box (how long riders wait there is the junction's exposure time, not part of the score).
- **Temperature**: synthetic UTCI at 14:00 per trail. Each trail piece is shifted by its real sun exposure relative to its trail's length-weighted average, times the full-sun minus full-shade UTCI gap of the hourly profile at 14:00 (39.9 − 34.6 = 5.3 °C), so the trail average stays the synthetic value. Junctions and stations: trail UTCI plus their local anomaly.
- **Combined**: weighted mean, heat 0.5 / sun 0.25 / water 0.25 (`weight_*` in assumptions.yaml). Heat already includes local sun, so equal weights would count sun twice.

**Riders are in the data** (synthetic `daily_cyclists_spring/summer` per trail, and an hourly profile). They are used:
- **Worst list** = score × riders/day at the point (severity per person; piece length doesn't change the order). Riders are the trail's spring riders, except at a station: 150 users/day (assumption).
- **Burden** (what a plan reduces) = Σ score × riders × seconds spent at the point, in rider-hours/day: piece length ÷ 4.2 m/s scaled so the trail's total ride time matches its VAS-R1 length (synthetic ÷ real length), a junction's current red-light wait (a green wave shortens it), 60 s at a station.

## Fixes (catalogue INT-01 to INT-06)
| ID | Fix | Where |
|---|---|---|
| INT-01 | Shade trees (12 trees per 100 m) | along the whole real street segment, priced per 100 m |
| INT-02 | Shade sail at traffic-light waiting box | junctions |
| INT-03 | Cyclist Oasis (pergola + chilled fountain + mist + bench) | trail segments and stations (not junctions). **The only water fix.** It is a rest stop beside the route: it adds water only (its cooling is for people who stop at it, not riders passing or waiting at a red light) |
| INT-04 | Cool pavement coating | along the whole real street segment, priced per 100 m |
| INT-05 | Heat-triggered green-wave traffic lights | junctions. Cuts the red-light wait to 15 s (less time in the heat); no UTCI change |
| INT-06 | Solar canopy at bike station | the 17 AMBici stations |

- Several fixes at one place don't add up linearly: the largest UTCI cut counts fully, the others at 50%.
- INT-08 is not a fix: its CO₂ (0.72 kg) and € (1.15) per replaced 3.8 km trip feed the rider KPIs.
- INT-07 (app) is city-wide and has no location. There is no standalone drinking fountain.
- "Fill the rest of the budget" runs a lazy greedy (CELF) over all (fix, place) candidates by burden reduction per €, then keeps the single best affordable fix instead if that alone reduces more. It is a heuristic, not a proven optimum.

# Rules

1. **Scope is the VAS-R1 trails only, mapped onto real streets.** A trail is the cycle-lane segments ("odcinki", `is_cycle_candidate`) on its matched streets; a matched street with no cycle-lane segment at all (Doctor Reig pedestrian zone, Torrent Ballester park, camí de la Roureda) is taken whole. The mapping is in `scripts/trail_mapping.yaml`.
   - 13 trails.
   - TRM-13 Agrarian Path is dropped because there is no real street match.
   - TRM-03 is Passeig de la Marina only.
   - The rest of the network is shown grey.
   - The 3 "Carril Bici_En Projecte DIBA" lines are excluded.
2. **Clickable points:**
   - each segment on a trail, with segments over 100 m split into ~50 m pieces
   - the 5 CRU traffic-light junctions. Their synthetic coordinates are 140–850 m off, so each is placed at the real feature its name refers to (`backend/app/config/point_anchors.yaml`): a trail crossing or a municipal facility. Each point says how it was placed.
   - all 17 real AMBici stations at their real location, also the ones off the trails. Each takes the UTCI of the nearest trail and the solar index of the nearest street segment. The 2 VAS-R1 stations (EST-B01/B02) are matched to real stations (`vas_station_match` in `assumptions.yaml`) and add their synthetic temperature anomaly and shade
3. **Data sources:**
   - **Real (municipal):** segment geometry, length, solar index, fountain locations, AMBici stations, facilities (`scripts/data/`, EPSG:25831, seeded into PostGIS). Cemetery fountains are excluded.
   - **Synthetic (VAS-R1):** temperature/UTCI, rider counts, hourly profile, junctions, shelters, catalogue costs and effects.
4. **The VAS-R1 dataset is synthetic.** Never present it as real Viladecans data, and show a "synthetic/demo data" label in the UI.
5. **Every assumption lives in `backend/app/config/assumptions.yaml`** with a short justification, so the KPIs recalculate when an assumption changes. Current assumptions:
   - the solar index has no unit; sun is scored on network percentiles 5–95
   - trees cut the solar index by 50%, a station canopy by 50%; the oasis adds water only; the green wave shortens the wait only
   - a second fix at the same place cools at 50%
   - cycling speed 4.2 m/s, 60 s at a station
   - "comfortable" means UTCI < 32 °C
   - "out of very strong heat" means UTCI < 38 °C
   - combined score weights: heat 0.5, sun 0.25, water 0.25; a station serves 150 users/day
   - removing a trail's heat dose above the cool benchmark trails (TRM-03/07) wins back all its summer rider drop, proportionally in between (the data agrees: drop % is linear in UTCI, r = 0.99); 122 summer days, 2 trips per cyclist; 50% of won-back trips replace a car
6. **All KPI numbers come from code**, recalculated live from the accepted fixes, never hard-coded. The challenge KPIs:
   - comfortable km
   - km out of very strong heat (UTCI < 38 °C)
   - °C reduction at critical points (the CRU junctions and every point on a trail rated "Critical"), averaged over all of them (uncooled count 0); also shown: average where cooled, max, count
   - tCO₂e avoided: replaced car trips (INT-08 × car share), tree/oasis sequestration and station-canopy PV avoidance, shown separately
   - € per km adapted (trees and cool pavement capex ÷ km they cover)
   - € per new summer cyclist (riders won back → trips ÷ 3.8 km → ÷ 2 trips per cyclist), plus opex per cyclist per year. Riders are won back from the heat dose on pieces, junctions and stations, so junction and station fixes count too
   - € saved per user per year (car share × 2 trips × €1.15 × 122 days)
7. **Credit generative AI tools and open-source licences** (a hackathon rule). Keep a work log of who did what.

# Prototype architecture

- `scripts/export_to_db.py` seeds PostGIS from `scripts/data` (the GeoPackage and the solar GeoJSON): real network, fountains, VAS-R1 trails/points/catalogue, and the trail→street links from `scripts/trail_mapping.yaml`. Re-run it when the data or the mapping changes, then restart the backend. Schema changes go through Alembic (`backend/alembic`).
- The backend keeps all domain logic in memory: `services/{dataset,effect_service,metric_service,kpi_service,planner_service}.py`. **The API is stateless**: the client sends the list of accepted fixes and the server recomputes from the baseline, so undo is just dropping the last item. `services/dataset.py` loads the dataset from PostGIS once per process: splitting into ~50 m pieces, snapping junctions, placing stations, fountain distances and WGS84 transforms happen in SQL.
- Endpoints:
  - `GET /api/map-data`
  - `POST /api/evaluate`
  - `POST /api/recommend`
  - `POST /api/auto-plan`
- Tests: `cd backend && pip install -r requirements-dev.txt && python -m pytest`. They need the seeded database running (`docker compose up db`).
