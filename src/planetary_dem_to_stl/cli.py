"""Command line: planet-stl."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .core import build_model
from .geo import Box, BoxError
from .mesh import write_stl
from .tiff import TiffError
from .worlds import WORLDS, get_world


def _positive(kind):
    def parse(text):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
        if not value > 0:
            raise argparse.ArgumentTypeError(f"must be greater than 0, got {text}")
        return value

    return parse


def _latitude(text):
    value = float(text)
    if not -90 <= value <= 90:
        raise argparse.ArgumentTypeError("latitude must be between -90 and 90")
    return value


def _longitude(text):
    value = float(text)
    if not -360 <= value <= 360:
        raise argparse.ArgumentTypeError("longitude must be between -360 and 360 (east positive)")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="planet-stl",
        description=(
            "Turn public Moon or Mars elevation data into a watertight, 3D-printable STL "
            "block with a flat base. Longitudes are east-positive, in degrees."
        ),
        epilog=(
            "examples:\n"
            "  planet-stl moon --lat -43.3 --lon -11.2 --size-km 150 -o tycho.stl\n"
            "  planet-stl mars --lat 18.65 --lon -133.8 --size-km 800 --exaggeration 3 -o olympus.stl\n"
            "  planet-stl moon --bbox -12 8 -8 12 -o copernicus.stl"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("world", choices=sorted(WORLDS), help="which body")
    where = p.add_argument_group("area (give --lat/--lon/--size-km or --bbox)")
    where.add_argument("--lat", type=_latitude, help="centre latitude, degrees north")
    where.add_argument("--lon", type=_longitude, help="centre longitude, degrees east")
    where.add_argument("--size-km", type=_positive(float), help="ground width of a square box, km")
    where.add_argument("--height-km", type=_positive(float), help="ground north-south size if not square, km")
    where.add_argument(
        "--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), help="lat/lon box, degrees"
    )
    out = p.add_argument_group("model")
    out.add_argument("-o", "--output", required=True, help="STL file to write")
    out.add_argument("--width-mm", type=_positive(float), default=100.0, help="model width (default 100)")
    out.add_argument(
        "--exaggeration", "-z", type=_positive(float), default=1.0, help="vertical exaggeration (default 1 = true scale)"
    )
    out.add_argument("--base-mm", type=_positive(float), default=2.0, help="solid base below the lowest point (default 2)")
    out.add_argument(
        "--resolution-mm", type=_positive(float), default=0.25, help="grid spacing on the model (default 0.25)"
    )
    adv = p.add_argument_group("advanced")
    adv.add_argument("--dem", help="read a local copy (or another URL) of the same global GeoTIFF instead")
    adv.add_argument("--workers", type=int, default=16, help="parallel HTTP range requests (default 16)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def parse_box(args, parser) -> Box:
    world = get_world(args.world)
    centre = [args.lat, args.lon, args.size_km]
    if args.bbox is not None:
        if any(v is not None for v in centre) or args.height_km is not None:
            parser.error("use either --bbox or --lat/--lon/--size-km, not both")
        west, south, east, north = args.bbox
        for v in (south, north):
            if not -90 <= v <= 90:
                parser.error("bbox latitudes must be between -90 and 90")
        try:
            return Box.from_bbox(west, south, east, north, world.radius_m)
        except BoxError as exc:
            parser.error(str(exc))
    if any(v is None for v in centre):
        parser.error("give --lat, --lon and --size-km (or --bbox)")
    return Box.from_centre(args.lat, args.lon, args.size_km, args.height_km)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    world = get_world(args.world)
    box = parse_box(args, parser)

    def say(msg):
        print(msg, file=sys.stderr)

    t0 = time.time()
    try:
        model = build_model(
            world,
            box,
            width_mm=args.width_mm,
            exaggeration=args.exaggeration,
            base_mm=args.base_mm,
            resolution_mm=args.resolution_mm,
            dem=args.dem,
            workers=args.workers,
            progress=say,
        )
    except BoxError as exc:
        say(f"error: {exc}")
        return 2
    except (TiffError, OSError) as exc:
        say(f"error reading elevation data: {exc}")
        return 3

    header = f"planet-stl {world.name} {box.lat:.4f},{box.lon:.4f} x{model.exaggeration:g}"
    write_stl(model.mesh, args.output, header=header)
    sx, sy, sz = model.mesh.size_mm
    say(
        f"wrote {args.output}: {sx:.1f} x {sy:.1f} x {sz:.1f} mm, {len(model.mesh.faces):,} triangles, "
        f"grid {model.grid_shape[1]}x{model.grid_shape[0]}"
    )
    say(
        f"ground {box.width_m / 1000:.1f} x {box.height_m / 1000:.1f} km, elevation "
        f"{model.elevation_min_m:.0f} to {model.elevation_max_m:.0f} m, relief {model.relief_mm:.2f} mm "
        f"at x{model.exaggeration:g} (1 mm = {1 / model.mm_per_m / 1000:.2f} km)"
    )
    for note in model.notes:
        say(note)
    say(f"data: {world.credit}")
    say(f"done in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
