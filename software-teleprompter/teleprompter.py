#!/usr/bin/env python3
"""Software teleprompter (terminal core).

Loads a script (text, file, or URL), formats it (margins, line
spacing, font-size-scaled wrapping, lightweight Markdown, mirroring)
and scrolls it at an adjustable speed in words per minute.

Terminal-only: there is no GUI/web UI and no real font rendering.
``font_face`` is stored metadata; ``font_size`` scales the wrap width
(larger font -> fewer characters per line). See docs/SPEC.md for the
honest scope statement.

Usage:
    python3 teleprompter.py --file script.txt --dump
    python3 teleprompter.py --url https://example.com/script.md --wpm 180
    cat script.txt | python3 teleprompter.py --dump
    python3 teleprompter.py --file script.txt --play --seconds 10

Interactive (curses) keys: Space pause/resume, +/- speed, m mirror,
h/l left margin, q quit.
"""

import argparse
import math
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEFAULT_FONT_SIZE = 24
DEFAULT_WPM = 150
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 72
MIN_WPM = 10
MAX_WPM = 600
MAX_LINE_SPACING = 3
MIN_EFFECTIVE_WIDTH = 20
URL_TIMEOUT_SECONDS = 15
MIRROR_MODES = ("none", "horizontal", "vertical", "both")


# ---------------------------------------------------------------- settings

@dataclass
class TeleprompterSettings:
    """All user-adjustable settings, validated on construction."""

    font_face: str = "monospace"
    font_size: int = DEFAULT_FONT_SIZE
    left_margin: int = 4
    right_margin: int = 4
    line_spacing: int = 0  # extra blank lines between lines; 0 = single
    mirror: str = "none"
    wpm: int = DEFAULT_WPM

    def __post_init__(self):
        if not isinstance(self.font_face, str) or not self.font_face.strip():
            raise ValueError("font_face must be a non-empty string")
        if not MIN_FONT_SIZE <= self.font_size <= MAX_FONT_SIZE:
            raise ValueError(
                f"font_size must be {MIN_FONT_SIZE}-{MAX_FONT_SIZE}, "
                f"got {self.font_size}"
            )
        if self.left_margin < 0 or self.right_margin < 0:
            raise ValueError("margins must be >= 0")
        if not 0 <= self.line_spacing <= MAX_LINE_SPACING:
            raise ValueError(
                f"line_spacing must be 0-{MAX_LINE_SPACING}, "
                f"got {self.line_spacing}"
            )
        if self.mirror not in MIRROR_MODES:
            raise ValueError(f"mirror must be one of {MIRROR_MODES}, got {self.mirror!r}")
        if not MIN_WPM <= self.wpm <= MAX_WPM:
            raise ValueError(f"wpm must be {MIN_WPM}-{MAX_WPM}, got {self.wpm}")

    def effective_width(self, width: int) -> int:
        """Wrap width for a terminal of `width` columns."""
        base = width - self.left_margin - self.right_margin
        if base <= MIN_EFFECTIVE_WIDTH:
            return max(base, 1)
        scaled = int(base * DEFAULT_FONT_SIZE / self.font_size)
        return max(MIN_EFFECTIVE_WIDTH, min(base, scaled))


# ---------------------------------------------------------------- script

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_EMPHASIS_RE = re.compile(r"(\*\*|__)(.+?)\1|(\*|_)(.+?)\3|`([^`]+)`")


def _strip_inline_markdown(text: str) -> str:
    text = _LINK_RE.sub(r"\1", text)

    def _repl(match):
        # Groups: 1=open **/__ , 2=its content, 3=open */_ , 4=its
        # content, 5=`code` content. Return content, never the opener.
        for group in (match.group(2), match.group(4), match.group(5)):
            if group is not None:
                return group
        return ""

    return _EMPHASIS_RE.sub(_repl, text)


class Script:
    """A loaded script: raw text plus lightweight Markdown rendering."""

    def __init__(self, text: str):
        self.text = text

    @classmethod
    def load_text(cls, text: str) -> "Script":
        return cls(text)

    @classmethod
    def load_file(cls, path: str) -> "Script":
        with open(path, "r", encoding="utf-8") as handle:
            return cls(handle.read())

    @classmethod
    def load_url(cls, url: str) -> "Script":
        try:
            with urllib.request.urlopen(url, timeout=URL_TIMEOUT_SECONDS) as resp:
                raw = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            raise ImportError(f"failed to import script from {url}: {exc}") from exc
        return cls(raw.decode("utf-8", errors="replace"))

    def markdown_lines(self) -> list:
        """Raw text -> plain lines: headings upper-cased, markers stripped.

        Blank lines are preserved as paragraph breaks.
        """
        lines = []
        for raw in self.text.splitlines():
            stripped = raw.strip()
            if not stripped:
                lines.append("")
                continue
            heading = _HEADING_RE.match(stripped)
            if heading:
                lines.append(_strip_inline_markdown(heading.group(1)).upper())
            else:
                lines.append(_strip_inline_markdown(stripped))
        return lines

    def average_words_per_line(self) -> float:
        words = [len(line.split()) for line in self.markdown_lines() if line.strip()]
        if not words:
            return 10.0
        return sum(words) / len(words)


