#!/usr/bin/env python3
"""LinkedIn Carousel Generator — Coding Challenges entry 21.

Turns a plain-text deck into a multi-page PDF carousel (one 1080x1080
page per slide) and an HTML preview with the same slides and
navigation. Python 3 standard library only.

Deck format: slides separated by a line containing exactly ``---``.
The first non-empty line of a slide is its title (a leading ``# ``
is stripped); the rest are body lines, ``- `` lines are bullets.
A slide may start with a ``!bg <path> [opacity]`` directive for a
per-slide background image (JPEG only in PDF output; default
opacity 0.15).

PDF output is produced by a minimal hand-written writer: the standard
library has no PDF library, and base-14 fonts need no embedding, so
the whole writer fits in this file. JPEG images are embedded
verbatim with /DCTDecode; PNGs are rejected for PDF with a clear
error (they still work in the HTML preview, where the browser
decodes them).
"""

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass, field

PAGE = 1080            # slide size in points (PDF) / px (HTML preview)
MARGIN = 90
ALLOWED_FONTS = ("Helvetica", "Helvetica-Bold", "Times-Roman", "Courier")
DEFAULT_BG_OPACITY = 0.15


class CarouselError(ValueError):
    """User-facing error: bad input, bad option, or unsupported file."""


# ---------------------------------------------------------------- theme

@dataclass
class Theme:
    bg: tuple = (255, 255, 255)
    fg: tuple = (17, 17, 17)
    font: str = "Helvetica"
    font_size: int = 36
    author: str = ""
    handle: str = ""
    avatar: str = ""


@dataclass
class Slide:
    title: str = ""
    body: list = field(default_factory=list)
    bg_image: str = ""
    bg_opacity: float = DEFAULT_BG_OPACITY


@dataclass
class TextLine:
    text: str
    x: float
    y: float
    size: float


def parse_hex(value):
    """'#RRGGBB' or 'RRGGBB' -> (r, g, b); raises CarouselError."""
    s = value.strip()
    if s.startswith("#"):
        s = s[1:]
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        raise CarouselError(f"invalid colour {value!r}: expected RRGGBB hex")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _rgb01(rgb):
    return " ".join(f"{c / 255:.4f}" for c in rgb)


# ---------------------------------------------------------------- parsing

def parse_deck(text):
    """Parse deck text into a list of Slides; raises CarouselError."""
    slides = []
    for chunk in re.split(r"(?m)^\s*---\s*$", text):
        lines = [ln.rstrip() for ln in chunk.splitlines()]
        bg_image, bg_opacity = "", DEFAULT_BG_OPACITY
        if lines and lines[0].strip().startswith("!bg"):
            parts = lines[0].strip().split()
            if len(parts) < 2:
                raise CarouselError("!bg directive needs an image path")
            bg_image = parts[1]
            if len(parts) > 2:
                try:
                    bg_opacity = float(parts[2])
                except ValueError:
                    raise CarouselError(f"bad !bg opacity {parts[2]!r}")
                if not 0.0 <= bg_opacity <= 1.0:
                    raise CarouselError("!bg opacity must be between 0 and 1")
            lines = lines[1:]
        non_empty = [ln for ln in lines if ln.strip()]
        if not non_empty:
            continue  # empty chunk (e.g. leading/trailing separator)
        title = re.sub(r"^#{1,2}\s+", "", non_empty[0].strip())
        slides.append(Slide(title=title, body=non_empty[1:],
                            bg_image=bg_image, bg_opacity=bg_opacity))
    if not slides:
        raise CarouselError("deck is empty: no slide with any text found")
    return slides


# ---------------------------------------------------------------- wrapping

def _estimate_width(text, font_size, factor):
    return len(text) * font_size * factor


