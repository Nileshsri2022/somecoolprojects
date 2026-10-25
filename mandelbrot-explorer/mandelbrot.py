#!/usr/bin/env python3
"""Mandelbrot Set Explorer — Coding Challenges #84.

Draws the Mandelbrot set (escape-time iteration of f(z) = z^2 + c from
z = 0) as ASCII art on stdout, or as a hand-written PNG file.
Python 3 standard library only; no display required.

Usage:
    python3 mandelbrot.py [--width W] [--height H] [--max-iter N]
    python3 mandelbrot.py --box XMIN XMAX YMIN YMAX
    python3 mandelbrot.py --center CX CY --zoom FACTOR
    python3 mandelbrot.py --output out.png [--width W] [--height H]
                          [--dpi DPI] [--palette NAME]
"""

import argparse
import struct
import sys
import zlib

DEFAULT_VIEW = (-2.0, 2.0, -2.0, 2.0)  # xmin, xmax, ymin, ymax (page's Step 2 framing)
GRADIENT = " .:-=+*#%"
INSIDE_CHAR = "@"
INSIDE_RGB = (0, 0, 0)

# Palette name -> list of RGB stops, interpolated by escape fraction.
PALETTES = {
    "grayscale": [(255, 255, 255), (128, 128, 128)],
    "fire": [(255, 255, 0), (255, 128, 0), (255, 0, 0), (128, 0, 0)],
    "ocean": [(0, 255, 255), (0, 128, 255), (0, 0, 255), (0, 0, 128)],
}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PIXELS_PER_METRE_PER_DPI = 39.3700787


def escape_count(c, max_iter=100):
    """Iterations until z = z^2 + c (from z = 0) exceeds |z| > 2.

    Returns the 1-based iteration that escaped, or max_iter if the
    point never escaped within max_iter iterations (treated as inside).
    """
    if max_iter <= 0:
        raise ValueError("max_iter must be positive")
    x = 0.0
    y = 0.0
    for iteration in range(1, max_iter + 1):
        x, y = x * x - y * y + c.real, 2.0 * x * y + c.imag
        if x * x + y * y > 4.0:
            return iteration
    return max_iter


def map_pixel(px, py, width, height, view):
    """Map pixel (px, py) to a complex number. Row 0 is the top."""
    xmin, xmax, ymin, ymax = view
    real = xmin + px / width * (xmax - xmin)
    imag = ymax - py / height * (ymax - ymin)
    return complex(real, imag)


def zoom_view(view, cx, cy, factor):
    """Shrink view by factor around centre (cx, cy). factor > 1 zooms in."""
    if factor <= 0:
        raise ValueError("zoom factor must be positive")
    xmin, xmax, ymin, ymax = view
    half_w = (xmax - xmin) / 2.0 / factor
    half_h = (ymax - ymin) / 2.0 / factor
    return (cx - half_w, cx + half_w, cy - half_h, cy + half_h)


def ascii_char(count, max_iter):
    """Character for an escape count; '@' is reserved for inside points."""
    if count >= max_iter:
        return INSIDE_CHAR
    return GRADIENT[count * (len(GRADIENT) - 1) // max_iter]


def render_ascii(view, width, height, max_iter=100):
    """Render the view as a list of height strings, each width chars."""
    rows = []
    for py in range(height):
        row = []
        for px in range(width):
            c = map_pixel(px, py, width, height, view)
            row.append(ascii_char(escape_count(c, max_iter), max_iter))
        rows.append("".join(row))
    return rows


def palette_color(count, max_iter, palette="grayscale"):
    """RGB colour for an escape count; inside points are black."""
    if palette not in PALETTES:
        raise ValueError("unknown palette: %r" % (palette,))
    if count >= max_iter:
        return INSIDE_RGB
    stops = PALETTES[palette]
    pos = count / max_iter * (len(stops) - 1)
    i = min(int(pos), len(stops) - 2)
    frac = pos - i
    r0, g0, b0 = stops[i]
    r1, g1, b1 = stops[i + 1]
    return (
        round(r0 + (r1 - r0) * frac),
        round(g0 + (g1 - g0) * frac),
        round(b0 + (b1 - b0) * frac),
    )


def _chunk(chunk_type, data):
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def render_png_bytes(view, width, height, max_iter=100, palette="grayscale", dpi=72):
    """Encode the view as PNG bytes (true-colour, filter 0 per scanline)."""
    raw = bytearray()
    for py in range(height):
        raw.append(0)  # no filter
        for px in range(width):
            c = map_pixel(px, py, width, height, view)
            raw.extend(palette_color(escape_count(c, max_iter), max_iter, palette))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ppm = round(dpi * PIXELS_PER_METRE_PER_DPI)
    phys = struct.pack(">IIB", ppm, ppm, 1)  # unit: metre
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"pHYs", phys)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + _chunk(b"IEND", b"")
    )


