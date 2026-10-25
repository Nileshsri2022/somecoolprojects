#!/usr/bin/env python3
"""Static site generator (single file, Python 3 standard library only).

Implements the Coding Challenges "Build Your Own Static Site
Generator" core steps: create a site, create a theme, add pages,
build Markdown content through a {{ Title }} / {{ Content }}
template into public/, and serve a dev version that rebuilds when
sources change. See docs/SPEC.md for the exact supported syntax,
divergences, and scope limits.

Usage:
    python3 ssg.py new <site>
    python3 ssg.py new theme <name> [--site <dir>]
    python3 ssg.py new page <slug> [--site <dir>]
    python3 ssg.py build [--site <dir>] [--theme <name>]
    python3 ssg.py serve [--site <dir>] [--theme <name>]
                         [--host 127.0.0.1] [--port 8000]
"""

import html
import os
import re
import shutil
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

USAGE = """Usage:
  ssg.py new <site>
  ssg.py new theme <name> [--site <dir>]
  ssg.py new page <slug> [--site <dir>]
  ssg.py build [--site <dir>] [--theme <name>]
  ssg.py serve [--site <dir>] [--theme <name>] [--host HOST] [--port PORT]
"""

DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html>
  <head>
    <title>{{ Title }}</title>
  </head>
  <body>
    {{ Content }}
  </body>
</html>
"""

PLACEHOLDER_INDEX = """# Welcome

