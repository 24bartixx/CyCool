"""Fetch hourly summer weather for Viladecans into scripts/data/summer_weather.json.

One-off: the output file is committed, so seeding (export_to_db.py) stays offline and reproducible.
Re-run only to refresh the weather.

Source: Open-Meteo historical weather API (https://open-meteo.com/en/docs/historical-weather-api),
model "best_match" (ECMWF ERA5 / ERA5-Land reanalysis, the land model where it exists). Weather data by
Open-Meteo.com, licensed under CC BY 4.0; ERA5 contains modified Copernicus Climate Change Service information.

Kept: every hour of July and August 2023-2025 (local time, Europe/Madrid) with air temperature, relative
humidity, 10 m wind speed and the solar radiation components. The backend picks the design hour and the hot
days from these rows (see assumptions.yaml) and computes UTCI per street segment from them.

Usage (from the repo root):
    python scripts/fetch_summer_weather.py [--out scripts/data/summer_weather.json]
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = SCRIPTS_DIR / "data" / "summer_weather.json"
API_URL = "https://archive-api.open-meteo.com/v1/archive"
USER_AGENT = "CyCool-hackathon-seed"
LATITUDE, LONGITUDE = 41.3155, 2.0145  # Viladecans town centre
YEARS = (2023, 2024, 2025)
MONTHS = ("07", "08")
VARIABLES = {  # Open-Meteo name -> name in the output file
    "temperature_2m": "temp_c",
    "relative_humidity_2m": "rh_pct",
    "wind_speed_10m": "wind_ms",
    "shortwave_radiation": "ghi_wm2",
    "diffuse_radiation": "dhi_wm2",
    "direct_radiation": "direct_h_wm2",
    "direct_normal_irradiance": "dni_wm2",
}


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(year: int) -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": f"{year}-07-01",
        "end_date": f"{year}-08-31",
        "hourly": ",".join(VARIABLES),
        "wind_speed_unit": "ms",
        "timezone": "Europe/Madrid",
        "models": "best_match",
    })
    req = urllib.request.Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120, context=_ssl_context()) as resp:
        return json.load(resp)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    hours: list[dict[str, Any]] = []
    grid = None
    for year in YEARS:
        data = fetch(year)
        grid = (data["latitude"], data["longitude"], data.get("elevation"))
        h = data["hourly"]
        for i, t in enumerate(h["time"]):
            if t[5:7] not in MONTHS:
                continue
            row = {"time": t, **{out: h[name][i] for name, out in VARIABLES.items()}}
            if any(v is None for v in row.values()):
                continue
            hours.append(row)
        print(f"  {year}: {sum(1 for r in hours if r['time'].startswith(str(year)))} hours")
    if not hours:
        sys.exit("No weather rows returned")

    out = {
        "source": "Open-Meteo historical weather API, model best_match (ECMWF ERA5 / ERA5-Land reanalysis)",
        "license": "CC BY 4.0 (Open-Meteo.com); contains modified Copernicus Climate Change Service information",
        "url": "https://open-meteo.com/en/docs/historical-weather-api",
        "fetched": date.today().isoformat(),
        "requested": {"latitude": LATITUDE, "longitude": LONGITUDE},
        "grid": {"latitude": grid[0], "longitude": grid[1], "elevation_m": grid[2]},
        "timezone": "Europe/Madrid (local time, summer = UTC+2)",
        "note": "Radiation is the mean of the preceding hour; wind at 10 m; July and August only.",
        "hours": [],
    }
    # One hour per line keeps the file small and diffable.
    head = json.dumps(out, indent=1, ensure_ascii=False).rsplit("[]", 1)[0]
    rows = ",\n  ".join(json.dumps(r, ensure_ascii=False) for r in hours)
    args.out.write_text(f"{head}[\n  {rows}\n ]\n}}\n", encoding="utf-8")
    print(f"Wrote {len(hours)} hours to {args.out}")


if __name__ == "__main__":
    main()
