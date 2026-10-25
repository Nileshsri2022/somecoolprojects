# SPEC — Build Your Own YAML Parser

## Challenge source (resolved, not guessed)

- Challenge: **Coding Challenge #67 — YAML Parser**, by John Crickett.
- Canonical page read for this build:
  `https://codingchallenges.substack.com/p/coding-challenge-67-yaml-parser`
- How it was resolved: the fyi tag pages were opened first
  (`https://codingchallenges.fyi/challenges/tags`, which lists the
  `intermediate` and `parsing` tags), and a web search for
  "codingchallenges.fyi YAML parser challenge" returned the Substack
  page as its top hit and confirmed the title "Build Your Own YAML
  Parser" on the fyi `intermediate` tag page. The challenge steps
  below are taken from that page's content as returned by search.
- Honest retrieval caveat: a direct text fetch of the Substack page
  and of the fyi parsing tag page was refused with HTTP 429
  (rate limit) during this build, so the steps below rest on the
  search-returned body of the page, not on a fresh full-page fetch.
  No fyi challenge URL is asserted here, because none was verified
  by readback; the Substack URL above is the verified source.
- This is a **different** challenge from `yq` (query/filter YAML):
  this one only parses YAML text into Python data (dict / list /
  scalar), printed as JSON by the CLI.

## Challenge steps (from the page)

### Step 1 — Simple nested mapping

```yaml
name: Coding Challenges
challenge:
  name: YAML Parser
```

must produce the equivalent of:

```json
{
  "name": "Coding Challenges",
  "challenge": {
    "name": "YAML Parser"
  }
}
```

### Step 2 — String, numeric, boolean and null scalars

```yaml
key1: true
key2: off
key3: null
key4: value
key5: 101
key6: ~
key7: 0x12d4
key8: 023332
key9: .inf
key10: .NAN
```

The page says to refer to the YAML specification for the valid and
invalid values of each type. Applied here as YAML 1.1 scalar rules
(see "Scalar typing" in DESIGN.md):

| Key | Value |
| --- | --- |
| key1 | `true` (bool) |
| key2 | `false` — `off` is a YAML 1.1 boolean |
| key3 | `null` |
| key4 | `"value"` (string) |
| key5 | `101` (int) |
| key6 | `null` — `~` is null |
| key7 | `4820` — `0x12d4` hex |
| key8 | `9946` — `023332` legacy octal |
| key9 | `Infinity` |
| key10 | `NaN` |

### Step 3 — Quoted vs plain strings, folded and literal blocks

Quoted strings translate control characters; plain strings do not:

```yaml
quoted: "Coding Challenges\n"
non: Coding Challenges\n
```

`quoted` ends in a real newline; `non` ends in the two characters
`\` and `n`.

Folded (`>`) strings spread over lines are concatenated without
newlines:

```yaml
message: >
  this is an example from
  the YAML parser Coding Challenge
  that spans more than
  one line
```

is `message: this is an example from the YAML parser Coding
Challenge that spans more than one line` (plus the single trailing
newline that YAML "clip" chomping adds — see DESIGN.md).

Literal (`|`) strings are interpreted as written, including the
newlines.

### Step 4 — Objects and arrays, block and flow style

```yaml
key: value
array:
 - 1
 - 2
dict:
  innerkey: innervalue
```

or the flow-sequence form:

```yaml
key: value
array: [1, 2]
dict:
  innerkey: innervalue
```

and flow mappings:

```yaml
john: { writes: Coding Challenges, loves: dogs, hates: meetings }
```

Note the page's block-sequence example indents `- 1` by only one
space under `array:` — sequences under a mapping key may sit at
the same indentation as the key, so that form is supported.

### Step 5 — Own tests and useful errors

Add tests to be confident the parser handles valid YAML and fails
with useful error messages on invalid YAML, digging into the YAML
specification for what has not been covered. Implemented here as:
the suite in `tests/test_yaml_parser.py` plus `YamlError` messages
that always name the offending line number (see TEST_PLAN.md).

## Supported YAML subset (honest scope)

- Block mappings and block sequences, arbitrarily nested.
- Sequences of mappings (`- key: value` with continuation keys).
- Scalars: null, YAML 1.1 booleans, ints (decimal, `0x` hex,
  `0o` octal, legacy leading-zero octal), floats (decimal,
  exponent, `.inf` / `-.inf` / `.nan` in any case), plain strings.
- Single-quoted strings (`''` = one `'`, no escape processing)
  and double-quoted strings (standard escapes, see DESIGN.md).
- Folded (`>`, `>-`, `>+`) and literal (`|`, `|-`, `|+`) block
  scalars with clip/strip/keep chomping.
- Flow sequences `[a, b]` and flow mappings `{k: v}`, nested,
  including inside block values and sequence items.
- Comments: full-line `#` comments and ` #` trailing comments
  outside quotes and outside block scalars.
- Blank lines; a leading `---` document marker and a trailing
  `...` end marker (single document only).
- Top-level mapping, sequence, or scalar document; empty
  document parses to `null`.
- Keys may be plain, single-quoted, or double-quoted. Keys are
  passed through the same scalar typing as values, so e.g.
  `101: x` yields an integer key (JSON output renders it as
  `"101"`).

## Deliberately NOT built

- **Not full YAML spec compliance.** This is the subset above.
- Anchors (`&a`), aliases (`*a`), merge keys (`<<`), tags
  (`!!str`, `!custom`), and directives (`%YAML`, `%TAG`): a
  value starting with `&`, `*`, or `!` is rejected with an error
  rather than silently mis-parsed.
- Multi-document streams: a second `---` raises an error.
- Timestamps: `2026-10-25` stays a string (not converted to a
  date object) — simpler and JSON-friendly.
- Sexagesimal numbers (`1:30`): left as a plain string.
- Complex keys (`? key`), sets, and block scalars with explicit
  indentation indicators (`|2`): rejected with an error.
- Multi-line plain scalars (a plain value continued on the next
  indented line without `>`/`|`): not supported; the continuation
  line raises an "unexpected indentation" error.
- Tab indentation: rejected with an error (YAML forbids tabs for
  indentation).
- Duplicate keys in one mapping: rejected with an error (stricter
  than YAML, which leaves it implementation-defined).

## Divergences from the page

1. **Boolean set is YAML 1.1, not YAML 1.2 core.** YAML 1.2 core
   only recognises `true`/`false`, but the page's own example
   requires `off` to be boolean, so `yes`/`no`/`on`/`off`/`y`/`n`
   (any case) are booleans here.
2. **Folded/literal trailing newline.** The page's folded example
   says the result is "equivalent to" the single-line string; YAML
   clip chomping actually appends one trailing `\n`. This parser
   follows YAML (clip = one trailing newline), documented in
   DESIGN.md, rather than the page's shorthand.
3. **Strict duplicate keys** (see "NOT built" above): an error,
   where a lenient parser would silently keep one value.
4. **Retrieval caveat** (above): steps rest on the search-returned
   page body after a 429 on direct fetch, not on a fresh fetch.
   No step has been invented beyond what that body states.

## CLI contract

```sh
python3 yaml_parser.py FILE        # parse FILE, print JSON (indent 2)
python3 yaml_parser.py              # read YAML from stdin
python3 yaml_parser.py FILE --json  # same as default (explicit flag)
```

- Exit code 0 on success, 1 on parse error or unreadable file.
- Errors go to stderr as `yaml_parser.py: line N: <message>`
  (or without a line number for file errors).
- `Infinity`/`NaN` print as JSON `Infinity`/`NaN` (Python's
  `json` default); integer keys print as JSON strings.