# ---------------------------------------------------------------- rendering

def render_lines(script: Script, settings: TeleprompterSettings, width: int) -> list:
    """Format a script into display lines.

    Order: Markdown -> wrap -> margins -> line-spacing blanks -> mirror.
    Margins are applied after horizontal mirroring so the left margin
    stays on the left.
    """
    wrap_width = settings.effective_width(width)
    wrapped = []
    for line in script.markdown_lines():
        if not line:
            wrapped.append("")
        else:
            wrapped.extend(
                textwrap.wrap(
                    line, width=wrap_width, break_long_words=True,
                    break_on_hyphens=False,
                )
                or [""]
            )
    spaced = []
    for line in wrapped:
        spaced.append(line)
        for _ in range(settings.line_spacing):
            spaced.append("")
    # Drop a trailing run of spacing blanks so the script does not end
    # in a long blank tail; interior spacing is untouched.
    while spaced and spaced[-1] == "":
        spaced.pop()
    if settings.mirror in ("horizontal", "both"):
        spaced = [line[::-1] for line in spaced]
    margined = [(" " * settings.left_margin) + line for line in spaced]
    if settings.mirror in ("vertical", "both"):
        margined.reverse()
    return margined


# ---------------------------------------------------------------- playback

class Player:
    """Scrolling playback over a rendered line list (headless)."""

    def __init__(self, lines: list, wpm: int = DEFAULT_WPM):
        if not MIN_WPM <= wpm <= MAX_WPM:
            raise ValueError(f"wpm must be {MIN_WPM}-{MAX_WPM}, got {wpm}")
        self.lines = list(lines)
        self.wpm = wpm
        self._avg_words = self._compute_avg_words()
        self.offset = 0.0
        self.playing = False

    def _compute_avg_words(self) -> float:
        words = [len(line.split()) for line in self.lines if line.strip()]
        return (sum(words) / len(words)) if words else 10.0

    @property
    def lines_per_second(self) -> float:
        return self.wpm / self._avg_words

    def set_wpm(self, wpm: int) -> None:
        if not MIN_WPM <= wpm <= MAX_WPM:
            raise ValueError(f"wpm must be {MIN_WPM}-{MAX_WPM}, got {wpm}")
        self.wpm = wpm

    def start(self) -> None:
        if not self.at_end():
            self.playing = True

    def stop(self) -> None:
        self.playing = False

    def toggle(self) -> None:
        if self.playing:
            self.stop()
        else:
            self.start()

    def step(self, dt_seconds: float) -> None:
        """Advance by lines_per_second * dt, only while playing."""
        if not self.playing or dt_seconds <= 0:
            return
        self.offset = min(
            float(max(len(self.lines) - 1, 0)),
            self.offset + self.lines_per_second * dt_seconds,
        )
        if self.at_end():
            self.playing = False

    def visible_lines(self, height: int) -> list:
        start = int(math.floor(self.offset))
        return self.lines[start:start + max(height, 0)]

    def at_end(self) -> bool:
        return self.offset >= max(len(self.lines) - 1, 0)

    def reset(self) -> None:
        self.offset = 0.0
        self.playing = False

    def seek(self, line: int) -> None:
        self.offset = float(min(max(line, 0), max(len(self.lines) - 1, 0)))

    def progress(self) -> float:
        if len(self.lines) <= 1:
            return 1.0
        return self.offset / (len(self.lines) - 1)


# ---------------------------------------------------------------- curses UI

