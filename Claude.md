# Project idea

A tool that helps Viladecans city planners decide where to spend a limited budget to make summer cycling comfortable, and on which fixes (VAS-R1 challenge).

The planner enters a **budget** and picks a **metric**. The map shows the **worst point** for that metric. Clicking it shows the recommended fixes from the cost catalogue. Accepting a fix deducts its cost and recalculates everything, and the next worst point appears. Undo reverts the last accepted fix.

## Metrics (0 = fine, 1 = worst)
- **Water access**: distance to the nearest water point. A fountain within 100 m counts as a short detour; a score of 1 means 300 m or more.
- **Sun exposure**: real solar value per segment (`solar_mean_positive`, assumed W/m²), scaled between the trail minimum and maximum. At junctions it is the mean of that and the red-light wait exposure (wait / 70 s × unshaded share).
- **Temperature**: synthetic UTCI at 14 h per trail, plus the local temperature anomaly at junctions.
- **Combined**: the mean of the three, with equal weights.

**Worst = metric × segment length / 100 m** (junctions and stations count as 100 m). There is no ridership data (cyclists per day), so it is not used anywhere.

## Fixes (catalogue INT-01 to INT-06 only)
| ID | Fix | Where |
|---|---|---|
| INT-01 | Shade trees (12 trees per 100 m) | per 100 m of trail |
| INT-02 | Shade sail at traffic-light waiting box | junctions |
| INT-03 | Cyclist Oasis (pergola + chilled fountain + mist + bench) | trail segments and stations (not junctions). **This is the only water fix** |
| INT-04 | Cool pavement coating | per 100 m of trail |
| INT-05 | Heat-triggered green-wave traffic lights | junctions |
| INT-06 | Solar canopy at bike station | the 17 AMBici stations |

Not used:
- INT-07 (app) is city-wide and has no location.
- INT-08 (modal-shift factors per replaced trip) needs ridership data, which we don't have.
- There is no standalone drinking fountain.

# Rules

1. **Scope is the VAS-R1 trails only, mapped onto real streets.** A trail is all network segments ("odcinki") on its matched street; the mapping is in `scripts/trail_mapping.yaml`.
   - 13 trails.
   - TRM-13 Agrarian Path is dropped because there is no real street match.
   - TRM-03 is Passeig de la Marina only.
   - The rest of the network is shown grey.
   - The 3 "Carril Bici_En Projecte DIBA" lines are excluded.
2. **Clickable points:**
   - each segment on a trail, with segments over 100 m split into ~50 m pieces
   - the 5 CRU traffic-light junctions, snapped onto their own trail and labelled as approximate locations, because their synthetic coordinates are 140–850 m off
   - all 17 real AMBici stations at their real location, also the ones off the trails. Each takes the UTCI of the nearest trail and the solar value of the nearest street segment. The 2 VAS-R1 stations (EST-B01/B02) are matched to real stations (`vas_station_match` in `assumptions.yaml`) and add their synthetic temperature anomaly
3. **Data sources:**
   - **Real (municipal):** segment geometry, length, solar value, fountain and AMBici station locations (`scripts/data/`, EPSG:25831, seeded into PostGIS). Cemetery fountains are excluded.
   - **Synthetic (VAS-R1):** temperature/UTCI, junctions, shelters, catalogue costs and effects.
4. **The VAS-R1 dataset is synthetic.** Never present it as real Viladecans data, and show a "synthetic/demo data" label in the UI.
5. **Every assumption lives in `backend/app/config/assumptions.yaml`** with a short justification, so the KPIs recalculate when an assumption changes. Current assumptions:
   - solar value is in W/m²
   - trees cut solar by 50%
   - an oasis cools within 25 m and cuts solar by 30%
   - a station canopy cuts solar by 50%
   - "comfortable" means UTCI < 32 °C
   - "out of very strong heat" means UTCI < 38 °C
6. **All KPI numbers come from code**, recalculated live from the accepted fixes, never hard-coded:
   - comfortable km
   - km out of very strong heat (UTCI < 38 °C)
   - °C reduction
   - tCO₂e (sequestration/avoidance of the accepted fixes only)
   - € per km
7. **Credit generative AI tools and open-source licences** (a hackathon rule). Keep a work log of who did what.

# Prototype architecture

- `scripts/export_to_db.py` seeds PostGIS from `scripts/data` (the GeoPackage and the solar GeoJSON): real network, fountains, VAS-R1 trails/points/catalogue, and the trail→street links from `scripts/trail_mapping.yaml`. Re-run it when the data or the mapping changes, then restart the backend. Schema changes go through Alembic (`backend/alembic`).
- The backend keeps all domain logic in memory: `services/{dataset,effect_service,metric_service,kpi_service,planner_service}.py`. **The API is stateless**: the client sends the list of accepted fixes and the server recomputes from the baseline, so undo is just dropping the last item. `services/dataset.py` loads the dataset from PostGIS once per process: splitting into ~50 m pieces, snapping junctions, placing stations, fountain distances and WGS84 transforms happen in SQL.
- Endpoints:
  - `GET /api/map-data`
  - `POST /api/evaluate`
  - `POST /api/recommend`
- Tests: `cd backend && pip install -r requirements-dev.txt && python -m pytest`. They need the seeded database running (`docker compose up db`).
