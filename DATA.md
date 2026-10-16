# Data sources and licences

`planet-stl` bundles no elevation data. Each run reads only the bytes it needs
from the two public GeoTIFFs below, using HTTP range requests. Both product pages
were checked on **16 October 2026**.

This project is not affiliated with, sponsored by or endorsed by NASA, JPL, the
USGS or the LOLA and MOLA science teams. Their names appear here only to credit
the data.

## Moon: LRO LOLA DEM 118 m

| | |
|---|---|
| Product page | https://astrogeology.usgs.gov/search/map/moon_lro_lola_dem_118m |
| File read | https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif (redirects to `asc-pds-services.s3.us-west-2.amazonaws.com`, 8.5 GB) |
| Authors | LOLA Science Team; originator NASA Goddard Space Flight Center; publisher USGS Astrogeology Science Center; published 2014-03-11 |
| Access Constraints (quoted) | "public domain" |
| Use Constraints (quoted) | "Please cite authors" |
| Grid | 92160 x 46080 px, 118.45 m/px at the equator, simple cylindrical, sphere radius 1,737,400 m, signed 16-bit, value x 0.5 = metres |

Suggested citation: LOLA Science Team (2014), *Moon LRO LOLA DEM 118m v1*, USGS
Astrogeology Science Center. Instrument paper: Smith, D. E., et al. (2010),
Initial observations from the Lunar Orbiter Laser Altimeter (LOLA), *Geophys.
Res. Lett.*, 37, L18204.

## Mars: MGS MOLA DEM 463 m

| | |
|---|---|
| Product page | https://astrogeology.usgs.gov/search/map/mars_mgs_mola_dem_463m |
| File read | https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif (redirects to `asc-pds-services.s3.us-west-2.amazonaws.com`, 2.1 GB) |
| Authors | MOLA Team; originator NASA Goddard Space Flight Center; publisher USGS Astrogeology Science Center; edition 2003-03-21 |
| Access Constraints (quoted) | "CC0 (public domain)" |
| Use Constraints (quoted) | "None" |
| Grid | 46080 x 23040 px, 463.09 m/px at the equator, simple cylindrical, sphere radius 3,396,190 m, signed 16-bit metres |

Suggested citation: MOLA Team (2003), *Mars MGS MOLA DEM 463m*, USGS
Astrogeology Science Center. Instrument paper: Smith, D. E., et al. (2001), Mars
Orbiter Laser Altimeter: Experiment summary after the first year of global
mapping of Mars, *J. Geophys. Res.*, 106(E10), 23689-23722.

**Deliberately not used:** the Mars HRSC/MOLA blended DEM (200 m). USGS labels
it "MOLA (CC0) and HRSC (CC BY-SA 3.0 IGO)", and the share-alike half would put
conditions on every model made from it.

## What this means for your prints

Both sources are public domain / CC0, so as far as the data goes, models you make with this tool are
yours to use, share and sell. Crediting the data is not legally required but is
asked for ("Please cite authors") and is good practice; `planet-stl` prints a
credit line after each run that you can paste into a listing.

## Why these files and not a COG

Neither product is published as a Cloud-Optimized GeoTIFF (16 Oct 2026). Both
files are uncompressed with one image row per TIFF strip, so the bytes for any
box can still be fetched directly: one small range request per image row.
GDAL's direct-I/O path returned wrong values on these files when tested, which
is one reason this tool ships its own small (~200-line) reader (`tiff.py`) instead of
depending on GDAL/rasterio.
