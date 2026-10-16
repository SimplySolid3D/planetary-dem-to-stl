import numpy as np
import pytest
import trimesh

from planetary_dem_to_stl import Box, build_model, write_stl
from planetary_dem_to_stl.core import sample_elevation
from planetary_dem_to_stl.geo import grid_xy, inverse_aeqd
from planetary_dem_to_stl.tiff import StripTiff, TiffError

from synthetic import analytic_field, global_grid, synthetic_world, write_strip_tiff


@pytest.mark.parametrize("rows_per_strip", [1, 7])
def test_reader_returns_exact_pixels(tmp_path, rows_per_strip):
    data = (np.arange(40 * 30).reshape(30, 40) - 600).astype(np.int16)
    path = tmp_path / "t.tif"
    write_strip_tiff(path, data, rows_per_strip=rows_per_strip)
    tif = StripTiff(str(path))
    assert (tif.width, tif.height) == (40, 30)
    got = tif.read_rows([3, 4, 10, 29], 5, 12)
    assert np.array_equal(got, data[[3, 4, 10, 29], 5:17])


def test_reader_wraps_columns(tmp_path):
    data = np.arange(10 * 6, dtype=np.int16).reshape(6, 10)
    path = tmp_path / "t.tif"
    write_strip_tiff(path, data)
    got = StripTiff(str(path)).read_rows([2], 8, 5)
    assert got[0].tolist() == [28, 29, 20, 21, 22]


def test_reader_refuses_non_tiff(tmp_path):
    path = tmp_path / "x.tif"
    path.write_bytes(b"not a tiff at all")
    with pytest.raises(TiffError):
        StripTiff(str(path))


@pytest.fixture
def world_and_dem(tmp_path):
    world = synthetic_world()
    glat, glon = global_grid(world)
    raw = np.round(analytic_field(glat, glon) / world.scale).astype(np.int16)
    path = tmp_path / "global.tif"
    write_strip_tiff(path, raw)
    return world, str(path)


@pytest.mark.parametrize("lat,lon", [(10, 20), (-55, -100), (0, 179.9)])
def test_sampling_matches_the_field(world_and_dem, lat, lon):
    world, dem = world_and_dem
    box = Box.from_centre(lat, lon, 400)  # radius 1000 km: corner 0.28 rad
    nx, ny = 25, 25
    elev, _ = sample_elevation(world, box, nx, ny, dem=dem, workers=4)
    gx, gy = grid_xy(box, nx, ny)
    glat, glon = inverse_aeqd(gx, gy, lat, lon, world.radius_m)
    expected = analytic_field(glat, glon)
    # bilinear on a 0.5 degree grid of a smooth field: within a few metres
    assert np.max(np.abs(elev - expected)) < 15.0


def test_build_model_end_to_end(world_and_dem, tmp_path):
    world, dem = world_and_dem
    box = Box.from_centre(30, 45, 300)
    model = build_model(world, box, width_mm=60, exaggeration=2, base_mm=3, resolution_mm=1.0, dem=dem)
    path = tmp_path / "out.stl"
    write_stl(model.mesh, path)
    tm = trimesh.load(path, force="mesh")
    assert tm.is_watertight and tm.volume > 0
    sx, sy, sz = tm.extents
    assert sx == pytest.approx(60, abs=1e-3) and sy == pytest.approx(60, abs=1e-3)
    assert sz == pytest.approx(3 + model.relief_mm, abs=1e-3)
    assert model.relief_mm == pytest.approx(
        (model.elevation_max_m - model.elevation_min_m) * 60 / 300_000 * 2
    )


def test_wrong_size_dem_is_refused(world_and_dem, tmp_path):
    world, _ = world_and_dem
    small = tmp_path / "small.tif"
    write_strip_tiff(small, np.zeros((10, 20), dtype=np.int16))
    with pytest.raises(TiffError, match="expected"):
        sample_elevation(world, Box.from_centre(0, 0, 50), 5, 5, dem=str(small))
