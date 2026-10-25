#!/usr/bin/env python3
"""md2pdf — Markdown To PDF Editor (codingchallenges.fyi, challenge-md-to-pdf).

Python 3 standard library only. Converts Markdown to a hand-written
PDF (base-14 fonts, no embedding) and to an HTML preview with the
same content and styling, and provides a terminal editing loop
(`edit`) and a file watcher (`watch`) in place of a GUI editor —
the challenge page explicitly allows a CLI + source-file + HTML
preview shape. See docs/SPEC.md, docs/DESIGN.md.
"""

import argparse
import html as html_lib
import os
import re
import sys
import time
from dataclasses import dataclass

# ---------------------------------------------------------------- AFM widths
# Widths per 1000 em for printable ASCII, from the core-font AFM data.
# Bold/oblique share the regular widths. Courier is fixed 600.
# Characters outside the table measure 556 (Helvetica) / 500 (Times).


def _helv_widths():
    w = {}
    vals = (
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
    )
    nums = (
        278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584,
        278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556,
        556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722,
        722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
        667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278,
        278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
        556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
        278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
    )
    for ch, n in zip(vals, nums):
        w[ch] = n
    return w


def _times_widths():
    w = {}
    vals = (
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
    )
    nums = (
        250, 333, 408, 500, 500, 833, 778, 180, 333, 333, 500, 564,
        250, 333, 250, 278, 500, 500, 500, 500, 500, 500, 500, 500,
        500, 500, 278, 278, 564, 564, 564, 444, 921, 722, 667, 667,
        722, 611, 556, 722, 722, 333, 389, 722, 611, 889, 722, 722,
        556, 722, 667, 556, 611, 722, 722, 944, 722, 722, 611, 333,
        278, 333, 469, 500, 333, 444, 500, 444, 500, 444, 333, 500,
        500, 278, 278, 500, 278, 778, 500, 500, 500, 500, 333, 389,
        278, 500, 500, 722, 500, 500, 444, 480, 200, 480, 541,
    )
    for ch, n in zip(vals, nums):
        w[ch] = n
    return w


HELV = _helv_widths()
TIMES = _times_widths()

FAMILIES = {
    "helvetica": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique",
                  "Helvetica-BoldOblique", HELV, 556),
    "times": ("Times-Roman", "Times-Bold", "Times-Italic",
              "Times-BoldItalic", TIMES, 500),
    "courier": ("Courier", "Courier-Bold", "Courier-Oblique",
                "Courier-BoldOblique", None, 600),
}
PAGE_SIZES = {"a4": (595, 842), "letter": (612, 792)}
MARGIN = 54


def text_width(text, family, size):
    """Width of *text* in points at *size* for base font *family*."""
    table, fallback = FAMILIES[family][4], FAMILIES[family][5]
    if table is None:
        return len(text) * 600 / 1000 * size
    return sum(table.get(ch, fallback) for ch in text) / 1000 * size


# ---------------------------------------------------------------- style


@dataclass
class Style:
    font: str = "helvetica"
    font_size: float = 12.0
    heading_scale: float = 1.0
    bg: tuple = (1.0, 1.0, 1.0)
    fg: tuple = (0.0, 0.0, 0.0)
    page: str = "a4"

    def heading_size(self, level):
        mult = {1: 2.0, 2: 1.67, 3: 1.33, 4: 1.17, 5: 1.0, 6: 0.92}
        return self.font_size * mult[level] * self.heading_scale

    def page_size(self):
        return PAGE_SIZES[self.page]


def parse_color(value):
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value or ""):
        raise ValueError(f"bad colour {value!r}: expected RRGGBB hex")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_str(rgb):
    return " ".join(f"{c:.3f}" for c in rgb)


# ---------------------------------------------------------------- inline parsing
# Span: (kind, text, url) kind in text/bold/italic/bolditalic/code/link/image


def _apply(spans, kind):
    out = []
    for k, t, u in spans:
        if k == "code" or k == "link" or k == "image":
            out.append((k, t, u))
        elif k == "bold" and kind == "italic":
            out.append(("bolditalic", t, u))
        elif k == "italic" and kind == "bold":
            out.append(("bolditalic", t, u))
        else:
            out.append((kind, t, u))
    return out


