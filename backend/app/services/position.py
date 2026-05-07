import math
from datetime import datetime, timezone

from sgp4.api import Satrec, jday


def _eci_to_geodetic(r: tuple, dt: datetime) -> tuple[float, float, float]:
    """Convert ECI position vector (km) to (lat_deg, lon_deg, alt_km).

    Uses Greenwich Apparent Sidereal Time to rotate ECI → ECEF,
    then iterative Bowring method for ECEF → geodetic.
    """
    x, y, z = r

    # Greenwich Sidereal Time (degrees)
    J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_days = (dt - J2000).total_seconds() / 86400.0
    gst_deg = (280.46061837 + 360.98564736629 * t_days) % 360
    gst_rad = math.radians(gst_deg)

    # Rotate ECI → ECEF
    x_e = x * math.cos(gst_rad) + y * math.sin(gst_rad)
    y_e = -x * math.sin(gst_rad) + y * math.cos(gst_rad)
    z_e = z

    # WGS-84 ellipsoid constants
    a = 6378.137  # km
    f = 1 / 298.257223563
    e2 = 2 * f - f**2

    p = math.sqrt(x_e**2 + y_e**2)
    lon = math.degrees(math.atan2(y_e, x_e))

    # Iterative geodetic latitude
    lat = math.degrees(math.atan2(z_e, p * (1 - e2)))
    for _ in range(5):
        sin_lat = math.sin(math.radians(lat))
        N = a / math.sqrt(1 - e2 * sin_lat**2)
        lat = math.degrees(math.atan2(z_e + e2 * N * sin_lat, p))

    sin_lat = math.sin(math.radians(lat))
    cos_lat = math.cos(math.radians(lat))
    N = a / math.sqrt(1 - e2 * sin_lat**2)
    if abs(cos_lat) > 1e-10:
        alt = p / cos_lat - N
    else:
        alt = abs(z_e) / abs(sin_lat) - N * (1 - e2)

    return lat, lon, alt


def get_position(
    line1: str, line2: str, at: datetime | None = None
) -> tuple[float, float, float] | None:
    """Return (lat_deg, lon_deg, alt_km) for a satellite at the given time.

    Returns None if SGP4 propagation fails (e.g. decayed orbit).
    """
    if at is None:
        at = datetime.now(timezone.utc)

    sat = Satrec.twoline2rv(line1, line2)
    jd, fr = jday(at.year, at.month, at.day, at.hour, at.minute, at.second)
    error, r, _ = sat.sgp4(jd, fr)

    if error != 0:
        return None

    return _eci_to_geodetic(r, at)
