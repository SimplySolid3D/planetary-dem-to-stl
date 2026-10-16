import math

import numpy as np
import pytest

from planetary_dem_to_stl import MARS, MOON, Box, BoxError
from planetary_dem_to_stl.geo import check_box, forward_aeqd, inverse_aeqd


@pytest.mark.parametrize("lat0,lon0", [(0, 0), (-43.3, -11.4), (60, 179.5), (18.65, -133.8)])
def test_inverse_then_forward_round_trips(lat0, lon0):
    x = np.linspace(-200e3, 200e3, 9)
    y = np.linspace(-150e3, 150e3, 7)
    gx, gy = np.meshgrid(x, y)
    lat, lon = inverse_aeqd(gx, gy, lat0, lon0, MOON.radius_m)
    bx, by = forward_aeqd(lat, lon, lat0, lon0, MOON.radius_m)
    assert np.allclose(bx, gx, atol=1e-3)
    assert np.allclose(by, gy, atol=1e-3)


def _great_circle_m(lat1, lon1, lat2, lon2, radius_m):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(a))


def test_box_is_square_on_the_ground_at_high_latitude():
    # At 70 N a box that is 100 km wide on the ground spans ~1/cos(70) = 2.9x
    # more longitude than at the equator, and both edges measure 100 km.
    for lat0 in (0.0, 70.0):
        lat, lon = inverse_aeqd(np.array([-50e3, 50e3, 0, 0]), np.array([0, 0, -50e3, 50e3]), lat0, 0, MOON.radius_m)
        ew = _great_circle_m(lat[0], lon[0], lat[1], lon[1], MOON.radius_m)
        ns = _great_circle_m(lat[2], lon[2], lat[3], lon[3], MOON.radius_m)
        assert ew == pytest.approx(100e3, rel=1e-9)
        assert ns == pytest.approx(100e3, rel=1e-9)
    _, lon_eq = inverse_aeqd(np.array([-50e3, 50e3]), np.array([0, 0]), 0, 0, MOON.radius_m)
    _, lon_70 = inverse_aeqd(np.array([-50e3, 50e3]), np.array([0, 0]), 70, 0, MOON.radius_m)
    ratio = (lon_70[1] - lon_70[0]) / (lon_eq[1] - lon_eq[0])
    assert ratio == pytest.approx(1 / math.cos(math.radians(70)), rel=0.01)


def test_refuses_polar_boxes():
    with pytest.raises(BoxError, match="latitude"):
        check_box(Box.from_centre(85, 0, 10), MOON.radius_m)
    with pytest.raises(BoxError, match="latitude"):
        # centre is fine but the box reaches past 80 N
        check_box(Box.from_centre(79.5, 0, 60), MOON.radius_m)
    check_box(Box.from_centre(75, 0, 60), MOON.radius_m)


def test_refuses_huge_boxes():
    with pytest.raises(BoxError, match="too large"):
        check_box(Box.from_centre(0, 0, 1500), MOON.radius_m)
    check_box(Box.from_centre(0, 0, 1500), MARS.radius_m)


def test_bbox_conversion():
    b = Box.from_bbox(-12, 8, -8, 12, MOON.radius_m)
    assert b.lat == pytest.approx(10)
    assert b.lon == pytest.approx(-10)
    deg = math.pi / 180 * MOON.radius_m
    assert b.height_m == pytest.approx(4 * deg)
    assert b.width_m == pytest.approx(4 * deg * math.cos(math.radians(10)))


def test_bbox_across_antimeridian():
    b = Box.from_bbox(178, -1, -178, 1, MOON.radius_m)
    assert abs(b.lon) == pytest.approx(180)
    assert b.width_m == pytest.approx(4 * math.pi / 180 * MOON.radius_m * math.cos(0), rel=1e-6)