def _find_close(text, start, marker):
    """Index of a closing *marker* at/after start, or -1.

    For '_' the closer must not be followed by an alphanumeric
    (so snake_case is not emphasis).
    """
    i = start
    while True:
        j = text.find(marker, i)
        if j < 0:
            return -1
        if marker == "_" and j + 1 < len(text) and text[j + 1].isalnum():
            i = j + 1
            continue
        return j


def parse_inline(text):
    spans = []
    buf = []

    def flush():
        if buf:
            spans.append(("text", "".join(buf), None))
            buf.clear()

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # Inline code: contents are never re-scanned.
        if ch == "`":
            j = text.find("`", i + 1)
            if j < 0:
                buf.append(ch)
                i += 1
            else:
                flush()
                spans.append(("code", text[i + 1:j], None))
                i = j + 1
            continue
        # Image: ![alt](url)
        if ch == "!" and text.startswith("![", i):
            end = text.find("](", i + 2)
            if end >= 0:
                close = text.find(")", end + 2)
                if close >= 0:
                    flush()
                    spans.append(("image", text[i + 2:end],
                                  text[end + 2:close]))
                    i = close + 1
                    continue
            buf.append(ch)
            i += 1
            continue
        # Link: [text](url)
        if ch == "[":
            end = text.find("](", i + 1)
            if end >= 0:
                close = text.find(")", end + 2)
                if close >= 0:
                    flush()
                    spans.append(("link", text[i + 1:end],
                                  text[end + 2:close]))
                    i = close + 1
                    continue
            buf.append(ch)
            i += 1
            continue
        # Bold: ** or __
        if text.startswith("**", i) or text.startswith("__", i):
            marker = text[i:i + 2]
            j = _find_close(text, i + 2, marker)
            if j >= 0 and j > i + 2:
                flush()
                spans.extend(_apply(parse_inline(text[i + 2:j]), "bold"))
                i = j + 2
                continue
            buf.append(ch)
            i += 1
            continue
        # Italic: * or _ (single); '_' must not open inside a word.
        if ch in "*_":
            if ch == "_" and i > 0 and text[i - 1].isalnum():
                buf.append(ch)
                i += 1
                continue
            j = _find_close(text, i + 1, ch)
            if j >= 0 and j > i + 1:
                flush()
                spans.extend(_apply(parse_inline(text[i + 1:j]), "italic"))
                i = j + 1
                continue
            buf.append(ch)
            i += 1
            continue
        buf.append(ch)
        i += 1
    flush()
    return spans


# ---------------------------------------------------------------- block parsing
# Block: ("heading", level, spans) | ("para", spans) |
#        ("ul"|"ol", items) item = (spans, [subblocks]) |
#        ("code", text) | ("quote", spans) | ("hr",)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HR_RE = re.compile(r"^(---|\*\*\*|___)\s*$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


