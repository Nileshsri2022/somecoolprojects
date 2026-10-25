# Static Site Generator

A small Hugo-like static site generator in a single Python 3 file,
standard library only. Built for the Coding Challenges challenge
[Build Your Own Static Site Generator](https://codingchallenges.fyi/challenges/challenge-ssg/).

## Quick start

```
python3 ssg.py new mysite
python3 ssg.py new theme cc --site mysite
python3 ssg.py new page about --site mysite
python3 ssg.py build --site mysite
python3 ssg.py serve --site mysite   # http://127.0.0.1:8000
```

Edit `mysite/content/*.md`, refresh the browser, and the dev server
rebuilds automatically (polling; it does not push a refresh to an
open tab). The deployable output is `mysite/public/`.

## Commands

| Command | Effect |
| --- | --- |
| `new <name>` | Create a site with `content/index.md` |
| `new theme <name> --site <dir>` | Create `themes/<name>/index.html` template |
| `new page <slug> --site <dir>` | Create `content/<slug>.md` |
| `build --site <dir> [--theme <name>]` | Render `content/` to `public/` |
| `serve --site <dir> [--port N] [--host H]` | Build, serve `public/`, rebuild on change |

`--site` defaults to the current directory when it contains a
`content/` directory. Run `python3 ssg.py --help` for usage.

## Templates

A theme is one file, `themes/<name>/index.html`, containing two
placeholders: `{{ Title }}` (first `#` heading of the page, or the
file name if there is none) and `{{ Content }}` (the converted
Markdown). No other template tags exist. With no themes, a built-in
template with the same two placeholders is used; with several
themes, pass `--theme`.

## Markdown supported

Headings `#`–`######`, paragraphs, `**bold**`, `*italic*`,
`` `code` ``, fenced code blocks, `-`/`*` and `1.` lists (single
level), `>` blockquotes, `---` rules, links and images. Tables,
nested lists, footnotes and front matter are NOT supported. Raw
HTML in source is escaped.

## What is NOT included

Hosting/deployment, blogging/archives/RSS, menus, sitemaps,
analytics, incremental builds, and browser auto-refresh. See
`docs/SPEC.md` for the full, honest list of divergences and limits.

## Tests

```
python3 -m unittest discover -s tests -v
```
