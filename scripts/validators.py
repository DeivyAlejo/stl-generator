"""Parameter validation for the lithophane generator."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HoleConfig:
    enabled: bool = False
    diameter: float = 5.0          # mm, flat-to-flat for hex
    position: str = "top_right"    # "top_right" | "top_left" | "top_center"
    angle_deg: float = 0.0         # degrees, rotation in XY plane
    offset_x: float = 0.0          # mm clearance from hole border to side edge
    offset_y: float = 0.0          # mm clearance from hole border to top edge


@dataclass
class CornerConfig:
    enabled: bool = False
    radius: float = 2.0            # mm
    segments: int = 8              # arc subdivisions per corner


@dataclass
class ImageAdjustConfig:
    auto_white_balance: bool = False
    denoise_strength: float = 0.0   # 0.0=no denoise, 1.0=light denoise





@dataclass
class LithophaneParams:
    image_path: str = ""
    max_height: float = 100.0      # mm, TOTAL height including border
    border: float = 5.0            # mm, 0 = no border
    thickness_min: float = 0.8     # mm, thinnest point (lightest pixel)
    thickness_max: float = 3.0     # mm, thickest point (darkest pixel)
    border_thickness: float | None = None  # mm, None -> use thickness_max
    mm_per_pixel: float | None = 0.12      # preferred sampling control
    resolution: int | None = None          # legacy fallback sampling control
    build_plate_surface: str = "auto"     # auto|back|front|bottom_edge|top_edge|left_edge|right_edge
    invert: bool = False           # True -> dark pixels become thin
    image_adjust: ImageAdjustConfig = field(default_factory=ImageAdjustConfig)
    hole: HoleConfig = field(default_factory=HoleConfig)
    corners: CornerConfig = field(default_factory=CornerConfig)
    output_path: str = "lithophane.stl"


class ValidationError(ValueError):
    pass


def validate(params: LithophaneParams) -> None:
    """Raise ValidationError on the first constraint violation found."""

    if not params.image_path:
        raise ValidationError("image_path must not be empty.")

    if params.max_height <= 0:
        raise ValidationError(f"max_height must be positive, got {params.max_height}.")

    if params.border < 0:
        raise ValidationError(f"border must be >= 0, got {params.border}.")

    if params.max_height <= 2 * params.border:
        raise ValidationError(
            f"max_height ({params.max_height}) must be greater than 2*border ({2*params.border}) "
            "because max_height now includes the border."
        )

    if params.thickness_min <= 0:
        raise ValidationError(
            f"thickness_min must be > 0, got {params.thickness_min}."
        )

    if params.thickness_max <= params.thickness_min:
        raise ValidationError(
            f"thickness_max ({params.thickness_max}) must be greater than "
            f"thickness_min ({params.thickness_min})."
        )

    if params.border_thickness is not None and params.border_thickness <= 0:
        raise ValidationError(
            f"border_thickness must be > 0 when provided, got {params.border_thickness}."
        )

    if params.thickness_min < 0.5:
        raise ValidationError(
            f"thickness_min {params.thickness_min} mm is below the recommended "
            "printability minimum of 0.5 mm."
        )

    if not (0.0 <= params.image_adjust.denoise_strength <= 1.0):
        raise ValidationError(
            f"image_adjust.denoise_strength must be between 0.0 and 1.0, got {params.image_adjust.denoise_strength}."
        )

    if params.mm_per_pixel is not None:
        if params.mm_per_pixel <= 0:
            raise ValidationError(
                f"mm_per_pixel must be > 0, got {params.mm_per_pixel}."
            )
        if not (0.02 <= params.mm_per_pixel <= 2.0):
            raise ValidationError(
                f"mm_per_pixel must be between 0.02 and 2.0, got {params.mm_per_pixel}."
            )
    elif params.resolution is not None:
        if not (10 <= params.resolution <= 1024):
            raise ValidationError(
                f"resolution must be between 10 and 1024, got {params.resolution}."
            )
    else:
        raise ValidationError("Provide either mm_per_pixel or resolution.")

    valid_surfaces = {
        "auto",
        "back",
        "front",
        "bottom_edge",
        "top_edge",
        "left_edge",
        "right_edge",
    }
    if params.build_plate_surface not in valid_surfaces:
        raise ValidationError(
            f"build_plate_surface must be one of {valid_surfaces}, got '{params.build_plate_surface}'."
        )

    if params.corners.enabled:
        if params.corners.radius <= 0:
            raise ValidationError(
                f"corners.radius must be > 0, got {params.corners.radius}."
            )
        if params.border > 0 and params.corners.radius > params.border:
            raise ValidationError(
                f"corners.radius ({params.corners.radius} mm) cannot exceed "
                f"border ({params.border} mm)."
            )
        if params.corners.segments < 4:
            raise ValidationError(
                f"corners.segments must be >= 4, got {params.corners.segments}."
            )

    if params.hole.enabled:
        if params.hole.diameter <= 0:
            raise ValidationError(
                f"hole.diameter must be > 0, got {params.hole.diameter}."
            )
        if params.hole.diameter < 2.0:
            raise ValidationError(
                f"hole.diameter {params.hole.diameter} mm is too small to be practical "
                "(minimum 2.0 mm)."
            )
        if params.hole.offset_x < 0 or params.hole.offset_y < 0:
            raise ValidationError(
                f"hole.offset_x and hole.offset_y must be >= 0, got "
                f"({params.hole.offset_x}, {params.hole.offset_y})."
            )
        if 0 < params.hole.offset_x < 1.0 or 0 < params.hole.offset_y < 1.0:
            raise ValidationError("hole offsets must be either 0 or >= 1.0 mm.")
        valid_positions = {"top_right", "top_left", "top_center"}
        if params.hole.position not in valid_positions:
            raise ValidationError(
                f"hole.position must be one of {valid_positions}, "
                f"got '{params.hole.position}'."
            )
        if not (-180.0 <= params.hole.angle_deg <= 180.0):
            raise ValidationError(
                f"hole.angle_deg must be between -180 and 180, got {params.hole.angle_deg}."
            )

    if not params.output_path:
        raise ValidationError("output_path must not be empty.")
