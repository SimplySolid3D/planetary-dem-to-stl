import numpy as np
import pytest
import trimesh

from planetary_dem_to_stl import cli

from synthetic import analytic_field, global_grid, synthetic_world, write_strip_tiff


@pytest.mark.parametrize(
    "argv",
    [
        [],  # no world
        ["venus", "--lat", "0", "--lon", "0", "--size-km", "10", "-o", "x.stl"],
        ["moon", "--lat", "0", "--lon", "0", "--size-km", "10"],  # no output
        ["moon", "--lat", "0", "--lon", "0", "-o", "x.stl"],  # no size
        ["moon", "--lat", "95", "--lon", "0", "--size-km", "10", "-o", "x.stl"],
        ["moon", "--lat", "0", "--lon", "0", "--size-km", "-5", "-o", "x.stl"],
        ["moon", "--lat", "0", "--lon", "0", "--size-km", "10", "--width-mm", "0", "-o", "x.stl"],
        ["moon", "--lat", "0", "--lon", "0", "--size-km", "10", "--exaggeration", "abc", "-o", "x.stl"],
        ["moon", "--bbox", "0", "0", "1", "1", "--lat", "0", "-o", "x.stl"],  # both forms
        ["moon", "--bbox", "0", "5", "1", "1", "-o", "x.stl"],  # south > north
        ["moon", "--bbox", "0", "0", "1", "-o", "x.stl"],  # three numbers
        ["moon", "--lat", "0", "--lon", "0", "--size-km", "10", "--workers", "0", "-o", "x.stl"],
    ],
)
def test_bad_arguments_exit_with_usage_error(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2


def test_polar_box_is_refused_with_message(capsys, tmp_path):
    code = cli.main(["moon", "--lat", "-88", "--lon", "0", "--size-km", "20", "-o", str(tmp_path / "p.stl")])
    assert code == 2
    assert "polar" in capsys.readouterr().err
    assert not (tmp_path / "p.stl").exists()


def test_too_large_box_is_refused(capsys, tmp_path):
    code = cli.main(["moon", "--lat", "0", "--lon", "0", "--size-km", "2000", "-o", str(tmp_path / "p.stl")])
    assert code == 2
    assert "too large" in capsys.readouterr().err


def test_cli_writes_stl_from_local_dem(tmp_path, monkeypatch, capsys):
    world = synthetic_world()
    glat, glon = global_grid(world)
    dem = tmp_path / "g.tif"
    write_strip_tiff(dem, np.round(analytic_field(glat, glon) / world.scale).astype(np.int16))
    monkeypatch.setattr(cli, "get_world", lambda name: world)
    out = tmp_path / "m.stl"
    code = cli.main(
        ["moon", "--bbox", "10", "10", "14", "13", "--width-mm", "80", "--base-mm", "2.5",
         "--resolution-mm", "1", "--dem", str(dem), "-o", str(out)]
    )
    assert code == 0
    tm = trimesh.load(out, force="mesh")
    assert tm.is_watertight
    assert tm.extents[0] == pytest.approx(80, abs=1e-3)
    assert "wrote" in capsys.readouterr().err
