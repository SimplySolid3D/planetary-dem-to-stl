"""Render a shaded preview PNG of an STL, offscreen (needs trimesh + matplotlib).

    python scripts/render_preview.py out/tycho.stl docs/tycho.png --title "Tycho crater"
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("stl")
    p.add_argument("png")
    p.add_argument("--title", default="")
    p.add_argument("--elev", type=float, default=38.0)
    p.add_argument("--azim", type=float, default=-60.0)
    args = p.parse_args()

    mesh = trimesh.load(args.stl)
    # Matplotlib sorts polygons by depth only roughly; the large bottom-fan
    # triangles can never be seen from above, so leave them out of the picture.
    visible = mesh.face_normals[:, 2] > -0.5
    tris = mesh.triangles[visible]
    normals = mesh.face_normals[visible]
    light = np.array([-0.5, -0.6, 0.62])
    light /= np.linalg.norm(light)
    shade = np.clip(normals @ light, 0.0, 1.0) * 0.8 + 0.2
    base = np.array([0.80, 0.78, 0.74])
    colours = np.clip(shade[:, None] * base[None, :], 0, 1)

    fig = plt.figure(figsize=(8, 6), dpi=110)
    ax = fig.add_subplot(projection="3d")
    ax.add_collection3d(Poly3DCollection(tris, facecolors=colours, edgecolors="none", linewidths=0))
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_zlim(z0, z1)
    ax.set_box_aspect((x1 - x0, y1 - y0, z1 - z0))
    ax.view_init(elev=args.elev, azim=args.azim)
    ax.set_axis_off()
    size = f"{x1 - x0:.0f} x {y1 - y0:.0f} x {z1 - z0:.1f} mm"
    ax.set_title(f"{args.title}\n{size}" if args.title else size, fontsize=11)
    fig.patch.set_facecolor("white")
    fig.tight_layout()
    fig.savefig(args.png, bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    main()
