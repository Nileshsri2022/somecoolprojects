# SPEC — Static Site Generator

## Challenge source (resolved, read before writing anything)

- Challenge: **Build Your Own Static Site Generator**
- URL: https://codingchallenges.fyi/challenges/challenge-ssg/
- Found via web search for `codingchallenges.fyi static site generator challenge`
  (first result) and confirmed by reading the full page. The tags page
  https://codingchallenges.fyi/challenges/tags lists `beginner` and `cli`,
  matching this project's assigned tags.
- The page is a Hugo-like generator. It is NOT a blogging platform and
  does not specify a Markdown dialect, a template language beyond two
  placeholders, index/archive pages, or incremental rebuilds.

## Challenge steps, as written on the page

- Step Zero: pick a stack that makes serving a site easy. Python was
  chosen (standard library only, so `http.server` covers serving).
- Step 1: initialise a project — create a new directory for the project
  with a basic homepage with placeholder headings/text. The page's
  example is `ccssg mysite` producing `mysite/index.html`.
- Step 2: create a theme — `ccsg new theme cc` producing
  `mysite/themes/cc/index.html`, and the homepage content moves into
  the theme's `index.html`.
- Step 3: manage theme and content separately — the generator should
  NO LONGER create an `index.html` in the site root. Instead create
  `content/index.md`, and add a command to add content, e.g.
  `ccssg new page about` producing `content/about.md` alongside
  `content/index.md`.
- Step 4: turn the theme `index.html` into a template with
  `{{ Title }}` and `{{ Content }}` placeholders, and add a build
  command that renders every page in `content/` through that template,
  replacing `{{ Content }}` with the transformed Markdown and
  `{{ Title }}` with the first top-level (`#`) header in the Markdown
  file. Output goes to a new directory `public/` (`about.md` →
  `public/about.html`, `index.md` → `public/index.html`). The `public/`
  directory is what would be deployed.
- Step 5: serve a development version that updates when the user edits
  any page or the theme ("livereload").
- Going Further (NOT required by the core steps): blogging, generating
  menus, more tags, sitemaps and analytics, other Hugo features.

## What this implementation does

Single file `ssg.py` (Python 3 standard library only), run as
`python3 ssg.py <command>`. Commands (all accept `--site <dir>`,
defaulting to the current directory when it looks like a site, i.e.
it contains `content/`; `new` takes the site name as its argument):

```
python3 ssg.py new mysite                  # create mysite/content/index.md
python3 ssg.py new theme cc --site mysite  # create mysite/themes/cc/index.html
python3 ssg.py new page about --site mysite
                                           # create mysite/content/about.md
python3 ssg.py build --site mysite         # render content/*.md -> public/*.html
python3 ssg.py build --site mysite --theme cc
python3 ssg.py serve --site mysite         # dev server, default http://127.0.0.1:8000
python3 ssg.py serve --site mysite --port 8080
```

- `new <name>`: creates `<name>/content/index.md` with a placeholder
  `#` heading and text. It does NOT create a root `index.html`
  (see Divergence 1).
- `new theme <name>`: creates `themes/<name>/index.html` containing the
  default template from Step 4 (DOCTYPE, `{{ Title }}`, `{{ Content }}`).
  Fails if that theme already exists.
- `new page <slug>`: creates `content/<slug>.md` with a placeholder
  `#` heading derived from the slug. Nested slugs such as
  `blog/first-post` create subdirectories and build to the matching
  `public/blog/first-post.html`. Fails if the page already exists.
  Slugs containing `..` or absolute paths are rejected.
- `build`: walks `content/` recursively, converts each `.md` file to
  HTML, wraps it in the chosen theme template, and writes the result
  to `public/` mirroring the relative path with a `.html` extension.
  Theme choice: `--theme` if given; otherwise the single theme found
  under `themes/` if there is exactly one; otherwise a built-in
  default template (same placeholders). If several themes exist and
  no `--theme` is given, build fails with a message listing them.
  A `static/` directory inside the site, if present, is copied
  verbatim into `public/` (see Divergence 4).
- `serve`: builds once, then serves `public/` on
  `http://127.0.0.1:8000` by default (override with `--port`, and
  `--host` if needed). A background poller checks `content/`,
  `themes/` and `static/` every 0.5 s and rebuilds when anything
  changes, so a browser refresh after an edit shows the new output
  (see Divergence 3 on livereload).