def write_png(path, view, width, height, max_iter=100, palette="grayscale", dpi=72):
    """Write the view as a PNG file."""
    with open(path, "wb") as fh:
        fh.write(render_png_bytes(view, width, height, max_iter, palette, dpi))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Explore the Mandelbrot set as ASCII art or a PNG file."
    )
    parser.add_argument("--width", type=int, default=None,
                        help="output width in characters/pixels "
                        "(default 80 for ASCII, 800 for PNG)")
    parser.add_argument("--height", type=int, default=None,
                        help="output height in characters/pixels "
                        "(default 40 for ASCII, 800 for PNG)")
    parser.add_argument("--max-iter", type=int, default=100,
                        help="escape-time iterations (default 100)")
    parser.add_argument("--box", type=float, nargs=4, metavar=("XMIN", "XMAX", "YMIN", "YMAX"),
                        help="complex-plane bounding box to render (wins over --center/--zoom)")
    parser.add_argument("--center", type=float, nargs=2, default=(0.0, 0.0),
                        metavar=("CX", "CY"), help="zoom centre (default 0 0)")
    parser.add_argument("--zoom", type=float, default=1.0,
                        help="magnification around --center; >1 zooms in (default 1)")
    parser.add_argument("--palette", default="grayscale",
                        choices=sorted(PALETTES),
                        help="PNG colour palette (default grayscale)")
    parser.add_argument("--output", metavar="FILE.png",
                        help="write a PNG file instead of ASCII art")
    parser.add_argument("--dpi", type=int, default=72,
                        help="PNG DPI metadata, e.g. 72 for web, 300 for a poster (default 72)")
    args = parser.parse_args(argv)
    if args.width is not None and args.width <= 0:
        parser.error("--width must be positive")
    if args.height is not None and args.height <= 0:
        parser.error("--height must be positive")
    if args.max_iter <= 0:
        parser.error("--max-iter must be positive")
    if args.zoom <= 0:
        parser.error("--zoom must be positive")
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    if args.box is not None:
        xmin, xmax, ymin, ymax = args.box
        if xmin >= xmax or ymin >= ymax:
            parser.error("--box needs xmin < xmax and ymin < ymax")
    if args.output is not None and not args.output.endswith(".png"):
        parser.error("--output must end in .png")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.box is not None:
        view = tuple(args.box)
    elif args.zoom != 1.0 or args.center != (0.0, 0.0):
        view = zoom_view(DEFAULT_VIEW, args.center[0], args.center[1], args.zoom)
    else:
        view = DEFAULT_VIEW
    if args.output is not None:
        width = args.width if args.width is not None else 800
        height = args.height if args.height is not None else 800
        write_png(args.output, view, width, height,
                  args.max_iter, args.palette, args.dpi)
    else:
        width = args.width if args.width is not None else 80
        height = args.height if args.height is not None else 40
        for row in render_ascii(view, width, height, args.max_iter):
            print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