class Parser:
    def __init__(self, text):
        self.lines = text.splitlines()
        self.pos = 0

    def parse(self):
        blocks = []
        while self.pos < len(self.lines):
            if not self.lines[self.pos].strip():
                self.pos += 1
                continue
            blocks.append(self._block())
        return blocks

    def _block(self):
        line = self.lines[self.pos]
        stripped = line.strip()
        m = HEADING_RE.match(line)
        if m:
            self.pos += 1
            return ("heading", len(m.group(1)), parse_inline(m.group(2)))
        if line.startswith("```"):
            self.pos += 1
            code = []
            while self.pos < len(self.lines):
                if self.lines[self.pos].startswith("```"):
                    self.pos += 1
                    break
                code.append(self.lines[self.pos])
                self.pos += 1
            return ("code", "\n".join(code))
        if HR_RE.match(stripped):
            self.pos += 1
            return ("hr",)
        if stripped.startswith(">"):
            parts = []
            while self.pos < len(self.lines):
                s = self.lines[self.pos].strip()
                if not s.startswith(">"):
                    break
                parts.append(s[1:].lstrip())
                self.pos += 1
            return ("quote", parse_inline(" ".join(parts)))
        lm = LIST_RE.match(line)
        if lm:
            # A list line at any indent starts a list block here; the
            # recursive list parser handles nesting. (Indented code
            # blocks are not in scope, so no 4-space exception.)
            return self._list(len(lm.group(1)))
        # Paragraph: until a blank line or another block start.
        spans = []
        while self.pos < len(self.lines):
            cur = self.lines[self.pos]
            if not cur.strip():
                break
            if (HEADING_RE.match(cur) or cur.startswith("```")
                    or HR_RE.match(cur.strip())
                    or cur.strip().startswith(">")
                    or LIST_RE.match(cur)):
                break
            spans.extend(parse_inline(cur.rstrip()))
            hard = cur.endswith("  ")
            self.pos += 1
            if self.pos < len(self.lines) and self.lines[self.pos].strip() \
                    and not (HEADING_RE.match(self.lines[self.pos])
                             or self.lines[self.pos].startswith("```")):
                spans.append(("break", "", None) if hard else ("text", " ", None))
        return ("para", spans)

    def _list(self, base_indent):
        first = LIST_RE.match(self.lines[self.pos])
        kind = "ol" if first.group(2)[0].isdigit() else "ul"
        items = []
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            if not line.strip():
                # Blank line: list continues only if a same-level,
                # same-kind item follows; otherwise the list is over.
                nxt = self.pos + 1
                while nxt < len(self.lines) and not self.lines[nxt].strip():
                    nxt += 1
                if nxt < len(self.lines):
                    nm = LIST_RE.match(self.lines[nxt])
                    nkind = ("ol" if nm and nm.group(2)[0].isdigit()
                             else "ul")
                    if nm and len(nm.group(1)) == base_indent \
                            and nkind == kind:
                        self.pos = nxt
                        continue
                break
            m = LIST_RE.match(line)
            if not m or len(m.group(1)) < base_indent:
                break
            if ("ol" if m.group(2)[0].isdigit() else "ul") != kind:
                break  # adjacent list of the other kind: separate block
            if len(m.group(1)) > base_indent:
                break  # handled by the item loop below, not here
            text_parts = [m.group(3)]
            subblocks = []
            self.pos += 1
            while self.pos < len(self.lines):
                nxt = self.lines[self.pos]
                if not nxt.strip():
                    break
                nm = LIST_RE.match(nxt)
                if nm and len(nm.group(1)) > base_indent:
                    subblocks.append(self._list(len(nm.group(1))))
                    continue
                if nm and len(nm.group(1)) <= base_indent:
                    break
                if len(nxt) - len(nxt.lstrip()) > base_indent:
                    text_parts.append(nxt.strip())
                    self.pos += 1
                    continue
                break
            items.append((parse_inline(" ".join(text_parts)), subblocks))
        return (kind, items)


def parse(text):
    return Parser(text).parse()


# ---------------------------------------------------------------- HTML preview

CSS_FONT = {"helvetica": "Helvetica, Arial, sans-serif",
            "times": "Georgia, 'Times New Roman', serif",
            "courier": "'Courier New', Courier, monospace"}


def _html_spans(spans):
    out = []
    for kind, text, url in spans:
        esc = html_lib.escape(text)
        if kind == "bold":
            out.append(f"<strong>{esc}</strong>")
        elif kind == "italic":
            out.append(f"<em>{esc}</em>")
        elif kind == "bolditalic":
            out.append(f"<strong><em>{esc}</em></strong>")
        elif kind == "code":
            out.append(f"<code>{esc}</code>")
        elif kind == "link":
            out.append(f'<a href="{html_lib.escape(url or "")}">{esc}</a>')
        elif kind == "image":
            out.append(f'<span class="image-placeholder">[Image: {esc}]</span>')
        elif kind == "break":
            out.append("<br>")
        else:
            out.append(esc)
    return "".join(out)


def _html_list(kind, items):
    tag = "ol" if kind == "ol" else "ul"
    parts = [f"<{tag}>"]
    for spans, subblocks in items:
        inner = _html_spans(spans)
        for sub in subblocks:
            inner += _html_list(sub[0], sub[1])
        parts.append(f"<li>{inner}</li>")
    parts.append(f"</{tag}>")
    return "".join(parts)