def wrap_text(text, max_width, font_size, factor=0.5):
    """Greedy word wrap on an estimated character width.

    Over-long words are hard-split so no returned line exceeds the
    width estimate (within one character). Empty text -> [].
    """
    if not text.strip():
        return []
    lines, current = [], ""
    for word in text.split():
        trial = word if not current else current + " " + word
        if _estimate_width(trial, font_size, factor) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        # Hard-split a word that alone exceeds the width.
        while _estimate_width(word, font_size, factor) > max_width:
            per_line = max(1, int(max_width // (font_size * factor)))
            lines.append(word[:per_line])
            word = word[per_line:]
        current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------- layout

def layout_slide(slide, theme, index, total):
    """Pure layout: slide -> list of TextLine (points, origin bottom-left).

    Title at the top (below the author row when an author is set),
    body below it, footer ``N / total`` bottom-right. All coordinates
    stay inside the 1080x1080 page.
    """
    lines = []
    width = PAGE - 2 * MARGIN
    y = PAGE - MARGIN
    if theme.author:
        label = theme.author + (f"  {theme.handle}" if theme.handle else "")
        lines.append(TextLine(label, MARGIN, y - 28, 28))
        y -= 90
    else:
        y -= 40
    title_size = round(theme.font_size * 1.6)
    for wrapped in wrap_text(slide.title, width, title_size, 0.55):
        y -= title_size * 1.25
        lines.append(TextLine(wrapped, MARGIN, y, title_size))
    y -= theme.font_size * 0.8
    for raw in slide.body:
        # Keep the "- " marker: the bullet glyph U+2022 is outside the
        # Latin-1 coverage of base-14 PDF fonts and would render as "?".
        body_text = raw
        for wrapped in wrap_text(body_text, width, theme.font_size):
            y -= theme.font_size * 1.35
            lines.append(TextLine(wrapped, MARGIN, y, theme.font_size))
    footer = f"{index + 1} / {total}"
    fx = PAGE - MARGIN - _estimate_width(footer, 24, 0.5)
    lines.append(TextLine(footer, fx, MARGIN - 30, 24))
    return lines


# ---------------------------------------------------------------- JPEG

def jpeg_dimensions(path):
    """(width, height) of a JPEG file; raises CarouselError otherwise."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise CarouselError(f"cannot read image {path!r}: {exc.strerror}")
    if data[:2] != b"\xff\xd8":
        raise CarouselError(
            f"image {path!r} is not a JPEG (only JPEG can be embedded "
            "in PDF output; use the HTML preview for other formats)")
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 4 > len(data):
            break
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):  # SOF: precision, H, W
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            return width, height
        i += 2 + length
    raise CarouselError(f"could not parse JPEG dimensions of {path!r}")


def _read_jpeg(path):
    width, height = jpeg_dimensions(path)
    with open(path, "rb") as fh:
        return width, height, fh.read()


# ---------------------------------------------------------------- PDF

def _pdf_escape(text):
    out = text.encode("latin-1", errors="replace").decode("latin-1")
    return out.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(deck, theme):
    """Deck + theme -> PDF bytes, one 1080x1080 page per slide."""
    if theme.font not in ALLOWED_FONTS:
        raise CarouselError(f"unknown font {theme.font!r}; "
                            f"choose one of {', '.join(ALLOWED_FONTS)}")
    if theme.font_size <= 0:
        raise CarouselError("font size must be positive")

    # Collect image XObjects (deduplicated by path) and opacity states.
    images = {}   # path -> (obj_id placeholder, width, height, bytes)
    for slide in deck:
        for path in (slide.bg_image, theme.avatar):
            if path and path not in images:
                images[path] = _read_jpeg(path)

    objects = []  # 1-based: objects[i-1] is object i

    def add(body):
        objects.append(body)
        return len(objects)

    font_id = add(f"<< /Type /Font /Subtype /Type1 "
                  f"/BaseFont /{theme.font} /Encoding /WinAnsiEncoding >>".encode())
    # Reserve ids: catalog=1? We add in order and patch the Pages object
    # below once page ids are known, so build pages first, then fix up.
    page_ids, content_ids = [], []
    image_ids = {p: add(b"") for p in images}  # placeholders, filled below
    gs_ids = {}
    for slide in deck:
        if slide.bg_image and slide.bg_opacity not in gs_ids:
            gs_ids[slide.bg_opacity] = add(
                f"<< /Type /ExtGState /ca {slide.bg_opacity:.4f} >>".encode())
    for idx, slide in enumerate(deck):
        parts = [f"{_rgb01(theme.bg)} rg 0 0 {PAGE} {PAGE} re f"]
        if slide.bg_image:
            # Full-bleed: scale the image unit square to the whole page.
            parts.append(f"q {PAGE} 0 0 {PAGE} 0 0 cm "
                         f"/GS{slide.bg_opacity} gs "
                         f"/Im{image_ids[slide.bg_image]} Do Q")
        if theme.avatar:
            # Square avatar, top-left, above the author line.
            parts.append(f"q 64 0 0 64 {MARGIN} {PAGE - MARGIN - 64} cm "
                         f"/Im{image_ids[theme.avatar]} Do Q")
        for line in layout_slide(slide, theme, idx, len(deck)):
            parts.append(
                f"BT /F1 {line.size} Tf {_rgb01(theme.fg)} rg "
                f"{line.x:.1f} {line.y:.1f} Td "
                f"({_pdf_escape(line.text)}) Tj ET")
        stream = "\n".join(parts).encode("latin-1", errors="replace")
        content_ids.append(add(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream"))
    for idx in range(len(deck)):
        resources = [f"/Font << /F1 {font_id} 0 R >>"]
        xobjects = {}
        if deck[idx].bg_image:
            xobjects[f"Im{image_ids[deck[idx].bg_image]}"] = image_ids[deck[idx].bg_image]
        if theme.avatar:
            xobjects[f"Im{image_ids[theme.avatar]}"] = image_ids[theme.avatar]
        if xobjects:
            resources.append("/XObject << " + " ".join(
                f"/{name} {oid} 0 R" for name, oid in xobjects.items()) + " >>")
        gs = ""
        if deck[idx].bg_image:
            gs = (f"/ExtGState << /GS{deck[idx].bg_opacity} "
                  f"{gs_ids[deck[idx].bg_opacity]} 0 R >>")
            resources.append(gs)
        page_ids.append(add(
            f"<< /Type /Page /Parent PAGESREF 0 R "
            f"/MediaBox [0 0 {PAGE} {PAGE}] "
            f"/Resources << {' '.join(resources)} >> "
            f"/Contents {content_ids[idx]} 0 R >>".encode()))
    pages_id = add(
        ("<< /Type /Pages /Kids [" + " ".join(f"{p} 0 R" for p in page_ids)
         + f"] /Count {len(page_ids)} >>").encode())
    catalog_id = add(
        f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    # Patch the parent reference in every page object.
    for pid in page_ids:
        objects[pid - 1] = objects[pid - 1].replace(b"PAGESREF", str(pages_id).encode())
    # Fill the image placeholders with real XObjects.
    for path, oid in image_ids.items():
        width, height, raw = images[path]
        objects[oid - 1] = (
            f"<< /Type /XObject /Subtype /Image /Width {width} "
            f"/Height {height} /ColorSpace /DeviceRGB "
            f"/BitsPerComponent 8 /Filter /DCTDecode "
            f"/Length {len(raw)} >>\nstream\n".encode() + raw + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} "
            f"/Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


# ---------------------------------------------------------------- HTML

def build_html(deck, theme):
    """Deck + theme -> a self-contained preview page (1080px slides)."""
    bg = "#%02x%02x%02x" % theme.bg
    fg = "#%02x%02x%02x" % theme.fg
    font_css = {"Helvetica": "Helvetica, Arial, sans-serif",
                "Helvetica-Bold": "Helvetica, Arial, sans-serif",
                "Times-Roman": "Georgia, 'Times New Roman', serif",
                "Courier": "'Courier New', monospace"}[theme.font]
    weight = "bold" if theme.font == "Helvetica-Bold" else "normal"
    slides_html = []
    for idx, slide in enumerate(deck):
        title = html.escape(slide.title)
        body = "".join(
            f"<p>{html.escape(line)}</p>\n" for line in slide.body)
        img = ""
        if slide.bg_image:
            img = (f'<img class="bg" src="{html.escape(slide.bg_image, quote=True)}" '
                   f'style="opacity:{slide.bg_opacity}" alt="">')
        avatar = ""
        if theme.avatar:
            avatar = (f'<img class="avatar" src="{html.escape(theme.avatar, quote=True)}" alt="">')
        author = html.escape(
            theme.author + (f"  {theme.handle}" if theme.handle else ""))
        slides_html.append(
            f'<section class="slide" data-slide="{idx}">\n{img}\n'
            f'<div class="inner">{avatar}'
            f'<div class="author">{author}</div>\n'
            f'<h1>{title}</h1>\n{body}'
            f'<div class="footer">{idx + 1} / {len(deck)}</div></div>\n</section>')
    slides_joined = "\n".join(slides_html)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Carousel preview</title>
<style>
body {{ font-family: {font_css}; background: #222; margin: 0; }}
nav {{ text-align: center; padding: 12px; color: #fff; }}
nav button {{ font-size: 18px; padding: 6px 18px; }}
.slide {{ width: 1080px; height: 1080px; margin: 0 auto 24px auto;
  background: {bg}; color: {fg}; position: relative; overflow: hidden;
  font-weight: {weight}; display: none; }}
.slide.active {{ display: block; }}
.slide img.bg {{ position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; }}
.slide .inner {{ position: relative; padding: 90px; }}
.slide img.avatar {{ width: 64px; height: 64px; object-fit: cover; }}
.slide .author {{ font-size: 28px; margin: 8px 0 40px 0; }}
.slide h1 {{ font-size: {round(theme.font_size * 1.6)}px; margin: 0 0 30px 0; }}
.slide p {{ font-size: {theme.font_size}px; line-height: 1.35; }}
.slide .footer {{ position: absolute; right: 90px; bottom: 60px; font-size: 24px; }}
</style></head><body>
<nav><button id="prev">‹ Prev</button>
<span id="counter">1 / {len(deck)}</span>
<button id="next">Next ›</button></nav>
{slides_joined}
<script>
let cur = 0; const slides = document.querySelectorAll('.slide');
const counter = document.getElementById('counter');
function show(i) {{ cur = (i + slides.length) % slides.length;
  slides.forEach((s, j) => s.classList.toggle('active', j === cur));
  counter.textContent = (cur + 1) + ' / ' + slides.length; }}
document.getElementById('prev').onclick = () => show(cur - 1);
document.getElementById('next').onclick = () => show(cur + 1);
show(0);
</script></body></html>
"""


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a LinkedIn carousel PDF + HTML preview from text.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build the carousel")
    build.add_argument("input", help="deck text file")
    build.add_argument("--pdf", default="carousel.pdf", help="PDF output path")
    build.add_argument("--preview", default=None, help="HTML preview path")
    build.add_argument("--bg", default="ffffff", help="background hex colour")
    build.add_argument("--fg", default="111111", help="foreground hex colour")
    build.add_argument("--font", default="Helvetica",
                       choices=ALLOWED_FONTS, help="base-14 font")
    build.add_argument("--font-size", type=int, default=36)
    build.add_argument("--author", default="")
    build.add_argument("--handle", default="")
    build.add_argument("--avatar", default="")
    args = parser.parse_args(argv)

    try:
        if not os.path.isfile(args.input):
            raise CarouselError(f"input file not found: {args.input}")
        with open(args.input, encoding="utf-8") as fh:
            deck = parse_deck(fh.read())
        theme = Theme(bg=parse_hex(args.bg), fg=parse_hex(args.fg),
                      font=args.font, font_size=args.font_size,
                      author=args.author, handle=args.handle,
                      avatar=args.avatar)
        pdf_bytes = build_pdf(deck, theme)
        preview = build_html(deck, theme) if args.preview else None
    except CarouselError as exc:
        print(f"carousel: error: {exc}", file=sys.stderr)
        return 1
    with open(args.pdf, "wb") as fh:
        fh.write(pdf_bytes)
    if args.preview:
        with open(args.preview, "w", encoding="utf-8") as fh:
            fh.write(preview)
    print(f"{len(deck)} slides -> {args.pdf}"
          + (f" + {args.preview}" if args.preview else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
