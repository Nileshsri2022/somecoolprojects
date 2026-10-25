#!/usr/bin/env python3
"""Terminal ebook reader core for EPUB files.

Python 3 standard library only. Parses EPUB 2 (NCX TOC) and EPUB 3
(nav-document TOC) files, paginates and navigates chapters, manages a
library with full-text search, applies persistent terminal themes, and
stores text-anchored bookmarks / highlights / notes.

This is deliberately NOT a GUI reader: book styling is flattened to
plain text, covers are recorded but not rendered, and font names are
stored but not rendered. See docs/SPEC.md for the honest scope list.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import textwrap
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

__all__ = [
    "EpubError", "Chapter", "TocEntry", "Book", "SearchResult",
    "parse_epub", "paginate", "Reader", "search_in_book",
    "Library", "Theme", "THEMES", "render_page",
    "AnnotationStore", "lookup_word", "wikipedia_summary",
    "DEFAULT_DATA_DIR",
]

DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "ebook-reader"


class EpubError(ValueError):
    """Raised when a file is not a readable, well-formed EPUB."""


# ---------------------------------------------------------------- text
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


_BLOCK = {
    "p", "div", "section", "article", "header", "footer", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "pre", "hr", "br",
    "table", "ul", "ol",
}


class _XhtmlToText(HTMLParser):
    """XHTML -> plain text, preserving block structure only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._lines: list[str] = []
        self._buf: list[str] = []
        self._skip = 0  # depth inside script/style
        self._in_li = False

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if text:
            self._lines.append(text)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag in _BLOCK:
            self._flush()
            if tag == "li":
                self._in_li = True
                self._buf.append("- ")
        if tag == "br":
            self._flush()

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in _BLOCK:
            self._flush()
            self._in_li = False

    def handle_data(self, data):
        if self._skip:
            return
        self._buf.append(data)

    def text(self) -> str:
        self._flush()
        # Collapse runs of blank lines (flush never emits blanks, so
        # this is just joining with a single blank line between blocks
        # that came from paragraph-ish elements is handled by callers
        # via double newline below).
        return "\n\n".join(self._lines)


def xhtml_to_text(source: str) -> str:
    parser = _XhtmlToText()
    parser.feed(source)
    parser.close()
    return parser.text()


# ---------------------------------------------------------------- model
@dataclass
class Chapter:
    id: str
    title: str
    href: str
    text: str


@dataclass
class TocEntry:
    title: str
    chapter_id: str | None
    href: str


@dataclass
class Book:
    path: str
    title: str
    author: str = ""
    language: str = ""
    identifier: str = ""
    chapters: list[Chapter] = field(default_factory=list)
    toc: list[TocEntry] = field(default_factory=list)
    cover_href: str | None = None
    stylesheets: list[str] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(len(c.text) for c in self.chapters)

    def chapter_by_id(self, chapter_id: str) -> Chapter | None:
        for ch in self.chapters:
            if ch.id == chapter_id:
                return ch
        return None


@dataclass
class SearchResult:
    book_title: str
    chapter_title: str
    offset: int
    snippet: str


# ---------------------------------------------------------------- EPUB
def _parse_xml(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise EpubError(f"invalid XML: {exc}") from exc


def _children(elem: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in elem if _local(c.tag) == name]


def _first_text(elem: ET.Element, name: str) -> str:
    for c in elem:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _opf_path(zf: zipfile.ZipFile) -> str:
    try:
        container = _parse_xml(zf.read("META-INF/container.xml"))
    except KeyError:
        return "OEBPS/content.opf"
    for elem in container.iter():
        if _local(elem.tag) == "rootfile":
            path = elem.get("full-path")
            if path:
                return path
    return "OEBPS/content.opf"


def _chapter_title(xhtml: str, href: str) -> str:
    for tag in ("h1", "h2", "title"):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xhtml,
                      re.IGNORECASE | re.DOTALL)
        if m:
            title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            title = html.unescape(re.sub(r"\s+", " ", title))
            if title:
                return title
    return Path(href).stem.replace("_", " ").replace("-", " ").title() or href


