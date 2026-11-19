"""Summer land surface temperature per street segment from Landsat 8/9 -> scripts/data/landsat_lst_segments.json.

One-off: the output file is committed, so seeding (export_to_db.py) stays offline and reproducible.
Re-run only to refresh it.

What it does:
  1. Searches the Landsat Collection 2 Level-2 archive on Microsoft Planetary Computer for clear-sky
     July-August scenes (Landsat 8 and 9, scene cloud cover < 10%) over the Viladecans network.
  2. Reads the surface temperature band (ST_B10, asset "lwir11"; thermal band at 100 m, delivered on a
     30 m grid) on a 30 m EPSG:25831 grid, masks cloud, cirrus and cloud-shadow pixels (QA_PIXEL), and
     takes the per-pixel median over all clear observations (overlapping tiles of one pass are merged first).
  3. Samples that median every 10 m along each real network segment and stores the segment mean in °C.

This is land SURFACE temperature at the ~10:30 local overpass, not air temperature or UTCI, so it is a
display-only layer for spotting relatively hot streets; it never changes scores or KPIs.
Landsat data courtesy of the U.S. Geological Survey (public domain).

Usage (from the repo root):
    pip install -r scripts/requirements.txt
    python scripts/fetch_landsat_lst.py [--years 2023 2024 2025] [--out scripts/data/landsat_lst_segments.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import warnings
from collections import defaultdict
from datetime import date
from pathlib import Path

# rasterio and pyproj wheels ship their own PROJ database; a system PROJ_LIB (e.g. set by a PostGIS install)
# points them at an incompatible one, so drop it before they load.
for _var in ("PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_var, None)

import numpy as np
import planetary_computer
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from shapely import wkb

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from export_to_db import GPKG_NAME, SRID, gpkg_wkb  # noqa: E402

DEFAULT_OUT = SCRIPTS_DIR / "data" / "landsat_lst_segments.json"
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
MONTHS = (7, 8)  # peak summer
MAX_SCENE_CLOUD = 10  # % scene cloud cover
PIXEL_M = 30.0
PAD_M = 300.0  # grid margin around the network
SAMPLE_STEP_M = 10.0  # sampling step along a segment
MIN_CLEAR_OBS = 3  # pixels with fewer clear observations are left empty
# Collection 2 Level-2 surface temperature: Kelvin = DN * 0.00341802 + 149.0, DN 0 = no data.
ST_SCALE, ST_OFFSET = 0.00341802, 149.0
# QA_PIXEL bits that make a pixel unusable: dilated cloud, cirrus, cloud, cloud shadow.
QA_BAD = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)


def load_segments() -> dict[int, object]:
    con = sqlite3.connect(f"file:{(SCRIPTS_DIR / 'data' / GPKG_NAME).as_posix()}?mode=ro", uri=True)
    rows = con.execute("SELECT objectid, geom FROM bike_network_source").fetchall()
    con.close()
    return {int(oid): wkb.loads(gpkg_wkb(g)) for oid, g in rows}


def search(bounds_utm: tuple[float, float, float, float], years: list[int]) -> list:
    to_wgs = Transformer.from_crs(SRID, 4326, always_xy=True).transform
    x0, y0, x1, y1 = bounds_utm
    lo, la = to_wgs(x0, y0)
    hi, ha = to_wgs(x1, y1)
    cat = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = []
    for y in years:
        items += cat.search(
            collections=[COLLECTION],
            bbox=[lo, la, hi, ha],
            datetime=f"{y}-{MONTHS[0]:02d}-01/{y}-{MONTHS[-1]:02d}-31",
            query={"eo:cloud_cover": {"lt": MAX_SCENE_CLOUD}, "platform": {"in": ["landsat-8", "landsat-9"]}},
        ).item_collection()
    return sorted(items, key=lambda i: i.datetime)


def read_on_grid(href: str, transform, width: int, height: int) -> np.ndarray:
    with rasterio.open(href) as src, WarpedVRT(
        src, crs=f"EPSG:{SRID}", transform=transform, width=width, height=height,
        resampling=Resampling.nearest, nodata=0,
    ) as vrt:
        return vrt.read(1)


def scene_lst(item, transform, width: int, height: int) -> np.ndarray:
    """Surface temperature in °C on the grid, NaN where cloudy or no data."""
    st = read_on_grid(item.assets["lwir11"].href, transform, width, height).astype("float64")
    qa = read_on_grid(item.assets["qa_pixel"].href, transform, width, height)
    out = st * ST_SCALE + ST_OFFSET - 273.15
    out[(st == 0) | ((qa & QA_BAD) != 0) | (qa == 1)] = np.nan  # qa == 1: fill
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024, 2025])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    segments = load_segments()
    xs0, ys0, xs1, ys1 = np.array([g.bounds for g in segments.values()]).T
    x0, y0 = xs0.min() - PAD_M, ys0.min() - PAD_M
    x1, y1 = xs1.max() + PAD_M, ys1.max() + PAD_M
    width, height = int(np.ceil((x1 - x0) / PIXEL_M)), int(np.ceil((y1 - y0) / PIXEL_M))
    transform = from_origin(x0, y1, PIXEL_M, PIXEL_M)

    items = search((x0, y0, x1, y1), args.years)
    if not items:
        sys.exit("No Landsat scenes found.")
    # One pass can cover the area from two overlapping tiles (same date): merge them before the median.
    by_date: dict[str, list[np.ndarray]] = defaultdict(list)
    used = []
    for item in items:
        lst = scene_lst(item, transform, width, height)
        clear = float(np.isfinite(lst).mean())
        print(f"  {item.id}  clear and covered {clear:5.1%}")
        if clear < 0.5:  # mostly cloud or outside this tile; its pixels would only add edge noise
            continue
        by_date[item.datetime.date().isoformat()].append(lst)
        used.append(item.id)
    if not by_date:
        sys.exit("No clear scenes over the area.")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels (outside a tile or always cloudy)
        stack = np.stack([np.nanmean(np.stack(v), axis=0) for v in by_date.values()])
        obs = np.isfinite(stack).sum(axis=0)
        median = np.nanmedian(stack, axis=0)
    median[obs < MIN_CLEAR_OBS] = np.nan

    values: dict[str, float] = {}
    for oid, geom in segments.items():
        n = max(2, int(np.ceil(geom.length / SAMPLE_STEP_M)) + 1)
        pts = [geom.interpolate(d) for d in np.linspace(0, geom.length, n)]
        cols = np.clip(((np.array([p.x for p in pts]) - x0) // PIXEL_M).astype(int), 0, width - 1)
        rows = np.clip(((y1 - np.array([p.y for p in pts])) // PIXEL_M).astype(int), 0, height - 1)
        v = median[rows, cols]
        if np.isfinite(v).any():
            values[str(oid)] = round(float(np.nanmean(v)), 2)

    vals = np.array(list(values.values()))
    out = {
        "source": "Landsat 8/9 Collection 2 Level-2 surface temperature (ST_B10), via Microsoft Planetary Computer",
        "license": "Landsat data courtesy of the U.S. Geological Survey; public domain",
        "fetched": date.today().isoformat(),
        "method": (
            f"Per-pixel median of clear-sky {'/'.join(map(str, MONTHS))} observations "
            f"({min(args.years)}-{max(args.years)}, scene cloud < {MAX_SCENE_CLOUD}%, QA cloud/shadow masked, "
            f">= {MIN_CLEAR_OBS} clear dates per pixel) on a {PIXEL_M:.0f} m EPSG:{SRID} grid; segment value = mean "
            f"of samples every {SAMPLE_STEP_M:.0f} m. Land surface temperature at ~10:30 local time, not air "
            "temperature or UTCI."
        ),
        "unit": "°C",
        "dates": sorted(by_date),
        "scenes": used,
        "segments": values,
    }
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(
        f"{len(values)}/{len(segments)} segments from {len(by_date)} dates ({len(used)} scenes); "
        f"LST {vals.min():.1f}-{vals.max():.1f} °C, median {np.median(vals):.1f} °C -> {args.out}"
    )


if __name__ == "__main__":
    main()
