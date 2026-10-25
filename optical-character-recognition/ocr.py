#!/usr/bin/env python3
"""Stdlib-only OCR tool for Coding Challenge #80.

Pipeline: load (PNG or Netpbm) -> greyscale -> Otsu binarisation
-> optional deskew -> connected-component segmentation -> line grouping
-> 5x7 template matching -> text on stdout.

Supported character set: uppercase A-Z and digits 0-9, in the built-in
5x7 bitmap font FONT below. Anything else that segments cleanly but
matches no template within MAX_DISTANCE is reported as '?'.
No neural networks, no trained models, no LLMs, no third-party libs.
"""

import argparse
import math
import struct
import sys
import zlib
from collections import deque

# ---------------------------------------------------------------- font
# Each glyph: 7 rows of 5 cells, '#' = ink, '.' = background.
FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "##..#", "#.#.#", "#..##", "#..##", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#..##", "#.#.#", "##..#", "#...#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": (".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "...#.", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
}

TEMPLATES = {ch: tuple(1 if c == "#" else 0 for row in rows for c in row)
             for ch, rows in FONT.items()}
MAX_DISTANCE = 6  # out of 35 cells; see DESIGN.md section 6

# ---------------------------------------------------------------- loading


def _netpbm_tokens(data, pos, count):
    """Read `count` whitespace-separated tokens, skipping # comments."""
    tokens = []
    n = len(data)
    while len(tokens) < count:
        while pos < n and chr(data[pos]) in " \t\r\n":
            pos += 1
        if pos < n and data[pos:pos + 1] == b"#":
            while pos < n and data[pos:pos + 1] != b"\n":
                pos += 1
            continue
        if pos >= n:
            raise ValueError("truncated Netpbm header")
        start = pos
        while pos < n and chr(data[pos]) not in " \t\r\n":
            pos += 1
        tokens.append(data[start:pos].decode("ascii"))
    return tokens, pos


def _rgb_grey(r, g, b, maxval):
    return (299 * r + 587 * g + 114 * b) // 1000 * 255 // maxval