def _nav_toc(zf: zipfile.ZipFile, base: str, manifest: dict,
             nav_href: str) -> list[TocEntry]:
    try:
        data = zf.read(base + nav_href)
    except KeyError:
        return []
    doc = data.decode("utf-8", errors="replace")
    entries: list[TocEntry] = []
    # Find the nav element with epub:type containing "toc".
    nav_m = re.search(
        r'<nav[^>]*epub:type="[^"]*toc[^"]*"[^>]*>(.*?)</nav>',
        doc, re.IGNORECASE | re.DOTALL)
    body = nav_m.group(1) if nav_m else doc
    for m in re.finditer(
            r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body,
            re.IGNORECASE | re.DOTALL):
        href, raw = m.group(1), m.group(2)
        title = html.unescape(re.sub(r"<[^>]+>", "", raw).strip())
        title = re.sub(r"\s+", " ", title)
        if title:
            entries.append(TocEntry(title=title, chapter_id=None, href=href))
    return entries


def _ncx_toc(zf: zipfile.ZipFile, base: str, ncx_href: str) -> list[TocEntry]:
    try:
        root = _parse_xml(zf.read(base + ncx_href))
    except KeyError:
        return []
    entries: list[TocEntry] = []

    def walk(elem: ET.Element) -> None:
        for child in elem:
            name = _local(child.tag)
            if name == "navPoint":
                label = ""
                src = ""
                for sub in child:
                    if _local(sub.tag) == "navLabel":
                        label = _first_text(sub, "text")
                    elif _local(sub.tag) == "content":
                        src = sub.get("src", "")
                if label:
                    entries.append(TocEntry(title=label, chapter_id=None,
                                            href=src))
                walk(child)

    for elem in root.iter():
        if _local(elem.tag) == "navMap":
            walk(elem)
            break
    return entries


def parse_epub(path: str | Path) -> Book:
    """Parse an EPUB file into a Book. Raises EpubError on bad input."""
    path = Path(path)
    if not path.is_file():
        raise EpubError(f"file not found: {path}")
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise EpubError(f"not a ZIP/EPUB archive: {path}") from exc
    with zf:
        opf_rel = _opf_path(zf)
        try:
            opf = _parse_xml(zf.read(opf_rel))
        except KeyError as exc:
            raise EpubError(f"OPF package document not found: {opf_rel}") from exc
        base = opf_rel.rsplit("/", 1)[0] + "/" if "/" in opf_rel else ""

        metadata, manifest_el, spine_el = None, None, None
        for child in opf:
            name = _local(child.tag)
            if name == "metadata":
                metadata = child
            elif name == "manifest":
                manifest_el = child
            elif name == "spine":
                spine_el = child
        if manifest_el is None or spine_el is None:
            raise EpubError("OPF is missing manifest or spine")

        title = _first_text(metadata, "title") if metadata is not None else ""
        author = _first_text(metadata, "creator") if metadata is not None else ""
        language = _first_text(metadata, "language") if metadata is not None else ""
        identifier = (_first_text(metadata, "identifier")
                      if metadata is not None else "")
        if not title:
            title = path.stem

        manifest: dict[str, tuple[str, str, str]] = {}  # id -> (href, type, props)
        for item in manifest_el:
            if _local(item.tag) != "item":
                continue
            item_id = item.get("id", "")
            if item_id:
                manifest[item_id] = (
                    item.get("href", ""),
                    item.get("media-type", ""),
                    item.get("properties", ""),
                )
        cover_href = None
        stylesheets: list[str] = []
        nav_href = None
        for item_id, (href, media_type, props) in manifest.items():
            if "cover-image" in props.split() or item_id == "cover":
                cover_href = href
            if media_type == "text/css":
                stylesheets.append(href)
            if "nav" in props.split():
                nav_href = href

        spine_ids: list[str] = []
        toc_id = spine_el.get("toc")
        for ref in spine_el:
            if _local(ref.tag) != "itemref":
                continue
            if ref.get("linear") == "no":
                continue
            spine_ids.append(ref.get("idref", ""))
        chapters: list[Chapter] = []
        href_to_id: dict[str, str] = {}
        for item_id in spine_ids:
            entry = manifest.get(item_id)
            if entry is None:
                raise EpubError(f"spine item {item_id!r} missing from manifest")
            href, media_type, _props = entry
            if media_type not in ("application/xhtml+xml", "text/html",
                                  "application/x-dtbook+xml"):
                continue
            try:
                raw = zf.read(base + href).decode("utf-8", errors="replace")
            except KeyError as exc:
                raise EpubError(f"spine file missing from archive: {href}") from exc
            chapter = Chapter(id=item_id, title=_chapter_title(raw, href),
                              href=href, text=xhtml_to_text(raw))
            chapters.append(chapter)
            href_to_id[href] = item_id
            href_to_id[href.split("#")[0]] = item_id

        raw_toc: list[TocEntry] = []
        if nav_href:
            raw_toc = _nav_toc(zf, base, manifest, nav_href)
        if not raw_toc and toc_id and toc_id in manifest:
            raw_toc = _ncx_toc(zf, base, manifest[toc_id][0])
        if not raw_toc:
            for item_id in manifest:
                if manifest[item_id][1] == "application/x-dtbncx+xml":
                    raw_toc = _ncx_toc(zf, base, manifest[item_id][0])
                    break
        toc: list[TocEntry] = []
        for entry in raw_toc:
            clean = entry.href.split("#")[0]
            toc.append(TocEntry(title=entry.title,
                                chapter_id=href_to_id.get(clean),
                                href=entry.href))
        if not toc:
            toc = [TocEntry(title=c.title, chapter_id=c.id, href=c.href)
                   for c in chapters]

    return Book(path=str(path), title=title, author=author,
                language=language, identifier=identifier,
                chapters=chapters, toc=toc, cover_href=cover_href,
                stylesheets=stylesheets)