def render_html(blocks, style):
    css = (
        f"body {{ font-family: {CSS_FONT[style.font]}; "
        f"font-size: {style.font_size}pt; "
        f"background: #{_hex(style.bg)}; color: #{_hex(style.fg)}; "
        f"max-width: 700px; margin: 2em auto; line-height: 1.5; }}\n"
        + "".join(
            f"h{l} {{ font-size: {style.heading_size(l):.1f}pt; }}\n"
            for l in range(1, 7))
        + "pre { background: #eeeeee; padding: 0.5em; overflow-x: auto; }\n"
        "code { font-family: 'Courier New', monospace; }\n"
        "a { color: #0000cc; }\n"
        "blockquote { border-left: 3px solid #999; padding-left: 1em; "
        "color: #555; }\n"
    )
    body = []
    for block in blocks:
        if block[0] == "heading":
            body.append(f"<h{block[1]}>{_html_spans(block[2])}</h{block[1]}>")
        elif block[0] == "para":
            body.append(f"<p>{_html_spans(block[1])}</p>")
        elif block[0] in ("ul", "ol"):
            body.append(_html_list(block[0], block[1]))
        elif block[0] == "code":
            body.append(f"<pre><code>{html_lib.escape(block[1])}</code></pre>")
        elif block[0] == "quote":
            body.append(f"<blockquote>{_html_spans(block[1])}</blockquote>")
        elif block[0] == "hr":
            body.append("<hr>")
    return ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">\n"
            f"<style>\n{css}</style></head>\n<body>\n"
            + "\n".join(body) + "\n</body></html>\n")


def _hex(rgb):
    return "".join(f"{round(c * 255):02x}" for c in rgb)


# ---------------------------------------------------------------- PDF layout

def _frag_font(style, kind):
    fam = FAMILIES[style.font]
    if kind == "code":
        return "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"
    return fam[:4]


def _frag_fontname(style, kind):
    regular, bold, oblique, boldoblique = _frag_font(style, kind)
    return {"text": regular, "link": regular, "image": regular,
            "bold": bold, "italic": oblique,
            "bolditalic": boldoblique, "code": regular}[kind]


def _frag_size(style, kind, base_size):
    return base_size


def _wrap_spans(spans, max_width, style, base_size):
    """Greedy word wrap. Lines are lists of (word, kind, url, space_before).

    space_before records whether a real space preceded the word in the
    source, so "[link](url)." renders as "link." not "link ." — the
    earlier version inserted a space between every two fragments.
    """
    words = []
    pending_space = False
    for kind, text, url in spans:
        if kind == "break":
            words.append((None, "break", None, False))
            pending_space = False
            continue
        disp = f"[Image: {text}]" if kind == "image" else text
        for m in re.finditer(r"\S+", disp):
            space_before = pending_space or (
                m.start() > 0 and disp[m.start() - 1] == " ")
            words.append((m.group(), kind, url, space_before))
            pending_space = False
        pending_space = disp.endswith(" ")
    lines, cur, cur_w = [], [], 0.0
    space_w = text_width(" ", style.font, base_size)
    for word, kind, url, space_before in words:
        if word is None:  # hard break
            lines.append(cur)
            cur, cur_w = [], 0.0
            continue
        ww = text_width(word, style.font if kind != "code" else "courier",
                        base_size)
        add = ww if not cur or not space_before else space_w + ww
        if cur and cur_w + add > max_width:
            lines.append(cur)
            cur, cur_w = [(word, kind, url, False)], ww
        else:
            cur.append((word, kind, url, space_before))
            cur_w += add
    if cur or not lines:
        lines.append(cur)
    return lines


def _wrap_code(text, max_width, size):
    lines = []
    for raw in text.split("\n"):
        if not raw:
            lines.append("")
            continue
        cur = ""
        for ch in raw:
            if cur and text_width(cur + ch, "courier", size) > max_width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def _pdf_escape(text):
    return (text.replace("\\", "\\\\").replace("(", "\\(")
                .replace(")", "\\)"))


def _pdf_text(text):
    """Encode for a base-14 font: Latin-1, '?' outside it."""
    return _pdf_escape(text.encode("latin-1", "replace").decode("latin-1"))


