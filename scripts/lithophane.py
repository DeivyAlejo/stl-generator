"""
lithophane.py — core lithophane STL generator.

All distances are in millimetres.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from scripts.validators import LithophaneParams, validate
from scripts.geometry import hole_center, punch_hex_hole, round_corners_2d


def _resolve_build_plate_surface(params: LithophaneParams) -> str:
    """Resolve which surface should sit on the build plate."""
    if params.build_plate_surface != "auto":
        return params.build_plate_surface

    # Default requested behavior: use thin surface opposite the top hole.
    if params.hole.enabled and params.hole.position in {"top_right", "top_left", "top_center"}:
        return "bottom_edge"

    return "back"


def _orient_mesh_for_build_plate(mesh, surface: str) -> None:
    """Rotate mesh so chosen surface is horizontal on the build plate (z=0)."""
    import trimesh

    rot = None
    if surface == "back":
        rot = None
    elif surface == "front":
        rot = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    elif surface == "bottom_edge":
        rot = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0])
    elif surface == "top_edge":
        rot = trimesh.transformations.rotation_matrix(-math.pi / 2.0, [1, 0, 0])
    elif surface == "left_edge":
        rot = trimesh.transformations.rotation_matrix(-math.pi / 2.0, [0, 1, 0])
    elif surface == "right_edge":
        rot = trimesh.transformations.rotation_matrix(math.pi / 2.0, [0, 1, 0])

    if rot is not None:
        mesh.apply_transform(rot)

    # Drop selected support plane to z=0.
    mesh.apply_translation([0.0, 0.0, -float(mesh.vertices[:, 2].min())])


def _auto_white_balance_rgb(img_rgb: Image.Image) -> Image.Image:
    """Apply simple per-channel percentile stretch for auto white balance."""
    arr = np.asarray(img_rgb, dtype=np.float32)

    for c in range(3):
        ch = arr[:, :, c]
        lo, hi = np.percentile(ch, [1.0, 99.0])
        if hi - lo < 1e-5:
            continue
        ch = (ch - lo) * (255.0 / (hi - lo))
        arr[:, :, c] = np.clip(ch, 0.0, 255.0)

    return Image.fromarray(arr.astype(np.uint8), mode="RGB")


def _preprocess_image(params: LithophaneParams) -> Image.Image:
    """Load and preprocess source image before grayscale conversion."""
    img = Image.open(params.image_path).convert("RGB")

    if params.image_adjust.auto_white_balance:
        img = _auto_white_balance_rgb(img)

    if params.image_adjust.denoise_strength > 0:
        # Keep denoise mild so we preserve lithophane details.
        radius = 0.3 + 1.2 * params.image_adjust.denoise_strength
        img = img.filter(ImageFilter.GaussianBlur(radius=radius))

    return img


def _image_to_thickness_map(
    params: LithophaneParams,
    img_w: int,
    img_h: int,
    physical_w: float,
    physical_h: float,
) -> tuple[np.ndarray, int, int]:
    """Return (thickness_map, grid_cols, grid_rows) for the image content area."""
    img = _preprocess_image(params).convert("L")

    aspect = img_w / img_h

    if params.mm_per_pixel is not None:
        grid_cols = max(2, int(round(physical_w / params.mm_per_pixel)) + 1)
        grid_rows = max(2, int(round(physical_h / params.mm_per_pixel)) + 1)
    else:
        # Backward-compatible fallback when using legacy resolution.
        base = int(params.resolution or 200)
        if aspect >= 1:
            grid_rows = base
            grid_cols = max(2, round(base * aspect))
        else:
            grid_cols = base
            grid_rows = max(2, round(base / aspect))

    img_resized = img.resize((grid_cols, grid_rows), Image.LANCZOS)
    gray = np.array(img_resized, dtype=np.float32) / 255.0

    # PIL uses top-left as origin; mesh uses bottom-left.
    gray = np.flipud(gray)

    depth = 1.0 - gray
    if params.invert:
        depth = 1.0 - depth

    thickness = depth * (params.thickness_max - params.thickness_min) + params.thickness_min
    return thickness, grid_cols, grid_rows


def _grid_faces(rows: int, cols: int, offset: int = 0) -> np.ndarray:
    """Face indices for a regular grid (CCW normals pointing +Z)."""
    idx = np.arange(rows * cols).reshape(rows, cols)
    bl = idx[:-1, :-1].ravel()
    br = idx[:-1, 1:].ravel()
    tl = idx[1:, :-1].ravel()
    tr = idx[1:, 1:].ravel()
    f1 = np.stack([bl, br, tl], axis=1)
    f2 = np.stack([br, tr, tl], axis=1)
    return np.vstack([f1, f2]) + offset


def _build_walls(rows: int, cols: int, back_offset: int) -> np.ndarray:
    """Side walls connecting perimeter of front to back."""
    idx = np.arange(rows * cols).reshape(rows, cols)
    perimeter = np.concatenate([
        idx[0, :-1],
        idx[:-1, -1],
        idx[-1, :0:-1],
        idx[:0:-1, 0],
    ])
    p_f = perimeter
    p_b = perimeter + back_offset
    p_fn = np.roll(p_f, -1)
    p_bn = np.roll(p_b, -1)
    t1 = np.stack([p_f, p_b, p_fn], axis=1)
    t2 = np.stack([p_fn, p_b, p_bn], axis=1)
    return np.vstack([t1, t2])


def _build_base_mesh(
    thickness_map: np.ndarray,
    physical_w: float,
    physical_h: float,
    border: float,
    border_thickness: float,
    corner_radius: float,
    corner_segments: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Build watertight mesh with a smooth border-to-image transition."""
    import trimesh
    from shapely.geometry import Polygon as ShapelyPolygon
    from trimesh.creation import extrude_polygon

    rows, cols = thickness_map.shape

    total_w = physical_w + 2 * border
    total_h = physical_h + 2 * border

    dx = physical_w / max(1, cols - 1)
    dy = physical_h / max(1, rows - 1)
    step_mm = max(min(dx, dy), 1e-6)

    border_cells = max(2, round(border / step_mm)) if border > 0 else 0

    total_cols = cols + 2 * border_cells
    total_rows = rows + 2 * border_cells

    xs = np.linspace(0.0, total_w, total_cols)
    ys = np.linspace(0.0, total_h, total_rows)
    XX, YY = np.meshgrid(xs, ys)

    image_min = float(thickness_map.min())
    ZZ = np.full((total_rows, total_cols), image_min, dtype=np.float32)

    r0 = border_cells
    c0 = border_cells
    r1 = r0 + rows
    c1 = c0 + cols

    # No transition blend: place the lithophane relief as-is.
    ZZ[r0:r1, c0:c1] = thickness_map

    if border_cells > 0:
        I, J = np.indices((total_rows, total_cols))

        dx_out = np.maximum(np.maximum(c0 - J, 0), np.maximum(J - (c1 - 1), 0))
        dy_out = np.maximum(np.maximum(r0 - I, 0), np.maximum(I - (r1 - 1), 0))
        d = np.maximum(dx_out, dy_out).astype(np.float32)

        # Keep outer border intact and flat.
        mask_border = d > 0
        ZZ[mask_border] = border_thickness

        # 45-degree chamfer going inside the image area only.
        ii, jj = np.indices((rows, cols))
        edge_cells = np.minimum.reduce([ii, rows - 1 - ii, jj, cols - 1 - jj]).astype(np.float32)
        inward_mm = edge_cells * step_mm
        chamfer_floor = float(border_thickness) - inward_mm
        content_with_chamfer = np.maximum(thickness_map, chamfer_floor)
        ZZ[r0:r1, c0:c1] = content_with_chamfer

    n = total_rows * total_cols
    front_verts = np.stack([XX.ravel(), YY.ravel(), ZZ.ravel()], axis=1)
    back_verts = np.stack([XX.ravel(), YY.ravel(), np.zeros(n)], axis=1)
    verts = np.vstack([front_verts, back_verts])

    front_faces = _grid_faces(total_rows, total_cols, offset=0)
    back_faces = _grid_faces(total_rows, total_cols, offset=n)[:, ::-1]
    wall_faces = _build_walls(total_rows, total_cols, back_offset=n)
    faces = np.vstack([front_faces, back_faces, wall_faces])

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)

    if corner_radius > 0:
        poly_pts = round_corners_2d(total_w, total_h, corner_radius, corner_segments)
        profile = ShapelyPolygon(poly_pts)
        prism_h = float(np.max(ZZ)) + 4.0
        cutter = extrude_polygon(profile, height=prism_h)
        cutter.apply_translation([0.0, 0.0, -2.0])
        clipped = trimesh.boolean.intersection([mesh, cutter], engine="manifold")
        if clipped is not None and len(clipped.vertices) > 0:
            mesh = clipped

    mesh.fix_normals()
    return np.array(mesh.vertices), np.array(mesh.faces)


