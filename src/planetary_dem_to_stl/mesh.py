"""Heightmap -> closed solid block -> binary STL.

The solid is a top surface on a regular grid, four vertical walls and a flat
bottom at z = 0. Every edge is shared by exactly two triangles and every
triangle is wound counter-clockwise seen from outside, so the mesh is
watertight with outward normals.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np


@dataclass
class Mesh:
    vertices: np.ndarray  # (n, 3) float64, millimetres
    faces: np.ndarray  # (m, 3) int64

    @property
    def bounds(self) -> np.ndarray:
        return np.array([self.vertices.min(axis=0), self.vertices.max(axis=0)])

    @property
    def size_mm(self) -> np.ndarray:
        b = self.bounds
        return b[1] - b[0]


def heightmap_to_solid(z_mm: np.ndarray, width_mm: float, depth_mm: float) -> Mesh:
    """Build the solid from a grid of top heights (row 0 = front/south edge).

    `z_mm` must be strictly positive so the walls have height everywhere.
    """
    z = np.asarray(z_mm, dtype=np.float64)
    if z.ndim != 2 or min(z.shape) < 2:
        raise ValueError("heightmap must be a 2-D grid of at least 2x2")
    if not np.all(np.isfinite(z)) or z.min() <= 0:
        raise ValueError("heights must be finite and above the base (z > 0)")
    ny, nx = z.shape
    xs = np.linspace(0.0, width_mm, nx)
    ys = np.linspace(0.0, depth_mm, ny)
    gx, gy = np.meshgrid(xs, ys)
    top = np.column_stack([gx.ravel(), gy.ravel(), z.ravel()])

    idx = np.arange(nx * ny).reshape(ny, nx)
    a = idx[:-1, :-1].ravel()
    b = idx[:-1, 1:].ravel()
    c = idx[1:, 1:].ravel()
    d = idx[1:, :-1].ravel()
    top_faces = np.concatenate([np.column_stack([a, b, c]), np.column_stack([a, c, d])])

    # Boundary loop, counter-clockwise seen from above: south edge west->east,
    # east edge south->north, north edge east->west, west edge north->south.
    ring = np.concatenate([idx[0, :-1], idx[:-1, -1], idx[-1, :0:-1], idx[:0:-1, 0]])
    n_top = len(top)
    k = len(ring)
    bottom_ring = top[ring].copy()
    bottom_ring[:, 2] = 0.0
    centre = np.array([[width_mm / 2.0, depth_mm / 2.0, 0.0]])
    vertices = np.vstack([top, bottom_ring, centre])

    ring_b = n_top + np.arange(k)  # bottom copy of ring[i]
    nxt = np.roll(np.arange(k), -1)
    t_a, t_b = ring, ring[nxt]
    b_a, b_b = ring_b, ring_b[nxt]
    walls = np.concatenate([np.column_stack([b_a, b_b, t_b]), np.column_stack([b_a, t_b, t_a])])
    c_idx = n_top + k
    bottom = np.column_stack([np.full(k, c_idx), b_b, b_a])  # clockwise from above = facing down

    faces = np.concatenate([top_faces, walls, bottom]).astype(np.int64)
    return Mesh(vertices, faces)


def face_normals(mesh: Mesh) -> np.ndarray:
    v = mesh.vertices[mesh.faces]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.where(length > 0, length, 1.0)


def write_stl(mesh: Mesh, path, header: str = "") -> None:
    """Write a binary STL (little-endian, float32)."""
    record = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    data = np.zeros(len(mesh.faces), dtype=record)
    data["normal"] = face_normals(mesh)
    data["v"] = mesh.vertices[mesh.faces]
    head = header.encode("ascii", "replace")[:80]
    if head.lower().startswith(b"solid"):
        head = b"binary " + head  # an ASCII-looking header confuses some readers
    head = head[:80].ljust(80, b" ")
    with open(path, "wb") as fh:
        fh.write(head)
        fh.write(struct.pack("<I", len(data)))
        fh.write(data.tobytes())