This is the homepage. Edit this file to change the site.
"""

PLACEHOLDER_PAGE_TEMPLATE = "# {title}\n\nWrite about {title} here.\n"


class SsgError(Exception):
    """User-facing error: printed as 'Error: ...', exit code 1."""


# ---------------------------------------------------------------- Markdown

def escape_html(text):
    return html.escape(text, quote=True)


def render_inline(text):
    """Inline Markdown -> HTML. Input is escaped first so raw HTML
    in source can never become markup; code spans are shielded from
    later bold/italic/link passes by placeholder substitution."""
    escaped = escape_html(text)
    code_spans = []

    def stash_code(match):
        code_spans.append("<code>%s</code>" % match.group(1))
        return "\x00%d\x00" % (len(code_spans) - 1)

    out = re.sub(r"`([^`\n]+)`", stash_code, escaped)
    # Images before links so ![...](...) is not consumed as a link.
    out = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                 r'<img alt="\1" src="\2">', out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                 r'<a href="\2">\1</a>', out)
    out = re.sub(r"\*\*([^\n]+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\*([^\n]+?)\*", r"<em>\1</em>", out)
    for i, span in enumerate(code_spans):
        out = out.replace("\x00%d\x00" % i, span)
    return out


def markdown_to_html(text):
    """Convert the documented Markdown subset (see SPEC.md) to HTML."""
    lines = text.splitlines()
    blocks = []
    paragraph = []
    list_items = None  # ("ul"|"ol", [items])
    quote_lines = []
    in_fence = False
    fence_lines = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            blocks.append("<p>%s</p>" % " ".join(
                render_inline(line.strip()) for line in paragraph))
            paragraph = []

    def flush_list():
        nonlocal list_items
        if list_items:
            tag, items = list_items
            blocks.append("<%s>\n%s\n</%s>" % (
                tag,
                "\n".join("<li>%s</li>" % render_inline(i) for i in items),
                tag))
            list_items = None

    def flush_quote():
        nonlocal quote_lines
        if quote_lines:
            blocks.append("<blockquote><p>%s</p></blockquote>" % " ".join(
                render_inline(line.strip()) for line in quote_lines))
            quote_lines = []

    def flush_all():
        flush_paragraph()
        flush_list()
        flush_quote()

    for line in lines:
        if in_fence:
            if line.strip().startswith("```"):
                blocks.append("<pre><code>%s</code></pre>" %
                              escape_html("\n".join(fence_lines)))
                fence_lines = []
                in_fence = False
            else:
                fence_lines.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_all()
            in_fence = True
            fence_lines = []
            continue
        if not stripped:
            flush_all()
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_all()
            blocks.append("<h%d>%s</h%d>" % (
                len(heading.group(1)),
                render_inline(heading.group(2).strip()),
                len(heading.group(1))))
            continue
        if stripped in ("---", "***", "___"):
            flush_all()
            blocks.append("<hr>")
            continue
        ul = re.match(r"^[-*]\s+(.*)$", stripped)
        if ul:
            flush_paragraph()
            flush_quote()
            if list_items is None or list_items[0] != "ul":
                flush_list()
                list_items = ("ul", [])
            list_items[1].append(ul.group(1).strip())
            continue
        ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ol:
            flush_paragraph()
            flush_quote()
            if list_items is None or list_items[0] != "ol":
                flush_list()
                list_items = ("ol", [])
            list_items[1].append(ol.group(1).strip())
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            flush_list()
            quote_lines.append(stripped[1:].strip())
            continue
        flush_list()
        flush_quote()
        paragraph.append(line)
    if in_fence:  # Unterminated fence: emit what was collected.
        blocks.append("<pre><code>%s</code></pre>" %
                      escape_html("\n".join(fence_lines)))
    flush_all()
    return "\n".join(blocks)


def extract_title(text, fallback):
    """First top-level (#) heading, else the file-name fallback."""
    for line in text.splitlines():
        match = re.match(r"^#\s+(.*)$", line.strip())
        if match:
            return match.group(1).strip()
    return fallback


def title_from_name(stem):
    return stem.replace("-", " ").replace("_", " ").title() or "Untitled"


def render_template(template, title, content):
    out = re.sub(r"\{\{\s*Title\s*\}\}", escape_html(title), template)
    out = re.sub(r"\{\{\s*Content\s*\}\}", content, out)
    return out


# ---------------------------------------------------------------- Site logic

def find_site_dir(explicit):
    if explicit:
        site = Path(explicit)
        if not site.is_dir():
            raise SsgError("site directory does not exist: %s" % explicit)
        return site
    cwd = Path.cwd()
    if (cwd / "content").is_dir():
        return cwd
    raise SsgError("no site found: pass --site <dir> or run inside a "
                   "site directory (one containing content/)")


def require_content_dir(site):
    content = site / "content"
    if not content.is_dir():
        raise SsgError("site has no content/ directory: %s" % site)
    return content


def resolve_theme(site, name):
    """Return the template text per the SPEC selection rule."""
    themes_dir = site / "themes"
    if name:
        template_path = themes_dir / name / "index.html"
        if not template_path.is_file():
            raise SsgError("theme not found: %s" % name)
        return template_path.read_text(encoding="utf-8")
    if not themes_dir.is_dir():
        return DEFAULT_TEMPLATE
    available = sorted(p.name for p in themes_dir.iterdir()
                       if p.is_dir() and (p / "index.html").is_file())
    if len(available) == 1:
        return (themes_dir / available[0] / "index.html").read_text(
            encoding="utf-8")
    if len(available) > 1:
        raise SsgError("multiple themes found (%s); pass --theme <name>"
                       % ", ".join(available))
    return DEFAULT_TEMPLATE


def build_site(site, theme_name=None):
    """Full rebuild: wipe public/, render every content/*.md, copy
    static/ if present. Returns the list of written HTML paths."""
    site = Path(site)
    content_dir = require_content_dir(site)
    template = resolve_theme(site, theme_name)
    public_dir = site / "public"
    if public_dir.exists():
        shutil.rmtree(public_dir)
    public_dir.mkdir(parents=True)
    written = []
    for md_path in sorted(content_dir.rglob("*.md")):
        rel = md_path.relative_to(content_dir).with_suffix(".html")
        out_path = public_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        source = md_path.read_text(encoding="utf-8")
        title = extract_title(source, title_from_name(md_path.stem))
        out_path.write_text(
            render_template(template, title, markdown_to_html(source)),
            encoding="utf-8")
        written.append(out_path)
    static_dir = site / "static"
    if static_dir.is_dir():
        shutil.copytree(static_dir, public_dir, dirs_exist_ok=True)
    return written


def validate_slug(slug):
    if not slug or slug.startswith("/") or ".." in Path(slug).parts:
        raise SsgError("unsafe page slug: %r" % slug)
    if not re.fullmatch(r"[A-Za-z0-9._\-/]+", slug):
        raise SsgError("invalid page slug: %r "
                       "(use letters, digits, -, _, . and /)" % slug)
    return slug


def cmd_new_site(name):
    site = Path(name)
    if site.exists():
        raise SsgError("directory already exists: %s" % name)
    content_dir = site / "content"
    content_dir.mkdir(parents=True)
    (content_dir / "index.md").write_text(PLACEHOLDER_INDEX,
                                          encoding="utf-8")
    print("Created site %s" % name)
    return 0


def cmd_new_theme(site, name):
    require_content_dir(site)
    theme_dir = site / "themes" / name
    if theme_dir.exists():
        raise SsgError("theme already exists: %s" % name)
    theme_dir.mkdir(parents=True)
    (theme_dir / "index.html").write_text(DEFAULT_TEMPLATE,
                                          encoding="utf-8")
    print("Created theme %s" % name)
    return 0


def cmd_new_page(site, slug):
    content_dir = require_content_dir(site)
    validate_slug(slug)
    target = content_dir / ("%s.md" % slug)
    if target.exists():
        raise SsgError("page already exists: %s" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    title = title_from_name(Path(slug).name)
    target.write_text(PLACEHOLDER_PAGE_TEMPLATE.format(title=title),
                      encoding="utf-8")
    print("Created page %s" % target)
    return 0


def snapshot_mtimes(site):
    """mtime snapshot of every file under content/, themes/, static/."""
    stamps = {}
    for sub in ("content", "themes", "static"):
        root = Path(site) / sub
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file():
                    try:
                        stamps[str(path)] = path.stat().st_mtime_ns
                    except OSError:
                        pass
    return stamps


def serve_site(site, theme_name, host, port):
    site = Path(site)
    require_content_dir(site)
    build_site(site, theme_name)
    public_dir = site / "public"

    def watcher():
        last = snapshot_mtimes(site)
        while True:
            time.sleep(0.5)
            current = snapshot_mtimes(site)
            if current != last:
                last = current
                try:
                    build_site(site, theme_name)
                except SsgError as exc:
                    print("Rebuild failed: %s" % exc, file=sys.stderr)

    thread = threading.Thread(target=watcher, daemon=True)
    thread.start()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(public_dir), **kwargs)

        def log_message(self, *args):  # keep dev output quiet
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    print("Serving %s at http://%s:%d/ (Ctrl-C to stop)"
          % (public_dir, host, server.server_address[1]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    return 0


# ---------------------------------------------------------------- CLI parsing

def parse_options(args, allowed):
    """Parse --key value / --key=value options; return (opts, rest)."""
    opts = {}
    rest = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            key, eq, value = arg[2:].partition("=")
            if key not in allowed:
                raise SsgError("unknown option: --%s" % key)
            if not eq:
                if i + 1 >= len(args):
                    raise SsgError("option --%s needs a value" % key)
                i += 1
                value = args[i]
            opts[key] = value
        else:
            rest.append(arg)
        i += 1
    return opts, rest


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args or args[0] in ("-h", "--help"):
            print(USAGE)
            return 0
        command = args[0]
        if command == "new":
            opts, rest = parse_options(args[1:], {"site"})
            if not rest:
                raise SsgError("usage: ssg.py new <site> | "
                               "new theme <name> | new page <slug>")
            if rest[0] == "theme" and len(rest) == 2:
                return cmd_new_theme(find_site_dir(opts.get("site")),
                                     rest[1])
            if rest[0] == "page" and len(rest) == 2:
                return cmd_new_page(find_site_dir(opts.get("site")),
                                    rest[1])
            if len(rest) == 1:
                return cmd_new_site(rest[0])
            raise SsgError("usage: ssg.py new <site> | "
                           "new theme <name> | new page <slug>")
        if command == "build":
            opts, rest = parse_options(args[1:], {"site", "theme"})
            if rest:
                raise SsgError("build takes no positional arguments")
            written = build_site(find_site_dir(opts.get("site")),
                                 opts.get("theme"))
            print("Built %d page(s) into public/" % len(written))
            return 0
        if command == "serve":
            opts, rest = parse_options(args[1:], {"site", "theme",
                                                  "host", "port"})
            if rest:
                raise SsgError("serve takes no positional arguments")
            try:
                port = int(opts.get("port", "8000"))
            except ValueError:
                raise SsgError("invalid port: %r" % opts.get("port"))
            return serve_site(find_site_dir(opts.get("site")),
                              opts.get("theme"),
                              opts.get("host", "127.0.0.1"), port)
        raise SsgError("unknown command: %s\n%s" % (command, USAGE))
    except SsgError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
