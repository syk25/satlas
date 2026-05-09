import json
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

_DATA_DIR = Path(__file__).parents[2] / "data"

# Loaded once at startup: {ISO-A2 -> Shapely geometry}
_country_polygons: dict = {}

# Hot-path lookup tables for repeated point-in-polygon checks (ADR-018/019).
# Populated lazily on first access to avoid paying the cost on startup for
# countries that may never be queried.
_country_bounds: dict = {}  # ISO-A2 -> (minx, miny, maxx, maxy)
_country_prepared: dict = {}  # ISO-A2 -> shapely PreparedGeometry


def load_country_polygons() -> None:
    geojson_path = _DATA_DIR / "ne_50m_admin_0_countries.geojson"
    with open(geojson_path) as f:
        data = json.load(f)

    for feature in data["features"]:
        props = feature["properties"]
        iso_a2 = props.get("ISO_A2") or props.get("iso_a2", "")
        if not iso_a2 or iso_a2 == "-99":
            continue
        iso_a2 = iso_a2.upper()
        geom = shape(feature["geometry"])
        if iso_a2 in _country_polygons:
            _country_polygons[iso_a2] = unary_union([_country_polygons[iso_a2], geom])
        else:
            _country_polygons[iso_a2] = geom

    # Force-reset memoized accelerators if reload happens (e.g. tests).
    _country_bounds.clear()
    _country_prepared.clear()


def _accelerators(country_code: str):
    """Return (bounds, prepared) for country, building once and caching.

    Bounds give an O(1) bbox reject; prepared geometry gives an O(1)–O(log n)
    contains check that is 10–100× faster than `polygon.contains` on complex
    multi-polygons (US, RU, CA).
    """
    cc = country_code.upper()
    bounds = _country_bounds.get(cc)
    if bounds is None:
        polygon = _country_polygons.get(cc)
        if polygon is None:
            return None, None
        bounds = polygon.bounds
        _country_bounds[cc] = bounds
        _country_prepared[cc] = prep(polygon)
    return bounds, _country_prepared[cc]


def is_over_country(lat: float, lon: float, country_code: str) -> bool:
    bounds, prepared = _accelerators(country_code)
    if bounds is None:
        return False
    minx, miny, maxx, maxy = bounds
    if lon < minx or lon > maxx or lat < miny or lat > maxy:
        return False
    return prepared.contains(Point(lon, lat))


def country_exists(country_code: str) -> bool:
    return country_code.upper() in _country_polygons