## Supported Markdown subset (exact — nothing beyond this is claimed)

Block level: ATX headings `#`–`######`; paragraphs (blank-line
separated); fenced code blocks (```); unordered lists (`-` or `*`
items, single level only); ordered lists (`1.` items, single level
only); blockquotes (`>` lines, single level only); horizontal rules
(`---`, `***` or `___` on a line alone). Inline: `**bold**`,
`*italic*`, `` `code` ``, links `[text](url)`, images
`![alt](src)`. Raw HTML in source text is escaped, not passed
through. NOT supported: nested lists, tables, footnotes, task lists,
definition lists, setext headings, reference-style links, YAML front
matter, or Markdown inside blockquotes/lists beyond plain inline
formatting. A file with no `#` heading uses a title derived from its
file name (`about-us` → `About Us`).

## Supported template features (exact)

Exactly two placeholders, matched case-sensitively with optional
surrounding whitespace: `{{ Title }}` and `{{ Content }}`. No other
tags, no conditionals, no loops, no partials, no filters. A template
missing `{{ Content }}` still builds (the content is simply not
inserted); a template missing `{{ Title }}` leaves the `<title>` (or
wherever it would go) untouched. Unknown `{{ ... }}` text is left
verbatim. `{{ Title }}` is HTML-escaped; `{{ Content }}` is the
generated HTML and is not re-escaped.

## Deliberate divergences from the page

1. **Step 1 vs Step 3 site layout.** Step 1 shows a root `index.html`;
   Step 3 explicitly says the generator should "no longer create an
   `index.html` in the root directory" and should create
   `content/index.md` instead. This implementation follows Step 3
   (the page's own later instruction) for `new`: the created site
   contains `content/index.md` only, no root `index.html`.
2. **Command names unified.** The page itself is inconsistent
   (`ccssg mysite`, `ccsg new theme cc`, `ccssg new page about`).
   This tool is `ssg.py` with one consistent grammar:
   `new <site>`, `new theme <name>`, `new page <slug>`, `build`,
   `serve`. The page's names are not supported.
3. **Livereload is poll-and-rebuild, not browser auto-refresh.**
   Step 5 asks for a dev version that "updates when the user edits"
   content or theme. `serve` rebuilds automatically on change, but
   it does NOT inject a livereload script or push a refresh to an
   open browser tab: the user refreshes the browser to see the
   change. No WebSocket, no injected JavaScript.
4. **`static/` copying is an addition, not a page step.** The page
   never mentions static assets. Copying `static/` → `public/` is
   included because a real site needs CSS/images, and it is
   documented here rather than presented as a challenge step.
   If no `static/` directory exists, nothing extra is copied.
5. **Full rebuild every time.** The page does not specify
   incremental rebuild, so `build` regenerates `public/` from
   scratch (the directory is removed and recreated). No caching,
   no incremental or dependency tracking is claimed.
6. **Theme auto-selection rule is an addition.** The page never says
   what happens with zero or several themes. Rule used: `--theme`
   wins; else exactly one theme is used automatically; else the
   built-in template is used (zero themes) or build fails asking
   for `--theme` (several themes).

## NOT built (honestly — do not claim these)

- Hosting or deployment (AWS S3/CloudFront, Cloudflare Pages, or any
  upload step). `public/` output is deployable by hand; nothing here
  deploys it.
- Blogging: no post dates, archives, tag pages, RSS, or pagination.
  `content/index.md` is just a page; there is no generated index
  listing of other pages beyond what the author writes by hand.
- Menus, extra template tags, sitemaps, analytics (all "Going
  Further" items).
- Incremental rebuild (see Divergence 5), file watching via OS
  events (polling only), live browser reload (see Divergence 3).
- A custom web server: serving uses Python's standard
  `http.server` (the page itself suggests Go/Python for this).
- Multi-theme fallback chains, theme inheritance, or per-page
  template selection: every page uses the one chosen theme's
  `index.html`.

## Errors (exit code non-zero, message on stderr)

- `new <name>` when the directory already exists.
- `new theme` / `new page` when the target already exists, when the
  site has no `content/` directory, or when a slug is unsafe.
- `build` / `serve` when the site has no `content/` directory, when
  a named theme does not exist, or when several themes exist and no
  `--theme` was given.
- Unknown command or missing arguments (usage printed).