# ------------------------------------------------------------- pagination
def paginate(text: str, width: int, lines_per_page: int) -> list[list[str]]:
    """Wrap text into pages. Repaginating never changes the text."""
    width = max(20, int(width))
    lines_per_page = max(1, int(lines_per_page))
    wrapped: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        wrapped.extend(textwrap.wrap(para, width=width) or [""])
        wrapped.append("")  # paragraph break
    if wrapped and wrapped[-1] == "":
        wrapped.pop()
    if not wrapped:
        return []
    return [wrapped[i:i + lines_per_page]
            for i in range(0, len(wrapped), lines_per_page)]


def search_in_book(book: Book, query: str) -> list[SearchResult]:
    if not query or not query.strip():
        return []
    needle = query.lower()
    results: list[SearchResult] = []
    for ch in book.chapters:
        hay = ch.text.lower()
        start = 0
        while True:
            idx = hay.find(needle, start)
            if idx < 0:
                break
            lo = max(0, idx - 40)
            hi = min(len(ch.text), idx + len(query) + 40)
            snippet = re.sub(r"\s+", " ", ch.text[lo:hi]).strip()
            results.append(SearchResult(book.title, ch.title, idx, snippet))
            start = idx + max(1, len(needle))
    return results


# ---------------------------------------------------------------- reader
@dataclass
class Theme:
    name: str = "light"
    font: str = "default"
    font_size: int = 16
    margins: int = 2
    line_spacing: int = 0
    foreground: str = ""
    background: str = ""

    def effective_width(self, base_width: int) -> int:
        return max(20, int(base_width) - 2 * self.margins
                   - (self.font_size - 16) * 2)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


THEMES: dict[str, Theme] = {
    "light": Theme(name="light", foreground="", background=""),
    "dark": Theme(name="dark", foreground="\x1b[97m", background="\x1b[40m"),
    "sepia": Theme(name="sepia", foreground="\x1b[33m", background="\x1b[43m"),
}


def render_page(lines: list[str], theme: Theme, use_ansi: bool = True) -> str:
    spacer = [""] * theme.line_spacing
    out: list[str] = []
    for line in lines:
        out.append(line)
        out.extend(spacer)
    if out and out[-1] == "" and theme.line_spacing:
        out.pop()
    text = "\n".join(out)
    if use_ansi and (theme.foreground or theme.background):
        return f"{theme.foreground}{theme.background}{text}\x1b[0m"
    return text


