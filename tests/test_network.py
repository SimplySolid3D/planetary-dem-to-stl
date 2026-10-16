"""Downloads a few MB of real data. Run with: pytest --network"""

import pytest
import trimesh

from planetary_dem_to_stl import cli


@pytest.mark.network
def test_tycho_from_the_real_lola_dem(tmp_path):
    out = tmp_path / "tycho.stl"
    code = cli.main(
        ["moon", "--lat", "-43.31", "--lon", "-11.36", "--size-km", "100",
         "--width-mm", "50", "--resolution-mm", "0.5", "-o", str(out)]
    )
    assert code == 0
    tm = trimesh.load(out, force="mesh")
    assert tm.is_watertight and tm.volume > 0
    assert tm.extents[0] == pytest.approx(50, abs=1e-3)
    # Tycho is roughly 4.5-5 km deep; at 100 km -> 50 mm, 1 km = 0.5 mm.
    relief_mm = tm.extents[2] - 2.0
    assert 1.5 < relief_mm < 4.0
