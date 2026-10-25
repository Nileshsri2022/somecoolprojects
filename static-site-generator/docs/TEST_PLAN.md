# TEST_PLAN — Static Site Generator

Run from the project directory:

```
python3 -m unittest discover -s tests -v
```

All tests use temporary directories; none touch the real filesystem
outside a temp dir, and none need network access (the `serve` test
binds to 127.0.0.1 on an ephemeral port and shuts its server down
in a `finally` block).

## Coverage

### CLI / site creation

1. `new` creates `content/index.md` with a `#` heading and no root
   `index.html` (Step 3 layout, SPEC Divergence 1).
2. `new` fails when the target directory already exists.
3. `new theme` creates `themes/<name>/index.html` containing
   `{{ Title }}` and `{{ Content }}`; fails on a duplicate theme.
4. `new page` creates `content/<slug>.md`; nested slugs create
   subdirectories; fails on a duplicate page; rejects `../evil`
   and absolute slugs.
5. Unknown command and missing arguments exit non-zero.

### Markdown conversion (unit tests on `markdown_to_html`)

6. Headings `#`–`######` map to `<h1>`–`<h6>`; `##` does not become
   the page title.
7. Paragraphs, blank-line separation, `**bold**`, `*italic*`,
   `` `code` ``, links, images.
8. Unordered and ordered lists; fenced code blocks (content escaped,
   not interpreted); blockquotes; horizontal rules.
9. Raw HTML in source is escaped (`<b>` stays literal text).

### Title and template

10. Title is the first `#` heading; a file with no `#` heading falls
    back to its file-name-derived title.
11. `{{ Title }}` (with varied inner whitespace) and
    `{{ Content }}` are substituted; unknown `{{ Foo }}` is left
    verbatim; title text is escaped in the output.

### Build

12. Full end-to-end build: `index.md` + `about.md` through a theme
    produce `public/index.html` and `public/about.html` with the
    right titles and converted bodies.
13. Nested content builds to nested `public/` paths.
14. Build with no themes uses the built-in template; with exactly
    one theme uses that theme; with several themes and no `--theme`
    fails; with `--theme` picks the named one; unknown `--theme`
    fails.
15. Rebuild wipes stale output: deleting a `.md` file and rebuilding
    removes its `.html`.
16. `static/` files are copied verbatim into `public/`; a site
    without `static/` builds fine.
17. Build fails cleanly when `content/` is missing.

### Dev server

18. `serve` (started in a subprocess on an ephemeral port) serves
    the built `public/index.html` over HTTP; after editing a source
    `.md` file and waiting for the poller, a fresh GET returns the
    updated content. The subprocess is terminated in `finally`;
    no server is left running after the suite.

## Not covered (deliberately)

- Deployment/hosting, blogging/archives/RSS, menus, sitemaps,
  analytics, incremental rebuild, browser auto-refresh: none of
  these are implemented (see SPEC.md "NOT built"), so there is
  nothing to test for them beyond the documented absences.
- Nested lists, tables, front matter: explicitly unsupported
  Markdown features; tests assert only the documented subset.
