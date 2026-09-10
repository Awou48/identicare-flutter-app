"""Geo helpers. GeoJSON coordinates are always [longitude, latitude]."""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: list[float] | tuple[float, float], b: list[float] | tuple[float, float]) -> float:
    """Great-circle distance between two [lng, lat] points."""
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def implied_speed_kmh(distance_km: float, minutes: float) -> float:
    """Speed needed to cover the distance in the elapsed time.

    Guards against a divide-by-zero when two claims land in the same minute: that
    case is infinitely fast, which is precisely the fraud signal, so it returns
    infinity rather than crashing or silently reporting 0.
    """
    if minutes <= 0:
        return float("inf") if distance_km > 0 else 0.0
    return distance_km / (minutes / 60.0)
