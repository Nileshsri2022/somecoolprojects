# loc-counter — SPEC

Coding Challenges: Build Your Own LOC Counter
(https://codingchallenges.fyi/challenges/challenge-loc-counter/)
— slug used: `challenge-loc-counter`. Found by web search; the
first-guess URL worked, no 404 correction was needed.

## What it is

A command-line tool, `loc.py`, that walks a directory tree and
counts lines of code per file and in total, split into blank,
comment, and code lines — a small local version of `cloc` /
`scc`, as the challenge page frames it.

```sh
python3 loc.py <directory>          # per-language summary (default)
python3 loc.py --files <directory>  # per-file breakdown
python3 loc.py --json <directory>   # JSON output (files + languages + total)
python3 loc.py --json --files <directory>  # same JSON (it always includes files)
```

A single file path is also accepted in place of a directory
(small extension of Step 1, which specifies a directory).

## Challenge steps (from the page)

- **Step 0 — setup:** Python 3, standard library only.
- **Step 1 — scan:** accept a single argument, the starting
  directory, and identify all source files in it and its
  subdirectories. Files are matched by extension against the
  language table (see DESIGN.md); unknown extensions are
  skipped, not counted.
- **Step 2 — blank vs non-blank:** scan each file, then print
  a summary (default) or a per-file breakdown (`--files`).
- **Step 3 — code vs comments:** a line whose first
  non-whitespace character is the comment character counts as
  a comment; C-like languages also get multi-line
  (`/* ... */`) comment support.
- **Step 4 — code + block-comment start on one line:** e.g.
  `i++; /*` followed by `comment` and `*/` counts as one line
  of code and two lines of comment. Rule generalised: a line
  counts once, as code if it contains any code outside
  comments, otherwise as a comment (if it contains comment
  content). So a closing line with code after `*/` also
  counts as code, and a closing line with nothing (or only a
  trailing line comment) after `*/` counts as a comment.
- **Step 5 — plain text and Markdown:** plain text counts
  blank vs non-blank only (non-blank lines are code,
  comments are always 0). Markdown counts fenced code blocks:
  lines inside a fence — and the fence delimiter lines
  themselves — count as code; non-blank prose outside a
  fence also counts as code (matching the page's `scc`
  example, where Markdown lines are all code), blank lines
  are blank. There is no comment category for Markdown.
- **Step 6 — additional languages, table-driven:** adding a
  language is adding one row to the `LANGUAGES` table in
  `loc.py` (extension -> language name, line comment,
  block comment delimiters, or a special kind for Markdown /
  plain text). No code change is needed for a new language
  with those comment forms.

## Output

Text summary (default), modelled on the page's `scc` example
but without complexity or COCOMO columns (see "Out of scope"):

```
Language                 Files     Lines   Blanks  Comments     Code
Python                       2        42       8         5       29
Total                        2        42       8         5       29
```

Text per-file output (`--files`) has the same columns with a
`File` column holding paths relative to the scanned root,
sorted alphabetically.

JSON output (`--json`) is an object with three keys:

```json
{"files": [{"path": "...", "language": "Python", "lines": 42,
            "blanks": 8, "comments": 5, "code": 29}],
 "languages": {"Python": {"files": 2, "lines": 42, "blanks": 8,
                          "comments": 5, "code": 29}},
 "total": {"files": 2, "lines": 42, "blanks": 8, "comments": 5, "code": 29}}
```

Every counted file satisfies `lines == blanks + comments + code`.

## Supported languages

| Language   | Extensions                              | Line comment | Block comment |
|------------|-----------------------------------------|--------------|---------------|
| Python     | `.py`, `.pyi`                           | `#`          | —             |
| C          | `.c`                                    | `//`         | `/* */`       |
| C Header   | `.h`                                    | `//`         | `/* */`       |
| C++        | `.cpp`, `.cc`, `.cxx`, `.hpp`           | `//`         | `/* */`       |
| Java       | `.java`                                 | `//`         | `/* */`       |
| JavaScript | `.js`                                   | `//`         | `/* */`       |
| TypeScript | `.ts`                                   | `//`         | `/* */`       |
| Go         | `.go`                                   | `//`         | `/* */`       |
| Rust       | `.rs`                                   | `//`         | `/* */`       |
| Shell      | `.sh`, `.bash`                          | `#`          | —             |
| Ruby       | `.rb`                                   | `#`          | —             |
| Markdown   | `.md`                                   | — (fences)   | —             |
| Text       | `.txt`                                  | —            | —             |

## Errors

- Missing argument, unknown flag: usage message on stderr,
  exit code 2 (argparse).
- Path that does not exist, or is neither a file nor a
  directory: message on stderr, exit code 2, nothing on
  stdout.
- An unreadable file or a file that cannot be decoded is
  skipped silently only if it looks binary (contains a NUL
  byte); other read errors propagate as a non-zero exit
  rather than silently undercounting — in practice the
  walker only meets regular files, so this path is
  defensive. Files that decode with replacement characters
  (invalid UTF-8) are still counted.

## Out of scope (deliberate)

- No complexity metric and no COCOMO cost/schedule estimates
  (the page's "Going Further" items). The core steps stop at
  blank/comment/code counts; inventing estimate formulas
  would be speculation beyond them.
- No `.gitignore` / ignore-file handling, no `--exclude`
  flag: hidden files and directories (names starting with
  `.`, which covers `.git`) are skipped, and that is the
  only exclusion rule.
- No per-language configuration file on disk: the language
  table lives in `loc.py` itself, which is what Step 6's
  "adding some config" amounts to at this size.