class Reader:
    """Positioned view over one book; pagination follows the theme."""

    def __init__(self, book: Book, theme: Theme | None = None,
                 width: int = 80, lines_per_page: int = 24):
        self.book = book
        self.theme = theme or Theme()
        self.width = width
        self.lines_per_page = lines_per_page
        self.chapter_index = 0
        self.page_index = 0

    def _pages(self) -> list[list[str]]:
        if not self.book.chapters:
            return []
        text = self.book.chapters[self.chapter_index].text
        return paginate(text, self.theme.effective_width(self.width),
                        self.lines_per_page)

    @property
    def page_count(self) -> int:
        return len(self._pages())

    def current_page_lines(self) -> list[str]:
        pages = self._pages()
        if not pages:
            return []
        return pages[min(self.page_index, len(pages) - 1)]

    def current_page_text(self, use_ansi: bool = True) -> str:
        return render_page(self.current_page_lines(), self.theme, use_ansi)

    def next_page(self) -> bool:
        pages = self._pages()
        if self.page_index + 1 < len(pages):
            self.page_index += 1
            return True
        return self.next_chapter()

    def prev_page(self) -> bool:
        if self.page_index > 0:
            self.page_index -= 1
            return True
        return self.prev_chapter(last_page=True)

    def next_chapter(self) -> bool:
        if self.chapter_index + 1 < len(self.book.chapters):
            self.chapter_index += 1
            self.page_index = 0
            return True
        return False

    def prev_chapter(self, last_page: bool = False) -> bool:
        if self.chapter_index > 0:
            self.chapter_index -= 1
            self.page_index = max(0, self.page_count - 1) if last_page else 0
            return True
        return False

    def goto_chapter(self, chapter_id_or_index) -> bool:
        if isinstance(chapter_id_or_index, int):
            if 0 <= chapter_id_or_index < len(self.book.chapters):
                self.chapter_index = chapter_id_or_index
                self.page_index = 0
                return True
            return False
        for i, ch in enumerate(self.book.chapters):
            if ch.id == chapter_id_or_index:
                self.chapter_index = i
                self.page_index = 0
                return True
        return False

    def goto_toc(self, title: str) -> bool:
        for entry in self.book.toc:
            if entry.title.lower() == title.lower() and entry.chapter_id:
                return self.goto_chapter(entry.chapter_id)
        return False

    @property
    def progress(self) -> float:
        if not self.book.chapters or self.book.total_chars == 0:
            return 0.0
        before = sum(len(c.text) for c in self.book.chapters[:self.chapter_index])
        pages = self._pages()
        current = self.book.chapters[self.chapter_index].text
        if pages and self.page_index:
            # Approximate: fraction of this chapter's pages consumed.
            before += int(len(current) * self.page_index / len(pages))
        return min(1.0, before / self.book.total_chars)


# ---------------------------------------------------------------- library
class Library:
    def __init__(self):
        self.books: dict[str, Book] = {}

    def import_epub(self, path: str | Path) -> Book:
        book = parse_epub(path)
        self.books[book.path] = book
        return book

    def import_text(self, path: str | Path) -> Book:
        """Convenience only (not part of the EPUB spec): one chapter."""
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        book = Book(path=str(path), title=path.stem,
                    chapters=[Chapter(id="ch0", title=path.stem,
                                      href=path.name, text=text)])
        book.toc = [TocEntry(title=path.stem, chapter_id="ch0", href=path.name)]
        self.books[book.path] = book
        return book

    def import_file(self, path: str | Path) -> Book:
        path = Path(path)
        if path.suffix.lower() == ".epub":
            return self.import_epub(path)
        if path.suffix.lower() == ".txt":
            return self.import_text(path)
        raise EpubError(f"unsupported file type: {path.suffix}")

    def find(self, query: str) -> Book | None:
        q = query.lower()
        for book in self.books.values():
            if q in book.path.lower() or q in book.title.lower():
                return book
        return None

    def list_books(self, sort_by: str = "title") -> list[Book]:
        key = {"title": lambda b: b.title.lower(),
               "author": lambda b: b.author.lower()}.get(sort_by)
        books = list(self.books.values())
        return sorted(books, key=key) if key else books

    def filter_books(self, author: str = "", language: str = "",
                     query: str = "") -> list[Book]:
        out = []
        for book in self.books.values():
            if author and author.lower() not in book.author.lower():
                continue
            if language and language.lower() != book.language.lower():
                continue
            if query:
                hay = f"{book.title} {book.author} {book.language}".lower()
                if query.lower() not in hay:
                    continue
            out.append(book)
        return out

    def search_all(self, query: str) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        results: list[SearchResult] = []
        for book in self.books.values():
            results.extend(search_in_book(book, query))
        return results


