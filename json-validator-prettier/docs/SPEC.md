# SPEC — JSON Validator And Prettier

Source: Coding Challenges, "Build Your Own JSON Validator And Prettier"
(<https://codingchallenges.fyi/challenges/challenge-json-validator>), re-read
2026-10-26 before any code was written. This spec follows that page; nothing
below is invented beyond the deliberate divergences listed at the end.

## Challenge steps (as written on the page)

- **Step Zero** — choose platform and language.
- **Step 1** — a UI with a large text input where users paste JSON; error
  messages must say what went wrong and where.
- **Step 2** — parse the input as JSON and validate it. If valid, display it
  nicely formatted with consistent indentation. If invalid, show a clear
  message with line number / character position / description.
  Page examples:
  - Valid: `{"name": "John", "job": "software engineer", "country": "United Kingdom"}`
    formats to the same object indented by 2 spaces.
  - Invalid, missing comma: `{"name": "John" "job": "software engineer"}`
    must produce an error, not formatted output.
  - Invalid, trailing comma: `{"name": "John",  "job": "software engineer",}`
    must produce a clear error.
  - Minified valid JSON must format correctly when validated.
- **Step 3** — sort keys alphabetically at every level of nesting, each
  object independently. Page examples:
  - `{"zebra": 1, "apple": 2, "banana": 3}`
    → `{"apple": 2, "banana": 3, "zebra": 1}`
  - `{"z": {"b": 1, "a": 2}, "a": {"y": 3, "x": 4}}`
    → `{"a": {"x": 4, "y": 3}, "z": {"a": 2, "b": 1}}`
- **Step 4** — compress: remove all non-essential whitespace (spaces,
  newlines, tabs between structural elements) while preserving whitespace
  inside string values. Page example:
  - formatted `{"name": "John", "message": "Hello World"}` (pretty form)
    → `{"name":"John","message":"Hello World"}` (space inside the string kept).
  - Newlines inside strings must also be tested, and it must be possible to
    return to the pretty version (here: re-run without `--compress`).
- **Step 5** — convert valid JSON to YAML, handling objects, arrays, strings,
  numbers, booleans and null, with correct indentation. Page examples:
  - `{"name": "John", "age": 30}` → `name: John` / `age: 30`
  - `{"person": {"name": "John", "hobbies": ["reading", "coding"]}}` →
    `person:` / `  name: John` / `  hobbies:` / `    - reading` / `    - coding`
  - `{"active": true, "count": 0, "message": null, "score": 9.5}` →
    `active: true` / `count: 0` / `message: null` / `score: 9.5`
- **Going Further** — copy-to-clipboard, configurable formatting, dark mode.

## What this build does

A CLI tool, `json_pretty.py` (Python 3, standard library only):

```
python3 json_pretty.py [options] [file]
cat file.json | python3 json_pretty.py [options]
python3 json_pretty.py --help
```

Input: a file path, `-`, or stdin when no file is given.

| Option | Effect |
| --- | --- |
| (no mode flag) | Validate, then pretty-print with 2-space indent (the page's "validate" button). |
| `--check` | Verdict only: prints `Valid JSON` on success, nothing else. |
| `--sort` | Pretty-print (or YAML, if combined) with keys sorted recursively. |
| `--compress` / `--minify` | Minified output: all whitespace outside strings removed. |
| `--yaml` | JSON → YAML conversion. |
| `--indent N` | Indent width for pretty-print (default 2; also the YAML step width). Must be an integer from 1 to 8; anything else is a usage error (exit 2). |

Modes combine predictably: `--sort` applies before any output mode, so
`--sort --yaml` emits sorted YAML and `--sort --compress` emits sorted,
minified JSON. One exception to the token-level compress rule: sorting
cannot be expressed by stripping whitespace from the original text, so
`--sort --compress` re-serializes the sorted value compactly (string
values and numbers are preserved, but original escape/number spellings
are normalized, as in pretty-print). `--compress --yaml` and
`--check` combined with `--compress`/`--yaml` are rejected as
contradictory (usage error, exit 2) rather than silently picking one.

## Output and exit codes

- Valid input: transformed output on stdout, exit 0. Every output ends with
  exactly one trailing newline.
- Invalid input: no transformed output. stderr carries
  `Invalid JSON: <message> at line L, column C`, followed by the offending
  source line and a `^` caret under the reported column, exit 1.
- Missing/unreadable file, unknown flag, or contradictory flags: a plain
  error on stderr, exit 2.
- Empty or whitespace-only input is invalid JSON ("Expecting value",
  line 1, column 1), not an empty success.

## JSON dialect accepted

Standard JSON only (RFC 8259 as implemented by Python's `json` module with
strict constants — see DESIGN):

- Objects, arrays, strings (including `\u` escapes), numbers (integer and
  floating point, including exponents), `true`, `false`, `null`.
- Rejected: trailing commas, missing commas, single-quoted strings,
  unquoted keys, trailing content after the top-level value, comments,
  `NaN` / `Infinity` / `-Infinity` (Python's `json` accepts these by default;
  this tool rejects them, because they are not JSON).
- Duplicate object keys: last value wins, as in Python's `json` (documented,
  not an error — JSON itself does not forbid them, and the page is silent).
- Numbers are re-emitted in normalized form by the pretty/YAML emitters
  (e.g. `1e2` parses to `100.0` and prints as `100.0`; `1.50` prints as
  `1.5`). Values are preserved; literal spellings are not. The exception is
  `--compress`, which is a token-level whitespace strip of the original text
  (see DESIGN), so original spellings and escapes survive there.
- Non-ASCII characters are emitted as-is (UTF-8) in pretty and YAML output,
  not `\u`-escaped, so the output stays readable.

## YAML dialect emitted

No YAML library is used (standard library only); the emitter in
`json_pretty.py` produces a plain subset of YAML:

- Mappings as `key: value`, nested mappings indented one step (default 2).
- Sequences as `- item`, indented one step below the owning key (matching
  the page's example, where `hobbies:` items sit two spaces deeper than
  `hobbies` itself, not flush with it).
- A mapping inside a sequence puts its first key on the dash line
  (`- name: John`, following keys aligned under it); a sequence inside a
  sequence puts the inner items one step deeper.
- Empty object → `{}`, empty array → `[]` (flow form, on the key line).
- Scalars: `true` / `false` / `null`; numbers as parsed; strings plain when
  safe, otherwise double-quoted with escapes (see DESIGN for the quoting
  rule). Strings containing a real newline are double-quoted with `\n`
  escapes, not block scalars.
- A top-level scalar or empty input document: a scalar input (e.g. `"hi"`,
  `42`) converts to that scalar alone; this is valid YAML for the value.
- Round-tripping through a real YAML parser is NOT verified here (no YAML
  library is available in the standard library); the emitter is tested
  against the page's examples and its own documented quoting/indentation
  rules instead. That is a stated limit, not a claim of full YAML compliance.

## Deliberate divergences from the page (honest list)

1. **CLI, not a paste-in web UI.** The page explicitly allows a CLI tool
   ("your project, your choice", and CLI tools are called out as a current
   trend), so Step 1's "large text input box" is stdin/a file instead of a
   browser box, and error "highlighting" is the caret line on stderr.
2. **Parsing via Python's `json` module, not a hand-written parser.**
   The page itself points at the JSON parser challenge as a prerequisite,
   and a hand-written parser already exists in this series
   (`somecoolprojects/json-parser`). Re-implementing it here would add
   nothing; the original work in this tool is the error-location reporting,
   the token-level compressor, the recursive sorter and the YAML emitter.
   Strictness beyond `json`'s defaults (rejecting `NaN`/`Infinity`) is added
   explicitly.
3. **Going Further, partially built.** Configurable formatting IS built
   (`--indent`). Copy-to-clipboard and dark mode are NOT built: both are
   UI concepts with no meaning for a CLI (clipboard access would also need
   a platform tool outside the standard library), and are recorded here
   rather than silently dropped.
4. **No web UI, no file watching, no schema validation.** The page asks
   for syntax validation only; JSON Schema validation is out of scope.
