"""Fetch the park polygons of Viladecans from OpenStreetMap into scripts/data/osm_parks.geojson.

One-off: the output file is committed, so seeding (export_to_db.py) stays offline and reproducible.
Re-run only to refresh the parks. Data © OpenStreetMap contributors, licensed under the ODbL.

Usage (from the repo root):
    pip install -r scripts/requirements.txt
    python scripts/fetch_osm_parks.py [--out scripts/data/osm_parks.geojson]
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, MultiPolygon, Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = SCRIPTS_DIR / "data" / "osm_parks.geojson"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
ATTEMPTS = 3
USER_AGENT = "CyCool-hackathon-seed"
QUERY = """
[out:json][timeout:60];
area["boundary"="administrative"]["admin_level"="8"]["name"="Viladecans"]->.a;
nwr["leisure"="park"](area.a);
out geom;
"""


def _ssl_context() -> ssl.SSLContext:
    """Prefer certifi's CA bundle: some Python installs ship an outdated store that rejects the Overpass chain."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch() -> list[dict[str, Any]]:
    """Ask each Overpass server in turn (the public ones are often busy), a few rounds with a pause."""
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    ctx = _ssl_context()
    for attempt in range(ATTEMPTS):
        for url in OVERPASS_URLS:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
                    return json.load(resp)["elements"]
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                print(f"  {url}: {e}", file=sys.stderr)
        if attempt + 1 < ATTEMPTS:
            time.sleep(15)
    sys.exit("No Overpass server answered; try again later.")


def _line(points: list[dict[str, float]]) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in points]


def _polygons(geom: BaseGeometry) -> MultiPolygon | None:
    """Keep only the polygon parts of a (made valid) geometry, as a MultiPolygon."""
    geom = make_valid(geom)
    parts = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon) and not g.is_empty]
    return MultiPolygon(parts) if parts else None


def way_geometry(el: dict[str, Any]) -> MultiPolygon | None:
    coords = _line(el.get("geometry") or [])
    if len(coords) < 4 or coords[0] != coords[-1]:
        return None  # an open way is not an area
    return _polygons(Polygon(coords))


def relation_geometry(el: dict[str, Any]) -> MultiPolygon | None:
    rings: dict[str, list[LineString]] = {"outer": [], "inner": []}
    for m in el.get("members") or []:
        if m.get("type") == "way" and m.get("geometry") and len(m["geometry"]) >= 2:
            rings["inner" if m.get("role") == "inner" else "outer"].append(LineString(_line(m["geometry"])))
    outer = list(polygonize(unary_union(rings["outer"]))) if rings["outer"] else []
    if not outer:
        return None
    area = unary_union(outer)
    inner = list(polygonize(unary_union(rings["inner"]))) if rings["inner"] else []
    if inner:
        area = area.difference(unary_union(inner))
    return _polygons(area)


def to_features(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for el in elements:
        osm_id = f"{el['type']}/{el['id']}"
        if el["type"] == "way":
            geom = way_geometry(el)
        elif el["type"] == "relation":
            geom = relation_geometry(el)
        else:
            geom = None  # a park mapped as a single node has no outline
        if geom is None:
            print(f"  skipped {osm_id}: no closed outline", file=sys.stderr)
            continue
        name = (el.get("tags") or {}).get("name")
        features.append({
            "type": "Feature",
            "properties": {"osm_id": osm_id, "name": name},
            "geometry": mapping(geom),
        })
    return sorted(features, key=lambda f: f["properties"]["osm_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    elements = fetch()
    features = to_features(elements)
    collection = {
        "type": "FeatureCollection",
        "source": "OpenStreetMap leisure=park within the Viladecans boundary, via the Overpass API",
        "license": "© OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright)",
        "fetched": date.today().isoformat(),
        "features": features,
    }
    args.out.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    print(f"{len(features)} parks ({len(elements)} OSM elements) written to {args.out}")


if __name__ == "__main__":
    main()