# -------------------------------------------------------------- settings
def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, path)


def load_theme(data_dir: Path) -> Theme:
    data = _load_json(Path(data_dir) / "settings.json", None)
    if isinstance(data, dict) and "theme" in data:
        try:
            return Theme.from_dict(data["theme"])
        except (TypeError, ValueError):
            pass
    return Theme()


def save_theme(data_dir: Path, theme: Theme) -> None:
    _save_json(Path(data_dir) / "settings.json", {"theme": theme.to_dict()})


# ------------------------------------------------------------ annotations
class AnnotationStore:
    """Bookmarks / highlights / notes, anchored to chapter text."""

    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / "annotations.json"
        self.data: dict = _load_json(self.path, {})
        if not isinstance(self.data, dict):
            self.data = {}

    def _bucket(self, book: Book) -> dict:
        bucket = self.data.setdefault(book.path, {"bookmarks": [], "highlights": []})
        bucket.setdefault("bookmarks", [])
        bucket.setdefault("highlights", [])
        return bucket

    def save(self) -> None:
        _save_json(self.path, self.data)

    def add_bookmark(self, book: Book, chapter_id: str, offset: int,
                     label: str = "") -> dict:
        ch = book.chapter_by_id(chapter_id)
        excerpt = ""
        if ch is not None:
            excerpt = re.sub(r"\s+", " ", ch.text[offset:offset + 60]).strip()
        mark = {"chapter_id": chapter_id, "offset": int(offset),
                "excerpt": excerpt, "label": label}
        self._bucket(book)["bookmarks"].append(mark)
        return mark

    def add_highlight(self, book: Book, chapter_id: str, start: int,
                      end: int, colour: str = "yellow",
                      note: str = "") -> dict:
        ch = book.chapter_by_id(chapter_id)
        text = ""
        if ch is not None:
            start, end = max(0, start), min(len(ch.text), end)
            text = ch.text[start:end]
        hl = {"chapter_id": chapter_id, "start": int(start), "end": int(end),
              "text": text, "colour": colour, "note": note}
        self._bucket(book)["highlights"].append(hl)
        return hl

    def add_note(self, book: Book, chapter_id: str, start: int, end: int,
                 note: str, colour: str = "yellow") -> dict:
        return self.add_highlight(book, chapter_id, start, end,
                                  colour=colour, note=note)

    def bookmarks(self, book: Book) -> list[dict]:
        return list(self._bucket(book)["bookmarks"])

    def highlights(self, book: Book) -> list[dict]:
        return list(self._bucket(book)["highlights"])

    @staticmethod
    def resolve_highlight(book: Book, highlight: dict) -> tuple[int, int] | None:
        """Return the (start, end) span for a highlight in current text.

        Verifies the stored offset first; if the text moved, re-searches
        the chapter for the exact stored text. Returns None if gone.
        """
        ch = book.chapter_by_id(highlight["chapter_id"])
        if ch is None:
            return None
        text, start, end = highlight["text"], highlight["start"], highlight["end"]
        if text and ch.text[start:end] == text:
            return (start, end)
        if text:
            idx = ch.text.find(text)
            if idx >= 0:
                return (idx, idx + len(text))
        return None


