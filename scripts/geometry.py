"""
Geometry helpers: hexagon hole and rounded outer-corner outline.

Coordinates are in mm:
  X -> width, Y -> height, Z -> thickness.
"""
from __future__ import annotations

import math
import numpy as np


def hexagon_vertices_2d(
    cx: float,
    cy: float,
    radius: float,
    flat_side_up: bool = True,
    rotation_deg: float = 0.0,
) -> np.ndarray:
    """Return (6, 2) 2-D vertices for a regular hexagon.

    radius is inradius (center to flat side midpoint).
    """
    circum_r = radius / math.cos(math.radians(30))
    offset = math.radians(30) if flat_side_up else 0.0
    offset += math.radians(rotation_deg)
    angles = [math.radians(60 * i) + offset for i in range(6)]
    return np.array([[cx + circum_r * math.cos(a), cy + circum_r * math.sin(a)] for a in angles])


def _hex_extent_from_center(diameter: float, angle_deg: float) -> tuple[float, float, float, float]:
    """Return (min_x, max_x, min_y, max_y) of a unit hex centered at origin."""
    radius = diameter / 2.0
    pts = hexagon_vertices_2d(0.0, 0.0, radius, flat_side_up=True, rotation_deg=angle_deg)
    return float(pts[:, 0].min()), float(pts[:, 0].max()), float(pts[:, 1].min()), float(pts[:, 1].max())


def hole_center(
    position: str,
    content_width: float,
    content_height: float,
    border: float,
    diameter: float,
    angle_deg: float,
    offset_x: float,
    offset_y: float,
) -> tuple[float, float]:
    """Return (cx, cy) of the keychain hole in total-mesh coordinates.

    Offsets are clearances from the OUTER hole border to the selected model edge:
      - offset=0: hole touches that edge
      - offset>=1: explicit spacing in mm
    """
    total_w = content_width + 2 * border
    total_h = content_height + 2 * border

    # Exact tangency can create boolean degeneracies; keep a tiny internal epsilon.
    eps = 1e-3
    ox = eps if offset_x == 0 else offset_x
    oy = eps if offset_y == 0 else offset_y

    min_x, max_x, _min_y, max_y = _hex_extent_from_center(diameter, angle_deg)

    if position == "top_right":
        cx = total_w - ox - max_x
        cy = total_h - oy - max_y
    elif position == "top_left":
        cx = ox - min_x
        cy = total_h - oy - max_y
    elif position == "top_center":
        cx = (total_w / 2.0) + offset_x
        cy = total_h - oy - max_y
    else:
        raise ValueError(f"Unknown hole position: {position!r}")

    return cx, cy


def punch_hex_hole(
    vertices: np.ndarray,
    faces: np.ndarray,
    cx: float,
    cy: float,
    radius: float,
    angle_deg: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Subtract a rotated hexagonal prism from the mesh."""
    import trimesh
    from trimesh.creation import extrude_polygon
    from shapely.geometry import Polygon as ShapelyPolygon

    hex_verts_2d = hexagon_vertices_2d(
        cx,
        cy,
        radius,
        flat_side_up=True,
        rotation_deg=angle_deg,
    )
    poly = ShapelyPolygon(hex_verts_2d)

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    hex_height = float(vertices[:, 2].max()) + 2.0
    cutter = extrude_polygon(poly, height=hex_height)
    cutter.apply_translation([0.0, 0.0, -1.0])

    try:
        result = trimesh.boolean.difference([mesh, cutter], engine="manifold")
        if result is None or len(result.vertices) == 0:
            raise RuntimeError("Boolean returned empty mesh")
    except Exception:
        result = _fallback_punch(mesh, poly)

    return np.array(result.vertices), np.array(result.faces)


def _fallback_punch(mesh, poly) -> object:
    """Fallback: remove faces whose centroid lies inside poly projection."""
    import trimesh
    from shapely.geometry import Point

    centroids = mesh.triangles_center[:, :2]
    keep = np.array([not poly.contains(Point(c[0], c[1])) for c in centroids])
    return trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces[keep], process=False)


def round_corners_2d(
    width: float,
    height: float,
    radius: float,
    segments: int = 8,
) -> np.ndarray:
    """Return (N, 2) outline for rectangle with rounded corners."""
    if radius <= 0:
        return np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=float)

    corners = [
        (radius, radius, math.radians(180), math.radians(270)),
        (width - radius, radius, math.radians(270), math.radians(360)),
        (width - radius, height - radius, math.radians(0), math.radians(90)),
        (radius, height - radius, math.radians(90), math.radians(180)),
    ]

    pts: list[list[float]] = []
    for cx, cy, a_start, a_end in corners:
        for i in range(segments + 1):
            t = i / segments
            a = a_start + t * (a_end - a_start)
            pts.append([cx + radius * math.cos(a), cy + radius * math.sin(a)])

    dedup: list[list[float]] = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - dedup[-1][0]) > 1e-9 or abs(p[1] - dedup[-1][1]) > 1e-9:
            dedup.append(p)

    return np.array(dedup, dtype=float)