class Painter:
    def __init__(self, style):
        self.style = style
        self.page_w, self.page_h = style.page_size()
        self.pages = []
        self.ops = None
        self.y = 0
        self.new_page()

    @property
    def bottom(self):
        return MARGIN

    @property
    def text_width(self):
        return self.page_w - 2 * MARGIN

    def new_page(self):
        self.ops = []
        self.pages.append(self.ops)
        bg = rgb_str(self.style.bg)
        self.ops.append(f"{bg} rg 0 0 {self.page_w} {self.page_h} re f")
        self.y = self.page_h - MARGIN

    def ensure(self, height):
        if self.y - height < self.bottom:
            self.new_page()

    def draw_line(self, frags, indent, size, leading):
        """frags: (text, kind, url). Draws one baseline at self.y."""
        self.ensure(leading)
        x = MARGIN + indent
        for text, kind, url in frags:
            if not text:
                continue
            fname = _frag_fontname(self.style, kind)
            fam = "courier" if kind == "code" else self.style.font
            w = text_width(text, fam, size)
            if kind == "code":
                self.ops.append(
                    f"0.93 0.93 0.93 rg {x - 1:.1f} {self.y - 2:.1f} "
                    f"{w + 2:.1f} {size + 3:.1f} re f")
            color = "0 0 0.8" if kind == "link" else rgb_str(self.style.fg)
            self.ops.append(
                f"BT /{fname} {size:.1f} Tf {color} rg "
                f"{x:.1f} {self.y:.1f} Td ({_pdf_text(text)}) Tj ET")
            if kind == "link":
                self.ops.append(
                    f"0 0 0.8 RG 0.5 w {x:.1f} {self.y - 1.5:.1f} m "
                    f"{x + w:.1f} {self.y - 1.5:.1f} l S")
            x += w  # fragments already carry their own spaces
        self.y -= leading

    def draw_block(self, block, indent=0):
        style = self.style
        avail = self.text_width - indent
        if block[0] == "heading":
            size = style.heading_size(block[1])
            leading = size * 1.25
            self.ensure(leading * 2)
            self.y -= 4
            for line in _wrap_spans(block[2], avail, style, size):
                self.draw_line(_join_frags(line), indent, size, leading)
            self.y -= 4
        elif block[0] == "para":
            size = style.font_size
            leading = size * 1.4
            for line in _wrap_spans(block[1], avail, style, size):
                self.draw_line(_join_frags(line), indent, size, leading)
            self.y -= 4
        elif block[0] in ("ul", "ol"):
            self._draw_list(block, indent)
            self.y -= 2
        elif block[0] == "code":
            size = max(style.font_size - 1, 8)
            leading = size * 1.35
            for raw in _wrap_code(block[1], avail, size):
                self.ensure(leading)
                if raw:
                    self.ops.append(
                        f"0.93 0.93 0.93 rg {MARGIN + indent:.1f} "
                        f"{self.y - 2:.1f} {avail:.1f} {leading:.1f} re f")
                    self.ops.append(
                        f"BT /Courier {size:.1f} Tf {rgb_str(style.fg)} rg "
                        f"{MARGIN + indent + 4:.1f} {self.y:.1f} Td "
                        f"({_pdf_text(raw)}) Tj ET")
                self.y -= leading
            self.y -= 4
        elif block[0] == "quote":
            size = style.font_size
            leading = size * 1.4
            lines = _wrap_spans(block[1], avail - 14, style, size)
            # Italicise: re-tag text spans as italic for the PDF.
            lines = [[(t, "italic" if k == "text" else k, u, s)
                      for t, k, u, s in line] for line in lines]
            total = len(lines) * leading
            self.ensure(total)
            top = self.y
            self.ops.append(
                f"0.6 0.6 0.6 rg {MARGIN + indent:.1f} {top - total + 2:.1f} "
                f"3 {total:.1f} re f")
            for line in lines:
                self.draw_line(_join_frags(line), indent + 14, size, leading)
            self.y -= 4
        elif block[0] == "hr":
            self.ensure(14)
            self.ops.append(
                f"0.6 0.6 0.6 RG 0.5 w {MARGIN + indent:.1f} {self.y:.1f} m "
                f"{MARGIN + indent + avail:.1f} {self.y:.1f} l S")
            self.y -= 14

    def _draw_list(self, block, indent):
        kind, items = block
        size = self.style.font_size
        leading = size * 1.4
        for idx, (spans, subblocks) in enumerate(items, 1):
            marker = f"{idx}." if kind == "ol" else "\u2022"
            # Bullet char is outside Latin-1; use '-' for PDF safety.
            if kind == "ul":
                marker = "-"
            prefix = marker + " "
            prefix_w = text_width(prefix, self.style.font, size)
            avail = self.text_width - indent - prefix_w
            lines = _wrap_spans(spans, avail, self.style, size)
            for li, line in enumerate(lines):
                frags = _join_frags(line)
                if li == 0:
                    frags = [(prefix, "text", None)] + frags
                    self.draw_line(frags, indent, size, leading)
                else:
                    self.draw_line(frags, indent + prefix_w, size, leading)
            for sub in subblocks:
                self._draw_list(sub, indent + prefix_w + 10)
            self.y -= 1


