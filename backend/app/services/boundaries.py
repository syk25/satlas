import json
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import unary_union

_DATA_DIR = Path(__file__).parents[2] / "data"

# Loaded once at startup: {ISO-A2 -> Shapely geometry}
_country_polygons: dict = {}


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


def is_over_country(lat: float, lon: float, country_code: str) -> bool:
    polygon = _country_polygons.get(country_code.upper())
    if polygon is None:
        return False
    return polygon.contains(Point(lon, lat))


def country_exists(country_code: str) -> bool:
    return country_code.upper() in _country_polygons
