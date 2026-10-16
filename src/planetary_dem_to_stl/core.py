"""Sample a world's elevation on a local grid and turn it into a solid."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .geo import Box, check_box, grid_xy, inverse_aeqd
from .mesh import Mesh, heightmap_to_solid
from .tiff import StripTiff, TiffError
from .worlds import World

MAX_SAMPLES_PER_SIDE = 2000


@dataclass
class Model:
    mesh: Mesh
    world: World
    box: Box
    width_mm: float
    depth_mm: float
    exaggeration: float
    base_mm: float
    mm_per_m: float
    elevation_min_m: float
    elevation_max_m: float
    grid_shape: tuple[int, int]
    notes: list[str] = field(default_factory=list)

    @property
    def relief_mm(self) -> float:
        return (self.elevation_max_m - self.elevation_min_m) * self.mm_per_m * self.exaggeration


def grid_size(box: Box, width_mm: float, resolution_mm: float, metres_per_px: float | None = None):
    """Samples along x and y: one per `resolution_mm`, never finer than the data."""
    depth_mm = width_mm * box.height_m / box.width_m
    step_mm = resolution_mm
    if metres_per_px:
        step_mm = max(step_mm, metres_per_px * width_mm / box.width_m)
    nx = int(round(width_mm / step_mm)) + 1
    ny = int(round(depth_mm / step_mm)) + 1
    scale = min(1.0, MAX_SAMPLES_PER_SIDE / max(nx, ny))
    nx = max(2, int(nx * scale))
    ny = max(2, int(ny * scale))
    return nx, ny, depth_mm


def heights_to_model(
    elevation_m: np.ndarray,
    box: Box,
    world: World,
    width_mm: float,
    exaggeration: float = 1.0,
    base_mm: float = 2.0,
    notes: list[str] | None = None,
) -> Model:
    """Turn an elevation grid (metres, row 0 = south) into the solid.

    True scale: 1 m on the ground = width_mm / box.width_m millimetres, in all
    three axes when exaggeration is 1.
    """
    if width_mm <= 0:
        raise ValueError("width must be positive")
    if exaggeration <= 0:
        raise ValueError("exaggeration must be positive")
    if base_mm <= 0:
        raise ValueError("base thickness must be positive (the model needs a floor)")
    elevation_m = np.asarray(elevation_m, dtype=np.float64)
    mm_per_m = width_mm / box.width_m
    depth_mm = width_mm * box.height_m / box.width_m
    lo, hi = float(np.min(elevation_m)), float(np.max(elevation_m))
    z = base_mm + (elevation_m - lo) * mm_per_m * exaggeration
    mesh = heightmap_to_solid(z, width_mm, depth_mm)
    return Model(
        mesh=mesh,
        world=world,
        box=box,
        width_mm=width_mm,
        depth_mm=depth_mm,
        exaggeration=exaggeration,
        base_mm=base_mm,
        mm_per_m=mm_per_m,
        elevation_min_m=lo,
        elevation_max_m=hi,
        grid_shape=elevation_m.shape,
        notes=list(notes or []),
    )


def sample_elevation(world: World, box: Box, nx: int, ny: int, dem: str | None = None, workers: int = 16, progress=None):
    """Elevation in metres on an (ny, nx) grid over the box, bilinear from the DEM."""
    check_box(box, world.radius_m)
    gx, gy = grid_xy(box, nx, ny)
    lat, lon = inverse_aeqd(gx, gy, box.lat, box.lon, world.radius_m)

    tif = StripTiff(dem or world.dem_url, workers=workers)
    if (tif.width, tif.height) != (world.width_px, world.height_px):
        raise TiffError(
            f"{dem or world.dem_url} is {tif.width}x{tif.height} px, expected "
            f"{world.width_px}x{world.height_px} for the {world.name} grid"
        )

    dpp = world.deg_per_px
    # Fractional pixel coordinates, pixel centres at integer + 0.5 offsets.
    col = (lon + 180.0) / dpp - 0.5
    row = (90.0 - lat) / dpp - 0.5
    # Unwrap columns across the antimeridian so the span is contiguous.
    if col.max() - col.min() > tif.width / 2:
        col = np.where(col < tif.width / 2, col + tif.width, col)
    c0 = int(math.floor(col.min()))
    c1 = int(math.floor(col.max())) + 1
    r0 = max(0, int(math.floor(row.min())))
    r1 = min(tif.height - 1, int(math.floor(row.max())) + 1)

    # Fetch every row only if the output is that fine; otherwise skip rows.
    stride = max(1, (r1 - r0) // max(1, 2 * ny))
    rows = list(range(r0, r1 + 1, stride))
    if rows[-1] != r1:
        rows.append(r1)
    if progress:
        progress(f"reading {len(rows)} rows x {c1 - c0 + 1} columns of {world.name} elevation")
    block = tif.read_rows(rows, c0, c1 - c0 + 1)

    raw_nodata = block == world.nodata
    block = block * world.scale
    notes = []
    if raw_nodata.any():
        block[raw_nodata] = np.nan
        notes.append(f"{int(raw_nodata.sum())} no-data pixels were filled with the lowest valid height")
        block = np.where(np.isnan(block), np.nanmin(block), block)

    # Bilinear interpolation on the fetched (row-strided) block.
    rows_arr = np.asarray(rows, dtype=np.float64)
    ri = np.interp(np.clip(row, rows_arr[0], rows_arr[-1]), rows_arr, np.arange(len(rows_arr)))
    ci = np.clip(col - c0, 0, block.shape[1] - 1)
    r_lo = np.clip(np.floor(ri).astype(int), 0, block.shape[0] - 2 if block.shape[0] > 1 else 0)
    c_lo = np.clip(np.floor(ci).astype(int), 0, block.shape[1] - 2 if block.shape[1] > 1 else 0)
    fr = ri - r_lo
    fc = ci - c_lo
    r_hi = np.minimum(r_lo + 1, block.shape[0] - 1)
    c_hi = np.minimum(c_lo + 1, block.shape[1] - 1)
    v = (
        block[r_lo, c_lo] * (1 - fr) * (1 - fc)
        + block[r_lo, c_hi] * (1 - fr) * fc
        + block[r_hi, c_lo] * fr * (1 - fc)
        + block[r_hi, c_hi] * fr * fc
    )
    source = getattr(tif.source, "requests", None)
    if source is not None:
        notes.append(f"downloaded {tif.source.bytes / 1e6:.1f} MB in {tif.source.requests} range requests")
    return v, notes


def build_model(
    world: World,
    box: Box,
    width_mm: float = 100.0,
    exaggeration: float = 1.0,
    base_mm: float = 2.0,
    resolution_mm: float = 0.25,
    dem: str | None = None,
    workers: int = 16,
    progress=None,
) -> Model:
    if resolution_mm <= 0:
        raise ValueError("resolution must be positive")
    check_box(box, world.radius_m)
    nx, ny, _ = grid_size(box, width_mm, resolution_mm, world.metres_per_px)
    elevation, notes = sample_elevation(world, box, nx, ny, dem=dem, workers=workers, progress=progress)
    return heights_to_model(elevation, box, world, width_mm, exaggeration, base_mm, notes)