def _join_frags(line):
    """Merge consecutive same-kind words into fragments.

    Words are joined with a space only when space_before says the
    source had one there.
    """
    frags = []
    for word, kind, url, space_before in line:
        if frags and frags[-1][1] == kind and frags[-1][2] == url:
            frags[-1] = (frags[-1][0] + (" " if space_before else "")
                         + word, kind, url)
        else:
            # A space between fragments lives at the start of the
            # later fragment (draw_line no longer adds one).
            prefix = " " if (space_before and frags) else ""
            frags.append((prefix + word, kind, url))
    return frags


# ---------------------------------------------------------------- PDF writer

FONT_NAMES = {
    "helvetica": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique",
                  "Helvetica-BoldOblique"),
    "times": ("Times-Roman", "Times-Bold", "Times-Italic",
              "Times-BoldItalic"),
    "courier": ("Courier", "Courier-Bold", "Courier-Oblique",
                "Courier-BoldOblique"),
}


def build_pdf(pages_ops, style):
    """Assemble a PDF. pages_ops: list of per-page operation lists.

    Font resource names: F1..F4 = chosen family regular/bold/
    oblique/bold-oblique, F5 = Courier (code). The content streams
    only reference names that exist for the chosen family mapping
    because _frag_fontname returns those base names; map them:
    """
    # Map base font names used in streams to resource names.
    fam = FONT_NAMES[style.font]
    name_map = {fam[0]: "F1", fam[1]: "F2", fam[2]: "F3", fam[3]: "F4",
                "Courier": "F5", "Courier-Bold": "F6",
                "Courier-Oblique": "F7", "Courier-BoldOblique": "F8"}
    mapped_pages = []
    for ops in pages_ops:
        mapped = []
        for op in ops:
            for base, res in name_map.items():
                op = op.replace(f"/{base} ", f"/{res} ")
            mapped.append(op)
        mapped_pages.append(mapped)

    page_w, page_h = style.page_size()
    n_pages = len(mapped_pages)
    # Object numbering: 1 catalog, 2 pages, then per page: page, content,
    # then font objects.
    first_font_id = 2 + 2 * n_pages + 1
    font_ids = {}
    ordered_fonts = [fam[0], fam[1], fam[2], fam[3],
                     "Courier", "Courier-Bold", "Courier-Oblique",
                     "Courier-BoldOblique"]
    res_names = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]
    for res, base in zip(res_names, ordered_fonts):
        font_ids[res] = first_font_id
        first_font_id += 1
    total = first_font_id - 1

    out = bytearray()
    offsets = {}

    def emit(obj_id, body):
        offsets[obj_id] = len(out)
        out.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
        out.extend(body if isinstance(body, bytes) else body.encode("latin-1"))
        out.extend(b"\nendobj\n")

    out.extend(b"%PDF-1.4\n")
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    emit(1, "<< /Type /Catalog /Pages 2 0 R >>")
    emit(2, f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")
    font_dict = " ".join(f"/{res} {fid} 0 R"
                         for res, fid in zip(res_names,
                                             [font_ids[r] for r in res_names]))
    for i, ops in enumerate(mapped_pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        stream = ("\n".join(ops) + "\n").encode("latin-1", "replace")
        emit(page_id,
             f"<< /Type /Page /Parent 2 0 R "
             f"/MediaBox [0 0 {page_w} {page_h}] "
             f"/Resources << /Font << {font_dict} >> >> "
             f"/Contents {content_id} 0 R >>")
        body = (f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
                + stream + b"endstream")
        emit(content_id, body)
    for res, base in zip(res_names, ordered_fonts):
        emit(font_ids[res],
             f"<< /Type /Font /Subtype /Type1 /BaseFont /{base} "
             f"/Encoding /WinAnsiEncoding >>")
    xref_pos = len(out)
    out.extend(f"xref\n0 {total + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, total + 1):
        out.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("latin-1"))
    out.extend(f"trailer\n<< /Size {total + 1} /Root 1 0 R >>\n"
               f"startxref\n{xref_pos}\n%%EOF\n".encode("latin-1"))
    return bytes(out)


def render_pdf(blocks, style):
    painter = Painter(style)
    for block in blocks:
        painter.draw_block(block)
    return build_pdf(painter.pages, style)


# ---------------------------------------------------------------- convert


def convert(input_path, output_path, preview_path=None, style=None):
    style = style or Style()
    with open(input_path, encoding="utf-8") as fh:
        text = fh.read()
    blocks = parse(text)
    pdf = render_pdf(blocks, style)
    with open(output_path, "wb") as fh:
        fh.write(pdf)
    if preview_path:
        with open(preview_path, "w", encoding="utf-8") as fh:
            fh.write(render_html(blocks, style))
    return output_path


# ---------------------------------------------------------------- editor loop

HELP = ("Commands: print | append | insert N | replace N | delete N | "
        "pdf | save | help | quit\n"
        "append/insert/replace read lines until a line containing only '.'\n")


def edit_loop(lines, instream, outstream, on_save=None, on_pdf=None):
    lines = list(lines)
    outstream.write(HELP)
    while True:
        outstream.write("md> ")
        outstream.flush()
        raw = instream.readline()
        if not raw:
            break
        cmd = raw.strip()
        if not cmd:
            continue
        parts = cmd.split()
        verb = parts[0].lower()
        if verb == "quit":
            break
        if verb == "help":
            outstream.write(HELP)
        elif verb == "print":
            if not lines:
                outstream.write("(empty)\n")
            for i, line in enumerate(lines, 1):
                outstream.write(f"{i}: {line}\n")
        elif verb == "append":
            new = _read_until_dot(instream)
            lines.extend(new)
        elif verb in ("insert", "replace"):
            if len(parts) != 2 or not parts[1].isdigit():
                outstream.write(f"usage: {verb} N\n")
                continue
            n = int(parts[1])
            if verb == "insert" and not (1 <= n <= len(lines) + 1):
                outstream.write(f"line {n} out of range\n")
                continue
            if verb == "replace" and not (1 <= n <= len(lines)):
                outstream.write(f"line {n} out of range\n")
                continue
            new = _read_until_dot(instream)
            if verb == "insert":
                lines[n - 1:n - 1] = new
            else:
                lines[n - 1:n] = new
        elif verb == "delete":
            if len(parts) != 2 or not parts[1].isdigit():
                outstream.write("usage: delete N\n")
                continue
            n = int(parts[1])
            if not (1 <= n <= len(lines)):
                outstream.write(f"line {n} out of range\n")
                continue
            del lines[n - 1]
        elif verb == "save":
            if on_save:
                on_save(list(lines))
            outstream.write("Saved.\n")
        elif verb == "pdf":
            if on_pdf:
                on_pdf(list(lines))
                outstream.write("PDF written.\n")
            else:
                outstream.write("No PDF output configured.\n")
        else:
            outstream.write(f"Unknown command: {verb}\n")
    return lines


def _read_until_dot(instream):
    out = []
    while True:
        line = instream.readline()
        if not line or line.rstrip("\n") == ".":
            break
        out.append(line.rstrip("\n"))
    return out


def _file_changed(path, prev_mtime):
    try:
        cur = os.path.getmtime(path)
    except OSError:
        return False, prev_mtime
    return cur != prev_mtime, cur


# ---------------------------------------------------------------- CLI


def _style_from_args(args):
    if args.font not in FAMILIES:
        raise ValueError(f"unknown font {args.font!r}")
    if args.page not in PAGE_SIZES:
        raise ValueError(f"unknown page size {args.page!r}")
    if args.font_size <= 0:
        raise ValueError("font size must be positive")
    return Style(font=args.font, font_size=args.font_size,
                 heading_scale=args.heading_scale,
                 bg=parse_color(args.bg), fg=parse_color(args.fg),
                 page=args.page)


def _add_style_args(parser):
    parser.add_argument("--font", default="helvetica")
    parser.add_argument("--font-size", type=float, default=12.0)
    parser.add_argument("--heading-scale", type=float, default=1.0)
    parser.add_argument("--bg", default="ffffff")
    parser.add_argument("--fg", default="000000")
    parser.add_argument("--page", default="a4")


def build_parser():
    parser = argparse.ArgumentParser(prog="md2pdf",
                                     description="Markdown to PDF editor")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("convert", help="convert Markdown to PDF")
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--preview")
    _add_style_args(p)
    p = sub.add_parser("preview", help="write only the HTML preview")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    _add_style_args(p)
    p = sub.add_parser("edit", help="terminal editing loop")
    p.add_argument("input")
    p.add_argument("--pdf")
    p.add_argument("--preview")
    _add_style_args(p)
    p = sub.add_parser("watch", help="rebuild PDF on every input change")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--preview")
    p.add_argument("--interval", type=float, default=1.0)
    _add_style_args(p)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        style = _style_from_args(args)
    except ValueError as exc:
        print(f"md2pdf: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "convert":
            out = args.output or (os.path.splitext(args.input)[0] + ".pdf")
            convert(args.input, out, args.preview, style)
            print(f"Wrote {out}")
            return 0
        if args.command == "preview":
            with open(args.input, encoding="utf-8") as fh:
                blocks = parse(fh.read())
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(render_html(blocks, style))
            print(f"Wrote {args.output}")
            return 0
        if args.command == "edit":
            if not os.path.exists(args.input):
                print(f"md2pdf: no such file: {args.input}", file=sys.stderr)
                return 2
            with open(args.input, encoding="utf-8") as fh:
                original = fh.read().splitlines()

            def _save(buf):
                with open(args.input, "w", encoding="utf-8") as fh:
                    fh.write("\n".join(buf) + ("\n" if buf else ""))

            def _pdf(buf):
                text = "\n".join(buf) + ("\n" if buf else "")
                blocks = parse(text)
                pdf_path = args.pdf or (os.path.splitext(args.input)[0]
                                        + ".pdf")
                with open(pdf_path, "wb") as fh:
                    fh.write(render_pdf(blocks, style))
                if args.preview:
                    with open(args.preview, "w", encoding="utf-8") as fh:
                        fh.write(render_html(blocks, style))

            final = edit_loop(original, sys.stdin, sys.stdout,
                              on_save=_save, on_pdf=_pdf)
            if final != original:
                if sys.stdin.isatty():
                    answer = input("Save changes? [y/N] ").strip().lower()
                    if answer != "y":
                        print("Changes discarded.")
                        return 0
                _save(final)
                print(f"Saved {args.input}")
            return 0
        if args.command == "watch":
            if not os.path.exists(args.input):
                print(f"md2pdf: no such file: {args.input}", file=sys.stderr)
                return 2
            convert(args.input, args.output, args.preview, style)
            print(f"Wrote {args.output} (watching {args.input})")
            prev = os.path.getmtime(args.input)
            try:
                while True:
                    time.sleep(args.interval)
                    changed, prev = _file_changed(args.input, prev)
                    if changed:
                        convert(args.input, args.output, args.preview, style)
                        print(f"Rebuilt {args.output}")
            except KeyboardInterrupt:
                print("\nStopped.")
                return 0
    except FileNotFoundError as exc:
        print(f"md2pdf: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError) as exc:
        print(f"md2pdf: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
