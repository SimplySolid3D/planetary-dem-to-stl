"""Ground geometry: a local azimuthal equidistant grid on a sphere.

The model is laid out on a flat x/y grid in metres centred on the chosen
point. Every grid node is mapped back to latitude/longitude with the inverse
azimuthal equidistant projection, so the box is square on the ground at any
latitude (an equirectangular lat/lon box would be squeezed east-west by
cos(latitude)). Distances from the centre are exact; across the box the scale
error stays below MAX_SCALE_ERROR, which is why box size is capped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: Boxes may not reach beyond this latitude. The source grids are
#: equirectangular, so near a pole a small box needs nearly whole image rows
#: and wraps around the pole; that case is not handled.
MAX_ABS_LAT = 80.0

#: Largest angular distance (radians) from the centre to a box corner. At
#: 0.35 rad the azimuthal equidistant projection stretches distances across
#: the azimuth by c/sin(c) - 1 = 2.1 %. Moon: ~860 km box; Mars: ~1680 km.
MAX_CORNER_ANGLE = 0.35


class BoxError(ValueError):
    """The requested box cannot be built (too big, too polar, malformed)."""


@dataclass(frozen=True)
class Box:
    lat: float
    lon: float
    width_m: float  # east-west ground size
    height_m: float  # north-south ground size

    @classmethod
    def from_centre(cls, lat: float, lon: float, size_km: float, height_km: float | None = None) -> "Box":
        if size_km <= 0 or (height_km is not None and height_km <= 0):
            raise BoxError("size must be positive")
        h = size_km if height_km is None else height_km
        return cls(float(lat), float(lon), size_km * 1000.0, h * 1000.0)

    @classmethod
    def from_bbox(cls, west: float, south: float, east: float, north: float, radius_m: float) -> "Box":
        """The ground rectangle of the same size, centred on the bbox middle.

        Width is measured along the middle latitude. Corners therefore differ a
        little from the lat/lon corners you typed, more so at high latitude.
        """
        if not south < north:
            raise BoxError("bbox needs south < north")
        span = (east - west) % 360.0
        if span == 0:
            raise BoxError("bbox needs west != east")
        lat_c = (south + north) / 2.0
        lon_c = _wrap_lon(west + span / 2.0)
        rad = math.pi / 180.0
        width = span * rad * radius_m * math.cos(lat_c * rad)
        height = (north - south) * rad * radius_m
        return cls(lat_c, lon_c, width, height)


def _wrap_lon(lon):
    return (np.asarray(lon) + 180.0) % 360.0 - 180.0


def check_box(box: Box, radius_m: float) -> None:
    if not -90 <= box.lat <= 90:
        raise BoxError("latitude must be between -90 and 90")
    corner = math.hypot(box.width_m, box.height_m) / 2.0 / radius_m
    if corner > MAX_CORNER_ANGLE:
        limit_km = 2 * MAX_CORNER_ANGLE * radius_m / math.sqrt(2) / 1000.0
        raise BoxError(
            f"box too large: keep it under about {limit_km:.0f} km across on this world "
            f"(beyond that a flat model distorts the surface by more than 2 %)"
        )
    # Polar check on the box outline (its extreme latitudes lie on the edges).
    lat, _ = inverse_aeqd(*outline_xy(box), box.lat, box.lon, radius_m)
    if np.nanmax(np.abs(lat)) > MAX_ABS_LAT or abs(box.lat) > MAX_ABS_LAT:
        raise BoxError(
            f"box reaches beyond {MAX_ABS_LAT:.0f} degrees latitude; polar regions are not "
            f"supported (the source grids are equirectangular and wrap at the poles)"
        )


def outline_xy(box: Box, n: int = 64):
    hw, hh = box.width_m / 2.0, box.height_m / 2.0
    t = np.linspace(-1.0, 1.0, n)
    x = np.concatenate([t * hw, np.full(n, hw), -t * hw, np.full(n, -hw)])
    y = np.concatenate([np.full(n, -hh), t * hh, np.full(n, hh), -t * hh])
    return x, y


def inverse_aeqd(x, y, lat0: float, lon0: float, radius_m: float):
    """Spherical inverse azimuthal equidistant: metres -> degrees."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    phi0 = math.radians(lat0)
    rho = np.hypot(x, y)
    c = rho / radius_m
    sin_c, cos_c = np.sin(c), np.cos(c)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(rho > 0, y * sin_c / np.where(rho > 0, rho, 1.0), 0.0)
    lat = np.arcsin(np.clip(cos_c * math.sin(phi0) + ratio * math.cos(phi0), -1.0, 1.0))
    lon = math.radians(lon0) + np.arctan2(x * sin_c, rho * math.cos(phi0) * cos_c - y * math.sin(phi0) * sin_c)
    lon = np.where(rho > 0, lon, math.radians(lon0))
    return np.degrees(lat), _wrap_lon(np.degrees(lon))


def forward_aeqd(lat, lon, lat0: float, lon0: float, radius_m: float):
    """Spherical azimuthal equidistant: degrees -> metres (used in tests)."""
    phi, lam = np.radians(lat), np.radians(lon)
    phi0, lam0 = math.radians(lat0), math.radians(lon0)
    cos_c = np.sin(phi0) * np.sin(phi) + np.cos(phi0) * np.cos(phi) * np.cos(lam - lam0)
    c = np.arccos(np.clip(cos_c, -1.0, 1.0))
    k = np.where(c > 0, c / np.where(c > 0, np.sin(c), 1.0), 1.0)
    x = radius_m * k * np.cos(phi) * np.sin(lam - lam0)
    y = radius_m * k * (np.cos(phi0) * np.sin(phi) - np.sin(phi0) * np.cos(phi) * np.cos(lam - lam0))
    return x, y


def grid_xy(box: Box, nx: int, ny: int):
    """Grid node coordinates (metres), row 0 = south edge, column 0 = west edge."""
    xs = np.linspace(-box.width_m / 2.0, box.width_m / 2.0, nx)
    ys = np.linspace(-box.height_m / 2.0, box.height_m / 2.0, ny)
    return np.meshgrid(xs, ys)
