import numpy as np
import pytest
import trimesh

from planetary_dem_to_stl import MOON, Box, heights_to_model, heightmap_to_solid, write_stl


def _load(mesh, tmp_path):
    path = tmp_path / "m.stl"
    write_stl(mesh, path, header="test")
    return trimesh.load(path, force="mesh"), path


def _bumpy(ny=40, nx=60):
    y, x = np.mgrid[0:ny, 0:nx]
    return 3.0 + np.sin(x / 5.0) + np.cos(y / 7.0)


def test_solid_is_watertight_with_outward_normals(tmp_path):
    mesh = heightmap_to_solid(_bumpy(), 60.0, 40.0)
    tm, _ = _load(mesh, tmp_path)
    assert tm.is_watertight
    assert tm.is_winding_consistent
    assert tm.volume > 0  # positive volume = normals point outwards
    assert tm.euler_number == 2  # one closed surface, no holes


def test_volume_matches_heightmap(tmp_path):
    z = np.full((11, 21), 5.0)
    mesh = heightmap_to_solid(z, 20.0, 10.0)
    tm, _ = _load(mesh, tmp_path)
    assert tm.volume == pytest.approx(20.0 * 10.0 * 5.0, rel=1e-6)


def test_binary_stl_layout(tmp_path):
    mesh = heightmap_to_solid(_bumpy(5, 6), 10.0, 8.0)
    _, path = _load(mesh, tmp_path)
    data = path.read_bytes()
    n = int.from_bytes(data[80:84], "little")
    assert n == len(mesh.faces)
    assert len(data) == 84 + 50 * n
    assert not data[:5].lower().startswith(b"solid")


def test_rejects_heights_at_or_below_floor():
    with pytest.raises(ValueError):
        heightmap_to_solid(np.zeros((3, 3)), 1, 1)


def _model(elev, width_km=10.0, height_km=None, **kw):
    box = Box.from_centre(0, 0, width_km, height_km)
    return heights_to_model(elev, box, MOON, **kw)


def test_dimensions_in_mm():
    elev = np.zeros((31, 51))
    elev[15, 25] = 500.0
    m = _model(elev, width_km=20, height_km=12, width_mm=150.0, base_mm=3.0)
    sx, sy, sz = m.mesh.size_mm
    assert sx == pytest.approx(150.0)
    assert sy == pytest.approx(150.0 * 12 / 20)
    assert m.mesh.bounds[0].tolist() == pytest.approx([0, 0, 0])


def test_base_thickness_is_below_lowest_point():
    elev = 1000.0 + 200.0 * np.random.default_rng(1).random((20, 20))
    m = _model(elev, base_mm=4.5, width_mm=80)
    top = m.mesh.vertices[m.mesh.vertices[:, 2] > 0]
    assert top[:, 2].min() == pytest.approx(4.5)


def test_true_scale_height():
    # A 1000 m bump on a 10 km wide box printed 100 mm wide: 1 m = 0.01 mm,
    # so the bump stands 10 mm above the base at 1x and 30 mm at 3x.
    elev = np.zeros((21, 21))
    elev[10, 10] = 1000.0
    for exaggeration in (1.0, 3.0):
        m = _model(elev, width_km=10, width_mm=100.0, base_mm=2.0, exaggeration=exaggeration)
        assert m.mm_per_m == pytest.approx(0.01)
        assert m.mesh.size_mm[2] == pytest.approx(2.0 + 10.0 * exaggeration)
        assert m.relief_mm == pytest.approx(10.0 * exaggeration)


def test_negative_elevations_are_fine(tmp_path):
    elev = -4000.0 + 50.0 * _bumpy()
    m = _model(elev, width_mm=50)
    tm, _ = _load(m.mesh, tmp_path)
    assert tm.is_watertight and tm.volume > 0
