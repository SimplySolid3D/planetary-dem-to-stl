"""Helpers: write a small global int16 GeoTIFF the reader understands."""

import struct

import numpy as np

from planetary_dem_to_stl import World


def write_strip_tiff(path, data: np.ndarray, rows_per_strip: int = 1, nodata_tag: bool = True) -> None:
    """Uncompressed little-endian classic TIFF, int16, single band, strips."""
    data = np.ascontiguousarray(data, dtype="<i2")
    h, w = data.shape
    n_strips = -(-h // rows_per_strip)
    pixel_start = 8
    pixels = data.tobytes()
    offsets = [pixel_start + s * rows_per_strip * w * 2 for s in range(n_strips)]
    counts = [min(rows_per_strip, h - s * rows_per_strip) * w * 2 for s in range(n_strips)]
    extra = pixel_start + len(pixels)
    off_ptr = extra
    cnt_ptr = off_ptr + 4 * n_strips
    ifd = cnt_ptr + 4 * n_strips
    entries = [
        (256, 4, 1, w),
        (257, 4, 1, h),
        (258, 3, 1, 16),
        (259, 3, 1, 1),
        (262, 3, 1, 1),
        (273, 4, n_strips, off_ptr if n_strips > 1 else offsets[0]),
        (277, 3, 1, 1),
        (278, 4, 1, rows_per_strip),
        (279, 4, n_strips, cnt_ptr if n_strips > 1 else counts[0]),
        (339, 3, 1, 2),
    ]
    out = bytearray(b"II" + struct.pack("<HI", 42, ifd))
    out += pixels
    out += struct.pack(f"<{n_strips}I", *offsets)
    out += struct.pack(f"<{n_strips}I", *counts)
    out += struct.pack("<H", len(entries))
    for tag, typ, n, value in entries:
        if typ == 3 and n == 1:
            out += struct.pack("<HHIHH", tag, typ, n, value, 0)
        else:
            out += struct.pack("<HHII", tag, typ, n, value)
    out += struct.pack("<I", 0)
    with open(path, "wb") as fh:
        fh.write(out)


def synthetic_world(width=720, height=360, radius_m=1_000_000.0, scale=0.5) -> World:
    return World(
        name="testworld",
        radius_m=radius_m,
        dem_url="unused",
        width_px=width,
        height_px=height,
        scale=scale,
        nodata=-32768,
        credit="synthetic",
        product_page="",
    )


def analytic_field(lat, lon):
    """Smooth elevation in metres, a function of position on the sphere."""
    return 800.0 * np.sin(np.radians(lat) * 3) + 600.0 * np.cos(np.radians(lon) * 2)


def global_grid(world: World):
    dpp = world.deg_per_px
    lat = 90.0 - (np.arange(world.height_px) + 0.5) * dpp
    lon = -180.0 + (np.arange(world.width_px) + 0.5) * dpp
    glon, glat = np.meshgrid(lon, lat)
    return glat, glon