def generate_lithophane(params: LithophaneParams) -> dict:
    """Generate a lithophane STL from *params*."""
    import trimesh

    t_start = time.time()
    warnings: list[str] = []

    validate(params)

    with Image.open(params.image_path) as img:
        img_w, img_h = img.size

    aspect = img_w / img_h

    total_h_target = params.max_height
    physical_h = total_h_target - 2 * params.border
    physical_w = physical_h * aspect

    thickness_map, grid_cols, grid_rows = _image_to_thickness_map(
        params,
        img_w,
        img_h,
        physical_w,
        physical_h,
    )

    border_thickness = (
        float(params.thickness_max)
        if params.border_thickness is None
        else float(params.border_thickness)
    )

    c_radius = params.corners.radius if params.corners.enabled else 0.0
    c_segs = params.corners.segments if params.corners.enabled else 8

    if params.corners.enabled and params.border > 0 and c_radius > 0.8 * params.border:
        warnings.append(
            f"Corner radius {params.corners.radius} mm is close to border {params.border} mm."
        )

    vertices, faces = _build_base_mesh(
        thickness_map,
        physical_w,
        physical_h,
        params.border,
        border_thickness,
        c_radius,
        c_segs,
    )

    if params.hole.enabled:
        total_w = physical_w + 2 * params.border
        total_h = physical_h + 2 * params.border
        hx, hy = hole_center(
            params.hole.position,
            physical_w,
            physical_h,
            params.border,
            params.hole.diameter,
            params.hole.angle_deg,
            params.hole.offset_x,
            params.hole.offset_y,
        )
        r = params.hole.diameter / 2
        if hx - r < 0 or hx + r > total_w or hy - r < 0 or hy + r > total_h:
            warnings.append("Keychain hole extends outside mesh boundary — skipping hole.")
        else:
            try:
                vertices, faces = punch_hex_hole(
                    vertices,
                    faces,
                    hx,
                    hy,
                    r,
                    angle_deg=params.hole.angle_deg,
                )
            except Exception as exc:
                warnings.append(f"Hole creation failed ({exc}); hole skipped.")

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.fix_normals()

    resolved_surface = _resolve_build_plate_surface(params)
    _orient_mesh_for_build_plate(mesh, resolved_surface)

    out = Path(params.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(out))

    is_wt = bool(mesh.is_watertight)
    if not is_wt:
        warnings.append("Mesh is NOT watertight — may not print correctly.")

    total_w = physical_w + 2 * params.border
    total_h = physical_h + 2 * params.border

    return {
        "output_path": str(out.resolve()),
        "image_size": (img_w, img_h),
        "dimensions_mm": {
            "content_width": round(physical_w, 3),
            "content_height": round(physical_h, 3),
            "total_width": round(total_w, 3),
            "total_height": round(total_h, 3),
            "thickness_min": round(float(thickness_map.min()), 3),
            "thickness_max": round(float(params.thickness_max), 3),
            "border": params.border,
            "border_thickness": round(border_thickness, 3),
            "mm_per_pixel_requested": params.mm_per_pixel,
            "mm_per_pixel_effective_x": round(physical_w / max(1, grid_cols - 1), 4),
            "mm_per_pixel_effective_y": round(physical_h / max(1, grid_rows - 1), 4),
            "build_plate_surface": resolved_surface,
        },
        "mesh_vertices": len(mesh.vertices),
        "mesh_faces": len(mesh.faces),
        "is_watertight": is_wt,
        "volume_cm3": round(float(mesh.volume) / 1000.0, 4),
        "generation_time_sec": round(time.time() - t_start, 3),
        "warnings": warnings,
    }
