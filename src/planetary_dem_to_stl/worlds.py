"""The worlds this tool knows, and the public elevation grid each one reads.

Both grids are global, simple-cylindrical (equirectangular) GeoTIFFs published
by the USGS Astrogeology Science Center. They are uncompressed, signed 16-bit,
one image row per TIFF strip, which is what lets us fetch just the bytes a box
needs with HTTP range requests. See DATA.md for licences and citations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class World:
    name: str
    #: Radius of the reference sphere the grid is drawn on, in metres.
    radius_m: float
    #: Where the GeoTIFF lives. The planetarymaps address redirects to S3.
    dem_url: str
    #: Expected raster size; the reader refuses a file that does not match.
    width_px: int
    height_px: int
    #: Stored value * scale = metres above the reference datum.
    scale: float
    nodata: int
    #: Short credit line printed by the CLI and written into the STL header.
    credit: str
    product_page: str

    @property
    def deg_per_px(self) -> float:
        return 360.0 / self.width_px

    @property
    def metres_per_px(self) -> float:
        import math

        return 2 * math.pi * self.radius_m / self.width_px


MOON = World(
    name="moon",
    radius_m=1_737_400.0,
    dem_url="https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif",
    width_px=92_160,
    height_px=46_080,
    scale=0.5,
    nodata=-32_768,
    credit="Moon LRO LOLA DEM 118m, LOLA Science Team / NASA GSFC, via USGS Astrogeology (public domain)",
    product_page="https://astrogeology.usgs.gov/search/map/moon_lro_lola_dem_118m",
)

MARS = World(
    name="mars",
    radius_m=3_396_190.0,
    dem_url="https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif",
    width_px=46_080,
    height_px=23_040,
    scale=1.0,
    nodata=-32_768,
    credit="Mars MGS MOLA DEM 463m, MOLA Team / NASA GSFC, via USGS Astrogeology (CC0)",
    product_page="https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m",
)

WORLDS: dict[str, World] = {w.name: w for w in (MOON, MARS)}


def get_world(name: str) -> World:
    try:
        return WORLDS[name.lower()]
    except KeyError:
        raise ValueError(
            f"unknown world {name!r}; choose one of: {', '.join(sorted(WORLDS))}"
        ) from None
