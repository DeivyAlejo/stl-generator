"""
run_example.py - minimal concept-verification runner.

Usage (from project root with uv):
    uv run python scripts/run_example.py path/to/image.jpg
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.lithophane import generate_lithophane
from scripts.validators import LithophaneParams, HoleConfig, CornerConfig, ImageAdjustConfig


def main() -> None:
    image_path = sys.argv[1] if len(sys.argv) > 1 else "sample.jpg"

    params = LithophaneParams(
        image_path=image_path,
        max_height=50,
        border=2.0,
        thickness_min=0.5,
        thickness_max=2.4,
        border_thickness=None,
        mm_per_pixel=0.1,
        resolution=None,
        build_plate_surface="auto",  # auto/back/front/bottom_edge/top_edge/left_edge/right_edge
        invert=False,
        image_adjust=ImageAdjustConfig(
            auto_white_balance=True,
            denoise_strength=0.2,
        ),
        hole=HoleConfig(
            enabled=True,
            diameter=2.0,
            position="top_right",
            angle_deg=30.0,
            offset_x=1,
            offset_y=1,
        ),
        corners=CornerConfig(enabled=True, radius=1.5, segments=8),
        output_path="output/lithophane.stl",
    )

    print(f"Generating lithophane from: {params.image_path}")
    print(f"  Max height       : {params.max_height} mm")
    print(f"  Border width     : {params.border} mm")
    print(f"  Border thickness : {params.border_thickness if params.border_thickness is not None else params.thickness_max} mm")
    print(f"  Thickness (image): {params.thickness_min}-{params.thickness_max} mm")
    print(f"  mm_per_pixel     : {params.mm_per_pixel}")
    print(f"  Build surface    : {params.build_plate_surface}")
    print(
        f"  Image adjust     : AWB={params.image_adjust.auto_white_balance}, denoise={params.image_adjust.denoise_strength}"
    )
    print(
        f"  Hole             : {params.hole.enabled} "
        f"({params.hole.position}, angle={params.hole.angle_deg} deg, "
        f"offset_x={params.hole.offset_x} mm, offset_y={params.hole.offset_y} mm)"
    )
    print(f"  Corners          : {params.corners.enabled} (r={params.corners.radius} mm)")
    print()

    metadata = generate_lithophane(params)

    print("Done!")
    print(json.dumps(metadata, indent=2))

    if metadata["warnings"]:
        print("\nWarnings:")
        for w in metadata["warnings"]:
            print(f"  ! {w}")


if __name__ == "__main__":
    main()
