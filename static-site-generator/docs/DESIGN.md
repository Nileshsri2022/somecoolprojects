# DESIGN — Static Site Generator

## Overview

One file, `ssg.py`, Python 3 standard library only. No third-party
Markdown library exists in the standard library, so the Markdown
converter is hand-written for exactly the subset documented in
SPEC.md. The CLI is `argparse`-free on purpose in the small
subcommand dispatcher: `new`, `new theme`, `new page`, `build`,
`serve`, each parsed by a tiny hand-rolled parser so `--site`,
`--theme`, `--port` and `--host` behave identically everywhere.

## Layout of a site (created by `new`, extended by other commands)

```
mysite/
  content/            # source pages, *.md, may contain subdirectories
    index.md
    about.md
  themes/             # optional; one directory per theme
    cc/
      index.html      # template with {{ Title }} and {{ Content }}
  static/             # optional; copied verbatim to public/
  public/             # generated output only; wiped on every build
    index.html
    about.html
```

`public/` is treated as purely generated: `build` removes it and
recreates it. Nothing the user cares about should live only there.

## Module structure inside ssg.py

- `DEFAULT_TEMPLATE` — the built-in template, identical in shape to
  the theme template written by `new theme`.
- `escape_html(text)` — `&`, `<`, `>`, `"` escaping for text/code/title.
- `render_inline(text)` — code spans first (protected from later
  passes), then images, links, bold, italic. HTML-escaping happens
  before inline markup is applied so raw `<` in source never becomes
  markup, while the markup this function itself emits is untouched.
- `markdown_to_html(text)` — line-based block parser. State machine
  over fenced-code blocks, lists, blockquotes, headings, rules and
  paragraphs; a paragraph is flushed on a blank line or a block
  boundary. Lists and blockquotes are single-level by design.
- `extract_title(text, fallback)` — first `# ` line, else the
  file-name-derived fallback.
- `render_template(template, title, content)` — two regex
  substitutions, `{{\s*Title\s*}}` and `{{\s*Content\s*}}`.
- `find_site_dir(explicit)` — `--site` if given, else the current
  directory if it contains `content/`; otherwise an error naming
  the missing directory.
- `resolve_theme(site, name)` — implements the SPEC selection rule
  and raises a clear error for unknown/ambiguous themes.
- `build_site(site, theme_name)` — wipes and recreates `public/`,
  renders every `.md` under `content/` (sorted, recursive), copies
  `static/` if present, returns the list of written HTML files.
- `cmd_new_site / cmd_new_theme / cmd_new_page` — creators; all
  refuse to overwrite existing targets.
- `serve_site(site, theme_name, host, port)` — builds once, starts a
  `ThreadingHTTPServer` serving `public/`, and a daemon poller thread
  that snapshots mtimes of `content/`, `themes/` and `static/` every
  0.5 s and rebuilds on change. `Ctrl-C` (KeyboardInterrupt) stops
  the server cleanly.
- `main(argv)` — dispatcher returning an exit code; `SsgError`
  exceptions become `Error: ...` on stderr with exit code 1.

## Key decisions and why

- **Hand-written Markdown, not a dependency.** The task requires
  standard library only. The subset is deliberately small so the
  converter stays auditable and its limits can be documented exactly.
- **Full rebuild, not incremental.** The page does not ask for
  incremental builds; wiping `public/` also guarantees no stale
  `.html` survives a deleted or renamed `.md` file.
- **Polling, not inotify.** Standard library has no portable file
  watcher; a 0.5 s mtime poll is simple, cross-platform, and good
  enough for a dev server. No browser auto-refresh is injected,
  keeping generated HTML byte-identical to template + content.
- **Title from first `#` only.** The page says "first top level
  header"; `##` headings do not count, and a file without one falls
  back to its file name rather than failing.
- **Theme template is a plain file, not a language.** Only two
  placeholders are substituted, so a theme author needs no new
  syntax and templates stay ordinary HTML.

## Testing approach

See TEST_PLAN.md. Tests live in `tests/test_ssg.py`, use
`unittest` and `tempfile.TemporaryDirectory` fixture sites, invoke
the CLI through `main()` in-process (fast, no subprocess except the
`serve` test, which must exercise a real HTTP port), and compare
generated HTML files byte-for-byte or by substring where whitespace
is incidental. No network access is needed by any test.