def parse_netpbm(data):
    """Return (width, height, greyscale rows) for P1-P6 data."""
    if len(data) < 2 or data[0:1] != b"P" or chr(data[1]) not in "123456":
        raise ValueError("not a Netpbm (P1-P6) file")
    kind = chr(data[1])
    tokens, pos = _netpbm_tokens(data, 2, 2 if kind in "14" else 3)
    width, height = int(tokens[0]), int(tokens[1])
    maxval = 1 if kind in "14" else int(tokens[2])
    if width <= 0 or height <= 0 or maxval <= 0:
        raise ValueError("invalid Netpbm dimensions/maxval")
    if kind in "123":  # ASCII
        per_px = 3 if kind == "3" else 1
        values, _ = _netpbm_tokens(data, pos, width * height * per_px)
        it = iter(values)
        grey = []
        for _ in range(height):
            row = []
            for _ in range(width):
                if kind == "3":
                    row.append(_rgb_grey(int(next(it)), int(next(it)), int(next(it)), maxval))
                elif kind == "2":
                    row.append(int(next(it)) * 255 // maxval)
                else:
                    row.append(0 if int(next(it)) else 255)
            grey.append(row)
        return width, height, grey
    # raw: exactly one whitespace byte follows maxval, then bytes
    pos += 1
    if kind == "4":
        row_bytes = (width + 7) // 8
        body = data[pos:pos + row_bytes * height]
        if len(body) < row_bytes * height:
            raise ValueError("truncated PBM body")
        grey = []
        for y in range(height):
            row = []
            for x in range(width):
                bit = (body[y * row_bytes + x // 8] >> (7 - x % 8)) & 1
                row.append(0 if bit else 255)
            grey.append(row)
        return width, height, grey
    channels = 3 if kind == "6" else 1
    need = width * height * channels
    body = data[pos:pos + need]
    if len(body) < need:
        raise ValueError("truncated Netpbm body")
    grey, idx = [], 0
    for _ in range(height):
        row = []
        for _ in range(width):
            if kind == "6":
                row.append(_rgb_grey(body[idx], body[idx + 1], body[idx + 2], maxval))
                idx += 3
            else:
                row.append(body[idx] * 255 // maxval)
                idx += 1
        grey.append(row)
    return width, height, grey


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def parse_png(data):
    """Return (width, height, greyscale rows) for 8-bit non-interlaced
    PNG colour types 0, 2, 6. Raises ValueError otherwise."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, width, height, bit_depth, color_type, interlace = 8, None, None, None, None, None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if len(chunk) < length:
            raise ValueError("truncated PNG chunk")
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
            interlace = chunk[12]
        elif ctype == b"IDAT":
            idat.extend(chunk)
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if width is None:
        raise ValueError("PNG missing IHDR")
    if interlace != 0:
        raise ValueError("interlaced PNG not supported")
    if bit_depth != 8:
        raise ValueError("only 8-bit PNG supported, got bit depth %d" % bit_depth)
    channels = {0: 1, 2: 3, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError("only PNG colour types 0, 2, 6 supported, got %d" % color_type)
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    grey, prev = [], bytearray(stride)
    off = 0
    for _ in range(height):
        if off + 1 + stride > len(raw):
            raise ValueError("truncated PNG pixel data")
        ftype, line = raw[off], bytearray(raw[off + 1:off + 1 + stride])
        off += 1 + stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if ftype == 0:
                pass
            elif ftype == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ftype == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ftype == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
            else:
                raise ValueError("unknown PNG filter type %d" % ftype)
        row = []
        for x in range(width):
            px = line[x * channels:(x + 1) * channels]
            if channels == 1:
                row.append(px[0])
            elif channels == 3:
                row.append((299 * px[0] + 587 * px[1] + 114 * px[2]) // 1000)
            else:  # RGBA over white
                alpha = px[3] / 255.0
                r = int(px[0] * alpha + 255 * (1 - alpha))
                g = int(px[1] * alpha + 255 * (1 - alpha))
                b = int(px[2] * alpha + 255 * (1 - alpha))
                row.append((299 * r + 587 * g + 114 * b) // 1000)
        grey.append(row)
        prev = line
    return width, height, grey


def load_image(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return parse_png(data)
    if len(data) >= 2 and data[0:1] == b"P" and chr(data[1]) in "123456":
        return parse_netpbm(data)
    raise ValueError("unsupported image format (need PNG or Netpbm P1-P6)")

# ---------------------------------------------------------------- pipeline


def otsu_threshold(grey):
    hist = [0] * 256
    total = 0
    for row in grey:
        for v in row:
            hist[v] += 1
            total += 1
    sum_all = sum(i * hist[i] for i in range(256))
    sum_b = w_b = 0
    best, best_t = -1.0, 0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, best_t = between, t
    return best_t


def binarize(grey, threshold=None, invert=False):
    if threshold is None:
        threshold = otsu_threshold(grey)
    out = []
    for row in grey:
        if invert:
            # Strict > : Otsu can return 0 for a bimodal 0/255 image, and
            # >= 0 would mark every pixel as ink. See TEST_PLAN notes.
            out.append([1 if v > threshold else 0 for v in row])
        else:
            out.append([1 if v <= threshold else 0 for v in row])
    return out


def rotate_binary(binary, angle_deg):
    """Rotate about the centre, nearest neighbour, same canvas size."""
    h, w = len(binary), len(binary[0]) if binary else 0
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            # inverse rotation: where did this dest pixel come from?
            dx, dy = x - cx, y - cy
            sx = int(round(cx + dx * cos_a + dy * sin_a))
            sy = int(round(cy - dx * sin_a + dy * cos_a))
            if 0 <= sx < w and 0 <= sy < h:
                out[y][x] = binary[sy][sx]
    return out


def _projection_score(binary):
    return sum(sum(row) ** 2 for row in binary)


def deskew_angle(binary):
    """Search -10..+10 degrees; return the best correction angle."""
    best_score, best_angle = _projection_score(binary), 0
    for angle in range(-10, 11):
        if angle == 0:
            continue
        score = _projection_score(rotate_binary(binary, angle))
        if score > best_score or (score == best_score and abs(angle) < abs(best_angle)):
            best_score, best_angle = score, angle
    return best_angle


def deskew(binary):
    """Search -10..+10 degrees; return (corrected_binary, angle_applied).

    Binary rotation is used for the angle search and for this helper;
    the full pipeline instead corrects the greyscale image (see
    rotate_grey) because re-sampling a binary image twice fragments
    thin diagonal strokes (W, R, ...)."""
    angle = deskew_angle(binary)
    return (rotate_binary(binary, angle) if angle else binary), angle


def rotate_grey(grey, angle_deg):
    """Rotate a greyscale image about its centre with bilinear
    interpolation; out-of-canvas samples read as white (255)."""
    h, w = len(grey), len(grey[0]) if grey else 0
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            dx, dy = x - cx, y - cy
            sx = cx + dx * cos_a + dy * sin_a
            sy = cy - dx * sin_a + dy * cos_a
            x0, y0 = int(math.floor(sx)), int(math.floor(sy))
            fx, fy = sx - x0, sy - y0
            def px(xx, yy):
                return grey[yy][xx] if 0 <= xx < w and 0 <= yy < h else 255
            top = px(x0, y0) * (1 - fx) + px(x0 + 1, y0) * fx
            bot = px(x0, y0 + 1) * (1 - fx) + px(x0 + 1, y0 + 1) * fx
            row.append(int(round(top * (1 - fy) + bot * fy)))
        out.append(row)
    return out


def deskewed_binary(grey, threshold=None, invert=False):
    """Binarise, find the deskew angle, then correct the GREYSCALE
    image with bilinear interpolation and re-binarise. Correcting the
    greyscale image preserves thin strokes that binary re-sampling
    would fragment."""
    binary = binarize(grey, threshold, invert)
    angle = deskew_angle(binary)
    if angle == 0:
        return binary
    return binarize(rotate_grey(grey, angle), threshold, invert)


def segment(binary):
    """Connected components (8-connectivity). Returns blob dicts with
    x, y, w, h and bitmap (list of rows of 0/1)."""
    h, w = len(binary), len(binary[0]) if binary else 0
    seen = [[False] * w for _ in range(h)]
    blobs = []
    for y in range(h):
        for x in range(w):
            if binary[y][x] and not seen[y][x]:
                queue = deque([(x, y)])
                seen[y][x] = True
                pixels = []
                min_x = max_x = x
                min_y = max_y = y
                while queue:
                    px, py = queue.popleft()
                    pixels.append((px, py))
                    min_x, max_x = min(min_x, px), max(max_x, px)
                    min_y, max_y = min(min_y, py), max(max_y, py)
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = px + dx, py + dy
                            if 0 <= nx < w and 0 <= ny < h and binary[ny][nx] and not seen[ny][nx]:
                                seen[ny][nx] = True
                                queue.append((nx, ny))
                bw, bh = max_x - min_x + 1, max_y - min_y + 1
                if bw < 2 or bh < 3 or len(pixels) < 4:
                    continue  # speck noise, not a character
                bitmap = [[0] * bw for _ in range(bh)]
                for px, py in pixels:
                    bitmap[py - min_y][px - min_x] = 1
                blobs.append({"x": min_x, "y": min_y, "w": bw, "h": bh,
                              "bitmap": bitmap, "count": len(pixels)})
    return blobs


def normalize_to_5x7(bitmap):
    """Resample a blob bitmap to 5x7 by majority vote per cell.

    The blob bitmap is tight-cropped, so its width alone does not tell
    where it sat in the 5-wide glyph cell: a narrow glyph such as 'I'
    (ink in columns 1-3 only) must NOT be stretched to fill all 5
    columns. Instead the glyph cell width is derived from the height
    (every glyph spans all 7 rows, so cell width = height * 5 / 7),
    the blob is centred in that cell, and the cell is resampled.
    """
    bh, bw = len(bitmap), len(bitmap[0])
    cell_w = max(bw, int(round(bh * 5 / 7.0)))
    offset = (cell_w - bw) // 2
    canvas = [[0] * cell_w for _ in range(bh)]
    for y in range(bh):
        for x in range(bw):
            canvas[y][x + offset] = bitmap[y][x]
    out = []
    for gy in range(7):
        for gx in range(5):
            y0, y1 = gy * bh // 7, (gy + 1) * bh // 7
            x0, x1 = gx * cell_w // 5, (gx + 1) * cell_w // 5
            votes = total = 0
            for yy in range(y0, max(y1, y0 + 1)):
                for xx in range(x0, max(x1, x0 + 1)):
                    votes += canvas[yy][xx]
                    total += 1
            out.append(1 if total and votes * 2 >= total else 0)
    return tuple(out)


def recognize_blob(blob):
    grid = normalize_to_5x7(blob["bitmap"])
    best_ch, best_d = "?", MAX_DISTANCE + 1
    for ch, tmpl in TEMPLATES.items():
        d = sum(1 for a, b in zip(grid, tmpl) if a != b)
        if d < best_d:
            best_ch, best_d = ch, d
    return best_ch if best_d <= MAX_DISTANCE else "?"


def group_lines(blobs):
    """Assign a character to each blob and group into lines of text.
    Returns (lines, results) where lines are strings and results are
    (char, x, y, w, h) tuples in reading order."""
    if not blobs:
        return [], []
    for blob in blobs:
        blob["char"] = recognize_blob(blob)
    blobs = sorted(blobs, key=lambda b: (b["y"] + b["h"] / 2.0, b["x"]))
    lines, current, cur_span = [], [], None
    for blob in blobs:
        cy = blob["y"] + blob["h"] / 2.0
        if cur_span is None or not (cur_span[0] <= cy <= cur_span[1]):
            if current:
                lines.append(current)
            current = [blob]
            med_h = blob["h"]
            cur_span = (blob["y"] - med_h / 2.0, blob["y"] + blob["h"] + med_h / 2.0)
        else:
            current.append(blob)
            lo = min(cur_span[0], blob["y"] - blob["h"] / 2.0)
            hi = max(cur_span[1], blob["y"] + blob["h"] + blob["h"] / 2.0)
            cur_span = (lo, hi)
    if current:
        lines.append(current)
    out_lines, results = [], []
    for line in lines:
        line = sorted(line, key=lambda b: b["x"])
        widths = sorted(b["w"] for b in line)
        med_w = widths[len(widths) // 2]
        space_at = max(3, int(0.8 * med_w))
        text, prev = "", None
        for blob in line:
            if prev is not None and blob["x"] - (prev["x"] + prev["w"]) >= space_at:
                text += " "
            text += blob["char"]
            results.append((blob["char"], blob["x"], blob["y"], blob["w"], blob["h"]))
            prev = blob
        out_lines.append(text)
    return out_lines, results


def recognize(grey, threshold=None, use_deskew=False, invert=False):
    binary = deskewed_binary(grey, threshold, invert) if use_deskew else binarize(grey, threshold, invert)
    blobs = segment(binary)
    return group_lines(blobs)


# ---------------------------------------------------------------- rendering


def render_text(text, scale=2, char_gap=None, word_gap=None):
    """Render text with FONT into a binary image (list of rows of 0/1).
    Used by the test suite for exact synthetic fixtures."""
    if char_gap is None:
        char_gap = scale
    if word_gap is None:
        word_gap = 4 * scale
    lines = text.split("\n")
    cell_w, cell_h = 5 * scale, 7 * scale
    width = 0
    for line in lines:
        wline = 0
        for i, ch in enumerate(line):
            if ch == " ":
                wline += word_gap
            else:
                wline += cell_w
                if i + 1 < len(line):
                    wline += char_gap
        width = max(width, wline)
    height = len(lines) * cell_h + (len(lines) - 1) * (2 * scale)
    img = [[0] * width for _ in range(height)]
    for li, line in enumerate(lines):
        y0 = li * (cell_h + 2 * scale)
        x = 0
        for ch in line:
            if ch == " ":
                x += word_gap
                continue
            rows = FONT.get(ch)
            if rows is None:
                x += cell_w + char_gap
                continue
            for gy, row in enumerate(rows):
                for gx, cell in enumerate(row):
                    if cell == "#":
                        for dy in range(scale):
                            for dx in range(scale):
                                img[y0 + gy * scale + dy][x + gx * scale + dx] = 1
            x += cell_w + char_gap
    return img


def to_pbm_bytes(binary):
    h, w = len(binary), len(binary[0]) if binary else 0
    out = bytearray("P4\n%d %d\n" % (w, h), "ascii")
    row_bytes = (w + 7) // 8
    for row in binary:
        buf = bytearray(row_bytes)
        for x, v in enumerate(row):
            if v:
                buf[x // 8] |= 1 << (7 - x % 8)
        out.extend(buf)
    return bytes(out)


def draw_boxes(binary, results):
    """Return a copy of binary with a 1-px box around each result box."""
    img = [row[:] for row in binary]
    h, w = len(img), len(img[0]) if img else 0
    for _ch, x, y, bw, bh in results:
        for xx in range(x, min(x + bw, w)):
            if 0 <= y - 1 < h:
                img[y - 1][xx] = 1
            if 0 <= y + bh < h:
                img[y + bh][xx] = 1
        for yy in range(y, min(y + bh, h)):
            if 0 <= x - 1 < w:
                img[yy][x - 1] = 1
            if 0 <= x + bw < w:
                img[yy][x + bw] = 1
    return img


# ---------------------------------------------------------------- CLI


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stdlib-only OCR: PNG/Netpbm -> text (A-Z, 0-9 bitmap font).")
    parser.add_argument("input", help="PNG or Netpbm image file")
    parser.add_argument("--threshold", type=int, default=None, help="fixed binarisation threshold 0-255 (default: Otsu)")
    parser.add_argument("--deskew", action="store_true", help="correct skew up to +/-10 degrees")
    parser.add_argument("--boxes", action="store_true", help="print 'char x y w h' lines to stderr")
    parser.add_argument("--boxes-pbm", default=None, help="write a PBM with boxes drawn around characters")
    parser.add_argument("--invert", action="store_true", help="read light-on-dark images")
    args = parser.parse_args(argv)
    try:
        _w, _h, grey = load_image(args.input)
    except (OSError, ValueError, zlib.error, struct.error) as exc:
        print("ocr: %s" % exc, file=sys.stderr)
        return 1
    binary = deskewed_binary(grey, args.threshold, args.invert) if args.deskew else binarize(grey, args.threshold, args.invert)
    blobs = segment(binary)
    lines, results = group_lines(blobs)
    for line in lines:
        print(line)
    if args.boxes:
        for ch, x, y, w, h in results:
            print("%s %d %d %d %d" % (ch, x, y, w, h), file=sys.stderr)
    if args.boxes_pbm:
        try:
            with open(args.boxes_pbm, "wb") as fh:
                fh.write(to_pbm_bytes(draw_boxes(binary, results)))
        except OSError as exc:
            print("ocr: %s" % exc, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