# ------------------------------------------------------- dictionary/wiki
DICTIONARY: dict[str, str] = {
    "serendipity": "The luck of finding something valuable when you were not looking for it.",
    "ephemeral": "Lasting for a very short time.",
    "wander": "To walk slowly, with no particular direction or purpose.",
    "book": "A written work, usually bound, that can be read.",
    "chapter": "A main division of a book.",
    "library": "A collection of books, or the place that holds them.",
    "author": "A person who writes a book.",
    "reader": "A person who reads; also, a device or program for reading books.",
    "story": "An account of events, real or imagined, told for entertainment.",
    "journey": "An act of travelling from one place to another.",
    "brave": "Ready to face danger or pain without fear.",
    "curious": "Eager to know or learn something.",
    "ancient": "Belonging to the very distant past.",
    "mystery": "Something that is difficult to understand or explain.",
    "adventure": "An unusual, exciting, and possibly dangerous activity.",
    "kingdom": "A country ruled by a king or queen.",
    "dragon": "A large, mythical, fire-breathing creature.",
    "ocean": "A very large area of sea.",
    "mountain": "A large natural rise of the earth's surface.",
    "forest": "A large area covered with trees.",
    "river": "A large natural stream of water flowing to a sea or lake.",
    "garden": "A piece of ground where flowers and plants are grown.",
    "letter": "A written message, or a character of an alphabet.",
    "memory": "The ability to remember, or something remembered.",
    "silence": "The absence of sound.",
    "shadow": "A dark area made when light is blocked by something.",
    "light": "The natural agent that makes things visible.",
    "dark": "With little or no light.",
    "dream": "A series of thoughts and images in sleep; also, a hope.",
    "hope": "A feeling of wanting something to happen.",
    "friend": "A person you know well and like.",
    "voyage": "A long journey by sea or in space.",
    "island": "A piece of land surrounded by water.",
    "treasure": "Valuable things, especially hidden or buried riches.",
    "quest": "A long search for something.",
}


def lookup_word(word: str) -> str | None:
    cleaned = re.sub(r"[^a-zA-Z']", "", word or "").lower()
    return DICTIONARY.get(cleaned)


def wikipedia_summary(term: str, opener=None) -> str | None:
    """Return the Wikipedia summary extract, or None on any failure.

    `opener` is injectable for tests: a callable taking a URL string
    and returning an object with a .read() -> bytes interface.
    """
    if not term or not term.strip():
        return None
    url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
           + urllib.parse.quote(term.strip().replace(" ", "_")))
    try:
        if opener is not None:
            raw = opener(url).read()
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "ebook-reader/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
        data = json.loads(raw.decode("utf-8", errors="replace"))
        extract = data.get("extract")
        return extract if isinstance(extract, str) and extract else None
    except Exception:
        return None


# -------------------------------------------------------------------- CLI
def _data_dir(args) -> Path:
    return Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR


def _load_library(args, data_dir: Path) -> tuple[Library, AnnotationStore, Theme]:
    lib = Library()
    # Re-parse every book found under the books subdir, if present.
    books_dir = data_dir / "books"
    if books_dir.is_dir():
        for f in sorted(books_dir.iterdir()):
            if f.suffix.lower() in (".epub", ".txt"):
                try:
                    lib.import_file(f)
                except EpubError:
                    continue
    return lib, AnnotationStore(data_dir), load_theme(data_dir)


