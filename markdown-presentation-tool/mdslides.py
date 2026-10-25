#!/usr/bin/env python3
"""mdslides — Markdown Presentation Tool (Python 3 standard library only).

Commands:
    new <dir> [--title ...] [--force]
    serve <project-dir> [--port N] [--raw]
    build <project-dir> [-o deck.html]
    export-pdf <project-dir> [-o deck.pdf]

See docs/SPEC.md for the documented Markdown subset and divergences.
"""

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import textwrap
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

__version__ = "1.0.0"

DEFAULT_CSS = """
body { margin: 0; background: #111827; color: #f9fafb;
       font-family: system-ui, -apple-system, sans-serif; }
main { max-width: 900px; margin: 0 auto; padding: 2rem; }
.slide { display: none; min-height: 70vh; }
.slide.active { display: block; }
h1 { font-size: 2.5rem; } h2 { font-size: 2rem; } h3 { font-size: 1.5rem; }
pre { background: #1f2937; padding: 1rem; overflow-x: auto;
      border-radius: 0.5rem; }
code { background: #1f2937; padding: 0.1rem 0.3rem; border-radius: 0.25rem; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #6b7280; margin-left: 0; padding-left: 1rem;
             color: #d1d5db; }
nav { display: flex; justify-content: space-between; align-items: center;
      padding: 1rem 2rem; color: #9ca3af; }
button { background: #374151; color: #fff; border: 0; border-radius: 0.5rem;
         padding: 0.5rem 1rem; cursor: pointer; }
@media print { nav { display: none; } .slide { display: block !important;
    page-break-after: always; min-height: auto; } }
"""

NAV_SCRIPT = """
<script>
let idx = 0;
const slides = document.querySelectorAll('.slide');
const counter = document.getElementById('counter');
function show(i) {
  if (!slides.length) return;
  idx = Math.max(0, Math.min(slides.length - 1, i));
  slides.forEach((s, j) => s.classList.toggle('active', j === idx));
  if (counter) counter.textContent = 'Slide ' + (idx + 1) + ' / ' + slides.length;
}
document.getElementById('prev').onclick = () => show(idx - 1);
document.getElementById('next').onclick = () => show(idx + 1);
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight' || e.key === ' ') show(idx + 1);
  if (e.key === 'ArrowLeft') show(idx - 1);
});
show(0);
</script>
"""

LIVE_RELOAD_SCRIPT = """
<script>
const initial = document.body.dataset.version || '';
setInterval(async () => {
  try {
    const r = await fetch('/__version__');
    const d = await r.json();
    if (initial && d.version && d.version !== initial) location.reload();
  } catch (e) {}
}, 1000);
</script>
"""

DEFAULT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{title}}</title>
<style>{{style}}</style>
</head>
<body>
<nav><button id="prev">Prev</button><span id="counter"></span>
<button id="next">Next</button></nav>
<main>
{{slides}}
</main>
{{scripts}}
</body>
</html>
"""

EXAMPLE_DECK = """# Welcome

- Write presentations in Markdown
- Version control them like code
- Present them with `mdslides serve`

---

# A Second Slide

