from __future__ import annotations

import argparse
from pathlib import Path

from scripts.lithophane import generate_lithophane
from scripts.validators import (
    CornerConfig,
    HoleConfig,
    ImageAdjustConfig,
    LithophaneParams,
)

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate lithophane STL files from every image in a folder "
            "using the same parameters."
        )
    )

    parser.add_argument(
        "input_dir",
        nargs="?",
        help="Folder containing source images.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Folder where STL files are written (default: output).",
    )

    parser.add_argument("--max-height", type=float, default=100.0)
    parser.add_argument("--border", type=float, default=5.0)
    parser.add_argument("--thickness-min", type=float, default=0.8)
    parser.add_argument("--thickness-max", type=float, default=3.0)
    parser.add_argument(
        "--border-thickness",
        type=float,
        default=None,
        help="Border thickness in mm. If omitted, thickness_max is used.",
    )

    parser.add_argument(
        "--mm-per-pixel",
        type=float,
        default=0.12,
        help="Sampling density. Ignored when --resolution is provided.",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        default=None,
        help="Legacy sampling control. If provided, mm_per_pixel is disabled.",
    )

    parser.add_argument("--invert", action="store_true")
    parser.add_argument(
        "--build-plate-surface",
        default="auto",
        choices=[
            "auto",
            "back",
            "front",
            "bottom_edge",
            "top_edge",
            "left_edge",
            "right_edge",
        ],
    )

    parser.add_argument("--auto-white-balance", action="store_true")
    parser.add_argument("--denoise-strength", type=float, default=0.2)

    parser.add_argument("--hole-enabled", action="store_true")
    parser.add_argument("--hole-diameter", type=float, default=5.0)
    parser.add_argument(
        "--hole-position",
        default="top_right",
        choices=["top_right", "top_left", "top_center"],
    )
    parser.add_argument("--hole-angle-deg", type=float, default=0.0)
    parser.add_argument("--hole-offset-x", type=float, default=0.0)
    parser.add_argument("--hole-offset-y", type=float, default=0.0)

    parser.add_argument("--corners-enabled", action="store_true")
    parser.add_argument("--corners-radius", type=float, default=2.0)
    parser.add_argument("--corners-segments", type=int, default=8)

    return parser.parse_args()


def _resolve_input_dir(raw_input_dir: str | None) -> Path:
    if raw_input_dir:
        return Path(raw_input_dir).expanduser()

    typed = input("Folder with images: ").strip()
    if not typed:
        raise ValueError("No input folder provided.")
    return Path(typed).expanduser()


def _collect_images(input_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    )


def _build_params(args: argparse.Namespace, image_path: Path, output_path: Path) -> LithophaneParams:
    if args.resolution is not None:
        mm_per_pixel = None
        resolution = args.resolution
    else:
        mm_per_pixel = args.mm_per_pixel
        resolution = None

    return LithophaneParams(
        image_path=str(image_path),
        max_height=args.max_height,
        border=args.border,
        thickness_min=args.thickness_min,
        thickness_max=args.thickness_max,
        border_thickness=args.border_thickness,
        mm_per_pixel=mm_per_pixel,
        resolution=resolution,
        build_plate_surface=args.build_plate_surface,
        invert=args.invert,
        image_adjust=ImageAdjustConfig(
            auto_white_balance=args.auto_white_balance,
            denoise_strength=args.denoise_strength,
        ),
        hole=HoleConfig(
            enabled=args.hole_enabled,
            diameter=args.hole_diameter,
            position=args.hole_position,
            angle_deg=args.hole_angle_deg,
            offset_x=args.hole_offset_x,
            offset_y=args.hole_offset_y,
        ),
        corners=CornerConfig(
            enabled=args.corners_enabled,
            radius=args.corners_radius,
            segments=args.corners_segments,
        ),
        output_path=str(output_path),
    )


def main() -> int:
    args = _parse_args()

    try:
        input_dir = _resolve_input_dir(args.input_dir)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Error: input folder not found or not a folder: {input_dir}")
        return 2

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    images = _collect_images(input_dir)
    if not images:
        print(f"No supported image files found in {input_dir}")
        print("Supported types: " + ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS)))
        return 1

    print(f"Found {len(images)} image(s) in {input_dir}")
    print(f"Output folder: {output_dir.resolve()}")

    success = 0
    failed: list[tuple[Path, str]] = []

    for image_path in images:
        output_path = output_dir / f"{image_path.stem}.stl"
        print(f"\n[{success + len(failed) + 1}/{len(images)}] {image_path.name} -> {output_path.name}")

        params = _build_params(args, image_path, output_path)

        try:
            metadata = generate_lithophane(params)
            success += 1
            print("  OK")

            warnings = metadata.get("warnings", [])
            for warning in warnings:
                print(f"  Warning: {warning}")
        except Exception as exc:
            failed.append((image_path, str(exc)))
            print(f"  Failed: {exc}")

    print("\nBatch complete")
    print(f"  Success: {success}")
    print(f"  Failed : {len(failed)}")

    if failed:
        print("\nFailed files:")
        for image_path, err in failed:
            print(f"  - {image_path.name}: {err}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