def _resolve_book(lib: Library, query: str) -> Book | None:
    if query in lib.books:
        return lib.books[query]
    book = lib.find(query)
    if book is not None:
        return book
    if Path(query).is_file():
        try:
            return lib.import_file(query)
        except EpubError:
            return None
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ebook_reader",
                                     description="Terminal EPUB reader core.")
    parser.add_argument("--data-dir", default=None,
                        help="data directory for annotations/settings")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import", help="import an EPUB/TXT file into the library")
    p.add_argument("file")

    p = sub.add_parser("list", help="list library books")
    p.add_argument("--sort", choices=["title", "author"], default="title")
    p.add_argument("--author", default="")
    p.add_argument("--language", default="")
    p.add_argument("--query", default="")

    p = sub.add_parser("toc", help="show a book's table of contents")
    p.add_argument("--book", required=True)

    p = sub.add_parser("read", help="read a page of a book")
    p.add_argument("--book", required=True)
    p.add_argument("--chapter", type=int, default=0)
    p.add_argument("--page", type=int, default=0)
    p.add_argument("--width", type=int, default=80)

    p = sub.add_parser("search", help="full-text search across the library")
    p.add_argument("query")

    p = sub.add_parser("bookmark", help="add a bookmark")
    p.add_argument("--book", required=True)
    p.add_argument("--chapter", type=int, default=0)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--label", default="")

    p = sub.add_parser("bookmarks", help="list a book's bookmarks")
    p.add_argument("--book", required=True)

    p = sub.add_parser("highlight", help="add a highlight (optionally with a note)")
    p.add_argument("--book", required=True)
    p.add_argument("--chapter", type=int, default=0)
    p.add_argument("--start", type=int, required=True)
    p.add_argument("--end", type=int, required=True)
    p.add_argument("--colour", default="yellow")
    p.add_argument("--note", default="")

    p = sub.add_parser("highlights", help="list a book's highlights")
    p.add_argument("--book", required=True)

    p = sub.add_parser("theme", help="show or set the theme")
    p.add_argument("--set", choices=list(THEMES), default=None)

    p = sub.add_parser("lookup", help="offline dictionary lookup")
    p.add_argument("word")

    p = sub.add_parser("wikipedia", help="Wikipedia summary lookup")
    p.add_argument("term")

    args = parser.parse_args(argv)
    data_dir = _data_dir(args)

    if args.cmd == "import":
        src = Path(args.file)
        dest_dir = data_dir / "books"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        dest.write_bytes(src.read_bytes())
        try:
            book = parse_epub(dest) if dest.suffix.lower() == ".epub" else None
        except EpubError as exc:
            dest.unlink(missing_ok=True)
            print(f"import failed: {exc}", file=sys.stderr)
            return 1
        print(f"imported: {book.title if book else dest.stem} by "
              f"{book.author if book else ''}")
        return 0

    lib, store, theme = _load_library(args, data_dir)

    if args.cmd == "list":
        books = lib.filter_books(author=args.author, language=args.language,
                                 query=args.query)
        books = sorted(books, key=lambda b: (b.title if args.sort == "title"
                                             else b.author).lower())
        for b in books:
            print(f"{b.title} — {b.author} [{b.language}] ({len(b.chapters)} ch)")
        return 0

    if args.cmd in ("toc", "read", "bookmark", "bookmarks",
                    "highlight", "highlights"):
        book = _resolve_book(lib, args.book)
        if book is None:
            print(f"book not found: {args.book}", file=sys.stderr)
            return 1
        if args.cmd == "toc":
            for e in book.toc:
                print(f"- {e.title}")
            return 0
        if args.cmd == "read":
            reader = Reader(book, theme=theme, width=args.width)
            if not reader.goto_chapter(args.chapter):
                print("chapter out of range", file=sys.stderr)
                return 1
            reader.page_index = args.page
            print(reader.current_page_text(use_ansi=False))
            print(f"[chapter {args.chapter + 1}/{len(book.chapters)}, "
                  f"progress {reader.progress:.0%}]")
            return 0
        if args.cmd == "bookmark":
            ch = book.chapters[args.chapter]
            mark = store.add_bookmark(book, ch.id, args.offset, args.label)
            store.save()
            print(f"bookmark saved: {mark['label'] or mark['excerpt']}")
            return 0
        if args.cmd == "bookmarks":
            for m in store.bookmarks(book):
                print(f"- ch={m['chapter_id']} @{m['offset']} "
                      f"{m['label'] or m['excerpt']}")
            return 0
        if args.cmd == "highlight":
            ch = book.chapters[args.chapter]
            hl = store.add_highlight(book, ch.id, args.start, args.end,
                                     colour=args.colour, note=args.note)
            store.save()
            print(f"highlight saved ({hl['colour']}): {hl['text'][:60]!r}")
            return 0
        if args.cmd == "highlights":
            for hl in store.highlights(book):
                span = store.resolve_highlight(book, hl)
                print(f"- [{hl['colour']}] {hl['text'][:60]!r} "
                      f"span={span} note={hl['note']!r}")
            return 0

    if args.cmd == "search":
        results = lib.search_all(args.query)
        for r in results:
            print(f"{r.book_title} / {r.chapter_title} @{r.offset}: {r.snippet}")
        if not results:
            print("no matches")
        return 0

    if args.cmd == "theme":
        if args.set:
            theme = THEMES[args.set]
            save_theme(data_dir, theme)
            print(f"theme set to {args.set}")
        else:
            print(f"current theme: {theme.name} (font {theme.font}, "
                  f"size {theme.font_size}, margins {theme.margins}, "
                  f"spacing {theme.line_spacing})")
        return 0

    if args.cmd == "lookup":
        definition = lookup_word(args.word)
        print(definition if definition else f"not found: {args.word}")
        return 0

    if args.cmd == "wikipedia":
        summary = wikipedia_summary(args.term)
        print(summary if summary else f"no Wikipedia summary for: {args.term}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
