# loc-counter — DESIGN

Assumptions, stated before coding (ponytail: think first,
minimum code, nothing speculative).

## Pipeline

```
path
  -> count_directory() / count_file()   walk + classify, per file
  -> summarize()                        per-language aggregates + total
  -> format_*() / JSON                  text table or JSON object
```

One public counting entry per level: `count_file(path)`
returns a `FileCounts` (path, language, lines, blanks,
comments, code); `count_directory(root)` returns a sorted
list of them; `summarize(files)` returns
`(languages_dict, total_dict)`. The CLI (`main`) only parses
argv and prints.

## Language table (Step 6)

`LANGUAGES` maps an extension (lowercased, with dot) to a
`Language` record: name, line-comment marker (or `None`),
block-comment start/end (or `None`), and a kind:
`"code"`, `"markdown"`, or `"text"`. Adding a language is
one table row. `.h` maps to "C Header" (as `scc` does),
not to C, because a header is not C source.

## Walking

`os.walk` with sorted directory/file names for deterministic
output. Hidden subdirectories (name starting with `.`) are
pruned, hidden files are skipped, symlinked directories are
not followed (`os.walk` default). Unknown extensions are
skipped. A file whose bytes contain NUL is treated as binary
and skipped. Remaining files are decoded as UTF-8 with
`errors="replace"` and split with `str.splitlines()`, so a
final line without a trailing newline still counts as a line.

## Line classification (code languages)

A single left-to-right scan, `_scan_line`, tracks whether
the scanner is inside a block comment and returns
`(has_code, has_comment, in_block_after)`:

- Blank lines (`strip() == ""`) count as blank and never
  change block state — even inside a block comment.
- A line-comment marker outside a string ends the line's
  scan: everything after it is comment.
- A block-comment start outside a string enters block state;
  a block end leaves it. Text on either side is scanned too,
  so a line is classified by what it actually contains.
- String literals (`"` or `'`) on the same line are skipped
  over (backslash escapes honoured), so a comment marker
  inside a string, e.g. `"# not a comment"` or
  `"// not a comment"`, does not start a comment. The
  string literal itself counts as code.
- Classification of one line: code if `has_code`, else
  comment if `has_comment`, else (unreachable for a
  non-blank line, since non-comment characters are code)
  code. This single rule implements Steps 3 and 4:
  `i++; /*` has code, so it is code; the following lines
  inside the block have only comment, so they are comments;
  `*/ int x;` has code after the block end, so it is code;
  `/* only */` has no code, so it is a comment.

## Line classification (special kinds)

- Text: blank -> blank, anything else -> code.
- Markdown: a fence state toggles on lines whose stripped
  form starts with ` ``` ` or `~~~` (the info string after
  the fence, e.g. ` ```python `, is ignored). Fence
  delimiters and lines inside a fence count as code;
  non-blank lines outside a fence count as code; blank
  lines count as blank. No line is ever a comment.

## Known limitations (documented, not hidden)

- The string scanner is a single-line heuristic, not a
  lexer: comment markers inside a multi-line string
  (e.g. a Python triple-quoted string spanning lines) may
  be miscounted, because block/string state is only tracked
  for block comments. Likewise a Rust lifetime annotation
  (`&'a`) can look like an unterminated string to the
  scanner; the line still counts as code (it contains code
  before the quote), but a block comment starting after
  such a quote on the same line could be missed.
- Comment markers inside a line comment are irrelevant
  (scanning stops there), and nested block comments are
  not supported: the first `*/` closes the block, which
  matches C/Java/Go behaviour.
- Line counting uses `splitlines()`, so exotic line
  boundaries (`\v`, `\f`, `\x1c` etc., which `splitlines`
  also splits on) count as line breaks. Normal `\n` and
  `\r\n` files are unaffected.

## Success criteria (verifiable)

- `python3 -m unittest discover -s tests -v` passes.
- On a fixture tree with hand-counted files, every file
  satisfies `lines == blanks + comments + code` and the
  per-language totals equal the sum of the fixture counts.
- The Step 4 example counts as 1 code + 2 comment lines.
- The CLI's default, `--files`, and `--json` outputs agree
  with each other on the same fixture tree.