def run_curses(stdscr, script: Script, settings: TeleprompterSettings) -> None:
    """Interactive UI. Thin loop over render_lines/Player; not unit-tested."""
    import curses

    curses.curs_set(0)
    stdscr.timeout(50)
    stdscr.keypad(True)
    player = None

    def rebuild():
        nonlocal player
        height, width = stdscr.getmaxyx()
        lines = render_lines(script, settings, width)
        offset = player.offset if player is not None else 0.0
        was_playing = player.playing if player is not None else False
        player = Player(lines, settings.wpm)
        player.offset = min(offset, max(len(lines) - 1, 0))
        player.playing = was_playing

    rebuild()
    last = time.monotonic()
    while True:
        now = time.monotonic()
        player.step(now - last)
        last = now
        height, width = stdscr.getmaxyx()
        stdscr.erase()
        for row, line in enumerate(player.visible_lines(height - 1)):
            try:
                stdscr.addstr(row, 0, line[: max(width - 1, 0)])
            except curses.error:
                pass
        status = (
            f" {'PLAYING' if player.playing else 'PAUSED'} | {settings.wpm} WPM "
            f"| font {settings.font_face} {settings.font_size}pt "
            f"| margins {settings.left_margin}/{settings.right_margin} "
            f"| spacing {settings.line_spacing} | mirror {settings.mirror} "
            f"| {int(player.progress() * 100)}% | Space pause, +/- speed, "
            f"m mirror, h/l margin, q quit"
        )
        try:
            stdscr.addstr(height - 1, 0, status[: max(width - 1, 0)], curses.A_REVERSE)
        except curses.error:
            pass
        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), 27):
            break
        if key == ord(" "):
            player.toggle()
        elif key == ord("+") or key == ord("="):
            try:
                settings.wpm = min(MAX_WPM, settings.wpm + 10)
                player.set_wpm(settings.wpm)
            except ValueError:
                pass
        elif key == ord("-"):
            try:
                settings.wpm = max(MIN_WPM, settings.wpm - 10)
                player.set_wpm(settings.wpm)
            except ValueError:
                pass
        elif key == ord("m"):
            nxt = MIRROR_MODES[(MIRROR_MODES.index(settings.mirror) + 1) % len(MIRROR_MODES)]
            settings.mirror = nxt
            rebuild()
        elif key == ord("h"):
            if settings.left_margin > 0:
                settings.left_margin -= 1
                rebuild()
        elif key == ord("l"):
            settings.left_margin += 1
            rebuild()


# ---------------------------------------------------------------- CLI

def _load_script(args) -> Script:
    if args.url:
        return Script.load_url(args.url)
    if args.file:
        return Script.load_file(args.file)
    if not sys.stdin.isatty():
        return Script.load_text(sys.stdin.read())
    return Script.load_text("")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Terminal software teleprompter.")
    parser.add_argument("--file", help="path to a plain-text/Markdown script file")
    parser.add_argument("--url", help="URL to import a plain-text/Markdown script from")
    parser.add_argument("--wpm", type=int, default=DEFAULT_WPM, help="scroll speed in words per minute")
    parser.add_argument("--font", default="monospace", help="font face name (stored; terminal cannot render fonts)")
    parser.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE, help="font size in points (8-72; scales wrap width)")
    parser.add_argument("--left-margin", type=int, default=4)
    parser.add_argument("--right-margin", type=int, default=4)
    parser.add_argument("--line-spacing", type=int, default=0, help="extra blank lines between lines (0-3)")
    parser.add_argument("--mirror", choices=list(MIRROR_MODES), default="none")
    parser.add_argument("--width", type=int, default=80, help="terminal width for --dump/--play")
    parser.add_argument("--height", type=int, default=20, help="viewport height for --play")
    parser.add_argument("--dump", action="store_true", help="print the formatted script and exit")
    parser.add_argument("--play", action="store_true", help="non-interactive timed playback (no curses)")
    parser.add_argument("--seconds", type=float, default=10.0, help="duration for --play")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = TeleprompterSettings(
            font_face=args.font, font_size=args.font_size,
            left_margin=args.left_margin, right_margin=args.right_margin,
            line_spacing=args.line_spacing, mirror=args.mirror, wpm=args.wpm,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        script = _load_script(args)
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dump:
        for line in render_lines(script, settings, args.width):
            print(line)
        return 0

    if args.play:
        lines = render_lines(script, settings, args.width)
        player = Player(lines, settings.wpm)
        player.start()
        deadline = time.monotonic() + args.seconds
        last = time.monotonic()
        while time.monotonic() < deadline and not player.at_end():
            now = time.monotonic()
            player.step(now - last)
            last = now
            print("\n".join(player.visible_lines(args.height)))
            print("---")
            time.sleep(0.5)
        return 0

    try:
        import curses
    except ImportError:
        print("error: curses is unavailable; use --dump or --play instead", file=sys.stderr)
        return 1
    try:
        curses.wrapper(run_curses, script, settings)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