This is a paragraph with **bold**, *italic* and a
[link](https://codingchallenges.fyi).

```python
print("hello, slides")
```

---

## Thanks

> Keep it simple. One file per idea, one slide per thought.
"""

PROJECT_README = """# {title}

Edit `slides/slides.md` — a line containing exactly `---` starts a
new slide.

```sh
python3 ../mdslides.py serve .     # present in the browser (live reload)
python3 ../mdslides.py build . -o deck.html
python3 ../mdslides.py export-pdf . -o deck.pdf
```

Customise the look in `template/template.html` and
`template/style.css`; delete either file to fall back to the
built-in default for that piece. Put images in `images/`.
"""


# ---------------------------------------------------------------- slides

def split_slides(text):
    """Split markdown on lines whose stripped form is exactly '---'.

    Empty slides (including leading/trailing ones) are dropped.
    """
    slides, current = [], []
    for line in text.splitlines():
        if line.strip() == "---":
            chunk = "\n".join(current).strip()
            if chunk:
                slides.append(chunk)
            current = []
        else:
            current.append(line)
    chunk = "\n".join(current).strip()
    if chunk:
        slides.append(chunk)
    return slides


def _strip_inline(text):
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text.replace("`", "")


def render_inline(text):
    """Escape HTML, then apply code / image / link / bold / italic.

    Code spans are extracted first and restored last, so markup
    inside backticks is never reinterpreted as bold/italic/etc.
    """
    out = html.escape(text)
    spans = []

    def stash(m):
        spans.append("<code>" + m.group(1) + "</code>")
        return "\x00CODE%d\x00" % (len(spans) - 1)

    out = re.sub(r"`([^`]+)`", stash, out)
    out = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                 lambda m: '<img alt="%s" src="%s">' % (
                     html.escape(m.group(1), quote=True),
                     html.escape(m.group(2), quote=True)), out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                 lambda m: '<a href="%s">%s</a>' % (
                     html.escape(m.group(2), quote=True), m.group(1)), out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", out)
    for i, span in enumerate(spans):
        out = out.replace("\x00CODE%d\x00" % i, span)
    return out


def render_markdown(text):
    """Render the documented Markdown subset to HTML."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        fence = re.match(r"^```(.*)$", stripped)
        if fence:
            lang = fence.group(1).strip()
            buf, i = [], i + 1
            while i < len(lines) and lines[i].strip() != "```":
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence (or EOF)
            cls = ' class="language-%s"' % html.escape(lang) if lang else ""
            out.append("<pre><code%s>%s</code></pre>"
                       % (cls, html.escape("\n".join(buf))))
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            out.append("<h%d>%s</h%d>"
                       % (level, render_inline(heading.group(2)), level))
            i += 1
            continue
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>%s</ul>" % "".join(
                "<li>%s</li>" % render_inline(t) for t in items))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>%s</ol>" % "".join(
                "<li>%s</li>" % render_inline(t) for t in items))
            continue
        if stripped.startswith(">"):
            items = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                items.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            out.append("<blockquote>%s</blockquote>" % "".join(
                "<p>%s</p>" % render_inline(t) for t in items))
            continue
        # Paragraph: consecutive plain lines.
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,6}\s+|[-*]\s+|\d+\.\s+>|```)", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>%s</p>" % render_inline(" ".join(buf)))
    return "\n".join(out)


def slide_title(text, index):
    for line in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.*)$", line.strip())
        if m:
            return _strip_inline(m.group(1)).strip()
    return "Slide %d" % (index + 1)


def plain_lines(text):
    """Plain-text lines of a slide, for the PDF handout."""
    result = []
    in_code = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            result.append(raw)
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            result.append(_strip_inline(m.group(1)))
            continue
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            result.append("\u2022 " + _strip_inline(m.group(1)))
            continue
        m = re.match(r"^\d+\.\s+(.*)$", line)
        if m:
            result.append(_strip_inline(m.group(1)))
            continue
        if line.startswith(">"):
            result.append(_strip_inline(re.sub(r"^>\s?", "", line)))
            continue
        if line:
            result.append(_strip_inline(line))
    return result


class Slide:
    def __init__(self, raw, index):
        self.raw = raw
        self.title = slide_title(raw, index)
        self.html = render_markdown(raw)
        self.lines = plain_lines(raw)


def parse_deck(text):
    return [Slide(chunk, i) for i, chunk in enumerate(split_slides(text))]


# ---------------------------------------------------------------- project

def load_project(project_dir):
    """Return (source_path, title, template_dir, slides)."""
    root = Path(project_dir)
    if not root.is_dir():
        raise FileNotFoundError("project directory not found: %s" % project_dir)
    config = {}
    config_path = root / "config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    source = None
    if config.get("source"):
        candidate = root / config["source"]
        if candidate.is_file():
            source = candidate
    if source is None:
        for candidate in (root / "slides" / "slides.md", root / "slides.md"):
            if candidate.is_file():
                source = candidate
                break
    if source is None:
        slides_dir = root / "slides"
        if slides_dir.is_dir():
            found = sorted(slides_dir.glob("*.md"))
            if found:
                source = found[0]
    if source is None:
        raise FileNotFoundError(
            "no markdown source found in project: %s" % project_dir)
    text = source.read_text(encoding="utf-8")
    slides = parse_deck(text)
    title = config.get("title") or (slides[0].title if slides else
                                    "Untitled Presentation")
    template_dir = root / config.get("template_dir", "template")
    return source, title, template_dir, slides, text


def load_template(template_dir):
    """Per-piece fallback: file if present, else embedded default."""
    template, style = DEFAULT_TEMPLATE, DEFAULT_CSS
    html_path = Path(template_dir) / "template.html"
    if html_path.is_file():
        template = html_path.read_text(encoding="utf-8")
    css_path = Path(template_dir) / "style.css"
    if css_path.is_file():
        style = css_path.read_text(encoding="utf-8")
    return template, style


def render_deck(slides, title, template_dir, live_reload=False, raw=False,
                version=""):
    template, style = load_template(template_dir)
    sections = []
    for i, slide in enumerate(slides):
        body = ("<pre>%s</pre>" % html.escape(slide.raw)) if raw else slide.html
        sections.append('<section class="slide">\n%s\n</section>' % body)
    scripts = NAV_SCRIPT
    if live_reload:
        scripts += LIVE_RELOAD_SCRIPT
    out = template.replace("{{title}}", html.escape(title))
    out = out.replace("{{style}}", style)
    out = out.replace("{{slides}}", "\n".join(sections))
    out = out.replace("{{slide_count}}", str(len(slides)))
    out = out.replace("{{scripts}}", scripts)
    if live_reload:
        out = out.replace("<body>", '<body data-version="%s">' % version, 1)
    return out


def source_version(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- PDF

def _pdf_escape(text):
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(slides, path):
    """Minimal PDF 1.4 writer: one page per slide, Helvetica/Courier."""
    objects = []  # byte strings, 1-based object numbers

    def add(obj):
        objects.append(obj if isinstance(obj, bytes) else obj.encode("latin-1"))
        return len(objects)

    catalog_id = add(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add(b"")  # filled below
    font_ids = {
        "F1": add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
        "F2": add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"),
        "F3": add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"),
    }
    page_ids = []
    for slide in slides:
        lines = []
        y = 738
        for wrapped in textwrap.wrap(slide.title, width=40) or [""]:
            lines.append((20, "F2", y, wrapped))
            y -= 28
        y -= 6
        seen_title = False
        for raw_line in slide.lines:
            if not seen_title and raw_line == slide.title:
                seen_title = True
                continue
            for wrapped in textwrap.wrap(raw_line, width=95) or [""]:
                if y < 54:
                    break
                lines.append((11, "F1", y, wrapped))
                y -= 15
        stream = ["BT"]
        for size, font, yy, txt in lines:
            stream.append("%s %d Tf 54 %d Td (%s) Tj ET BT"
                          % (font, size, yy, _pdf_escape(txt)))
        if stream[-1] == "BT":
            stream.pop()
        else:
            stream.append("ET")
        content = "\n".join(stream).encode("latin-1")
        content_id = add(b"<< /Length %d >>\nstream\n" % len(content)
                         + content + b"\nendstream")
        # Page object references its content; content id already known,
        # page id is the next object.
        page_id = len(objects) + 1
        page_ids.append(page_id)
        add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
             "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >> "
             "/Contents %d 0 R >>"
             % (pages_id, font_ids["F1"], font_ids["F2"], font_ids["F3"],
                content_id)).encode("latin-1"))
    objects[pages_id - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                             % (" ".join("%d 0 R" % p for p in page_ids),
                                len(page_ids))).encode("latin-1")
    out = [b"%PDF-1.4\n"]
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(sum(len(b) for b in out))
        out.append(("%d 0 obj\n" % i).encode("latin-1") + obj + b"\nendobj\n")
    xref_pos = sum(len(b) for b in out)
    out.append(("xref\n0 %d\n" % (len(objects) + 1)).encode("latin-1"))
    out.append(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.append(("%010d 00000 n \n" % off).encode("latin-1"))
    out.append(("trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objects) + 1, catalog_id, xref_pos)).encode("latin-1"))
    Path(path).write_bytes(b"".join(out))
    return len(slides)


# ---------------------------------------------------------------- commands

def cmd_new(args):
    dest = Path(args.directory)
    if dest.exists() and any(dest.iterdir()) and not args.force:
        print("error: directory not empty: %s (use --force)" % dest,
              file=sys.stderr)
        return 2
    (dest / "slides").mkdir(parents=True, exist_ok=True)
    (dest / "template").mkdir(parents=True, exist_ok=True)
    (dest / "images").mkdir(parents=True, exist_ok=True)
    (dest / "slides" / "slides.md").write_text(EXAMPLE_DECK, encoding="utf-8")
    (dest / "template" / "template.html").write_text(DEFAULT_TEMPLATE,
                                                     encoding="utf-8")
    (dest / "template" / "style.css").write_text(DEFAULT_CSS, encoding="utf-8")
    (dest / "config.json").write_text(json.dumps(
        {"title": args.title, "source": "slides/slides.md",
         "template_dir": "template"}, indent=2) + "\n", encoding="utf-8")
    (dest / "README.md").write_text(
        PROJECT_README.format(title=args.title), encoding="utf-8")
    try:
        subprocess.run(["git", "init", "-q", str(dest)],
                       check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("warning: git init failed; project created without .git",
              file=sys.stderr)
    print("created presentation project: %s" % dest)
    return 0


def _load_or_report(project_dir):
    try:
        return load_project(project_dir)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return None


def cmd_build(args):
    loaded = _load_or_report(args.project)
    if loaded is None:
        return 2
    source, title, template_dir, slides, _text = loaded
    out_path = Path(args.output)
    if out_path.resolve() == source.resolve():
        print("error: output would overwrite the source file", file=sys.stderr)
        return 2
    out_path.write_text(render_deck(slides, title, template_dir),
                        encoding="utf-8")
    print("wrote %s (%d slides)" % (out_path, len(slides)))
    return 0


def cmd_export_pdf(args):
    loaded = _load_or_report(args.project)
    if loaded is None:
        return 2
    source, title, template_dir, slides, _text = loaded
    out_path = Path(args.output)
    if out_path.resolve() == source.resolve():
        print("error: output would overwrite the source file", file=sys.stderr)
        return 2
    write_pdf(slides, out_path)
    print("wrote %s (%d pages)" % (out_path, len(slides)))
    return 0


def make_handler(project_dir, raw):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/__version__":
                loaded = _load_or_report(project_dir)
                version = source_version(loaded[4]) if loaded else ""
                body = json.dumps({"version": version}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path != "/":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"not found")
                return
            loaded = _load_or_report(project_dir)
            if loaded is None:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"project could not be loaded")
                return
            _source, title, template_dir, slides, text = loaded
            body = render_deck(slides, title, template_dir,
                               live_reload=True, raw=raw,
                               version=source_version(text))
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return Handler


def cmd_serve(args):
    loaded = _load_or_report(args.project)
    if loaded is None:
        return 2
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(args.project, args.raw))
    print("serving http://127.0.0.1:%d/ (Ctrl-C to stop)"
          % server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mdslides", description="Markdown Presentation Tool")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new", help="create a new presentation project")
    p.add_argument("directory")
    p.add_argument("--title", default="My Presentation")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("serve", help="serve the deck in a browser")
    p.add_argument("project")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--raw", action="store_true",
                   help="render markdown as raw text (Step 2)")
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("build", help="write a static HTML deck")
    p.add_argument("project")
    p.add_argument("-o", "--output", default="deck.html")
    p.set_defaults(func=cmd_build)
    p = sub.add_parser("export-pdf", help="export slides to PDF")
    p.add_argument("project")
    p.add_argument("-o", "--output", default="deck.pdf")
    p.set_defaults(func=cmd_export_pdf)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
