"""Turn public Moon and Mars elevation data into watertight, printable STL files."""

__version__ = "0.1.0"

from .core import Model, build_model, heights_to_model  # noqa: E402
from .geo import Box, BoxError  # noqa: E402
from .mesh import Mesh, heightmap_to_solid, write_stl  # noqa: E402
from .worlds import MARS, MOON, WORLDS, World, get_world  # noqa: E402

__all__ = [
    "Box",
    "BoxError",
    "MARS",
    "MOON",
    "Mesh",
    "Model",
    "WORLDS",
    "World",
    "build_model",
    "get_world",
    "heightmap_to_solid",
    "heights_to_model",
    "write_stl",
]
