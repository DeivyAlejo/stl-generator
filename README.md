# STL Generator (Lithophane Batch CLI)

This project generates lithophane STL files from images.

It supports both single-image and batch workflows, and the main CLI can process all supported image files in a folder using the same parameters.

## What it does

- Reads all images from an input folder.
- Converts each image into a lithophane mesh.
- Applies the same geometry settings to every image.
- Exports one STL per image, preserving the image filename stem.

## Current border/chamfer behavior

- Border is kept intact.
- No blending transition is applied between border and relief.
- Chamfer is 45 degrees and goes inward into the image area.

## Supported image formats

- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.tif`
- `.tiff`
- `.webp`

## Quick start 
```bash
git clone
```
From project root:
```bash
uv sync
```

### Linux
```bash
uv run main.py /home/desk24/Documents/projects/stl-generator/images \
  --output-dir /home/desk24/Documents/projects/stl-generator/output/batch \
  --max-height 50 \
  --border 2 \
  --thickness-min 0.5 \
  --thickness-max 2.4 \
  --border-thickness 2.4 \
  --mm-per-pixel 0.08 \
  --build-plate-surface left_edge \
  --auto-white-balance \
  --denoise-strength 0.2 \
  --hole-enabled \
  --hole-diameter 2 \
  --hole-position top_right \
  --hole-angle-deg 30 \
  --hole-offset-x 1.0 \
  --hole-offset-y 1.0 \
  --corners-enabled \
  --corners-radius 1.5 \
  --corners-segments 8
```

### Windows
```bash
uv run main.py C:\Users\folder `
  --output-dir C:\Users\folder `
  --max-height 50 `
  --border 2 `
  --thickness-min 0.5 `
  --thickness-max 2.4 `
  --border-thickness 2.4 `
  --mm-per-pixel 0.1 `
  --build-plate-surface left_edge `
  --auto-white-balance `
  --denoise-strength 0.2 `
  --hole-enabled `
  --hole-diameter 2 `
  --hole-position top_right `
  --hole-angle-deg 30 `
  --hole-offset-x 1.0 `
  --hole-offset-y 1.0 `
  --corners-enabled `
  --corners-radius 1.5 `
  --corners-segments 8
```

## Output

Generated STLs are written to the folder passed in `--output-dir`, for example:

- `fam.png` -> `fam.stl`
- `test_image.jpg` -> `test_image.stl`

## Notes

- If `--resolution` is provided, it is used as sampling control and `--mm-per-pixel` is ignored.
- Use `--invert` only when you want the depth mapping inverted.
