# DESIGN — yaml-parser

## Overview

`yaml_parser.py` is a single-file, standard-library-only,
hand-written parser. No PyYAML or any other YAML library is used
(and none is in the standard library). Pipeline:

```
text -> split into raw lines -> significant lines (comments
stripped, blanks dropped, tab indentation rejected) -> recursive
descent over significant lines by indentation -> Python value
-> CLI prints json.dumps(value, indent=2)
```

## Line model

- A `RawLine` keeps `lineno`, `indent` (count of leading spaces),
  and `text` (content after the indent). A line whose indent
  contains a tab raises `YamlError` immediately.
- A `SigLine` (significant line) adds `raw_index` so block-scalar
  consumption can switch back to the raw lines (where blank lines
  and comments matter) and then resynchronise.
- Comment stripping scans a line tracking single/double quote
  state; a `#` that is at the start or preceded by a space/tab
  and is outside quotes ends the line. A `#` inside a quoted
  string, or glued to a plain scalar (`a#b`), is kept.
- `---` (only as the very first significant line) and `...` (as
  the last significant line) are accepted and dropped. A second
  `---` anywhere else is an error (multi-document not supported).

## Recursive descent by indentation

- `parse_block(indent)` dispatches on the current significant
  line: a line starting with `- ` (or exactly `-`) is a sequence,
  a line containing a mapping key is a mapping, anything else is
  a single scalar document (top level only).
- `parse_mapping(indent)` consumes consecutive lines at exactly
  `indent`. A line indented *more* than `indent` where a key was
  expected is an "unexpected indentation" error; a line indented
  less ends the mapping. A sequence line at this indent ends the
  mapping (its caller handles it).
- Key splitting finds the first `:` outside quotes and flow
  brackets that is followed by a space or end-of-line. A line
  with no such colon inside a mapping is an error, not a silent
  string. Keys are parsed with the same scalar rules as values.
- A key with an empty inline value looks at the next significant
  line:
  - indent greater than the key's indent -> nested block;
  - same indent and a sequence item -> block sequence belonging
    to this key (the page's `- 1` indented one space, or flush
    with the key, both work);
  - anything else -> `None` (null).
- `parse_sequence(indent)` consumes consecutive `-` items at
  exactly `indent`. Item content:
  - empty -> nested block on following lines, else `None`;
  - a mapping start (`key: ...`) -> a mapping whose first key
    is on the dash line and whose continuation keys sit at
    `indent + 2` (the column after `"- "`);
  - a nested sequence start (`- ...`) -> a sequence at
    `indent + 2`, same first-line trick;
  - a block-scalar indicator (`>`, `|`, with chomping) ->
    block scalar whose content is indented more than `indent`;
  - anything else -> inline scalar / flow value.
- The first-line trick is implemented by passing the dash-line
  content into `parse_mapping`/`parse_sequence` as a virtual
  first line, so continuation lines are handled by the normal
  loop and indentation errors stay consistent.

## Block scalars

When a mapping value (or sequence item) is `>`, `|`, `>-`,
`>+`, `|-`, `|+` (an explicit indentation digit such as `|2`
is rejected), content is consumed from the *raw* lines:
blank lines are tentatively included, lines indented more than
the parent indent belong, and the first non-blank line at or
below the parent indent ends the block. The block indent is the
indent of the first non-blank content line; content is dedented
by that amount.

- Literal (`|`): lines joined with `\n`.
- Folded (`>`): lines in one paragraph joined with a single
  space; each blank line contributes one `\n` (standard
  "more-indented line" handling is not special-cased: a
  more-indented line still folds with a space, which is a
  documented simplification).
- Chomping, applied after joining: clip (default) strips
  trailing blank lines and adds one `\n` (empty content stays
  `""`); strip (`-`) adds nothing; keep (`+`) keeps every
  trailing blank line as a `\n`.
- After consumption, the significant-line cursor is resynced to
  the first significant line at or after the raw line where the
  block ended.

## Flow values

A small character parser over the inline string handles `[` /
`]` sequences and `{` / `}` mappings, nested arbitrarily, with
quoted strings (same escape rules) and plain scalars (terminated
by `,`, `]`, `}`, or, in a flow mapping, by `:` followed by a
space, `,`, or `}`). Unclosed brackets/quotes raise `YamlError`
naming the line. Flow scalars are typed with the same rules as
block scalars.

## Scalar typing (plain scalars, YAML 1.1)

Order matters — checked in this order:

1. Empty / `~` / `null` (any case) -> `None`.
2. Boolean: `y|yes|n|no|true|false|on|off` (any case) ->
   `True`/`False`. Single `y`/`n` included per YAML 1.1.
3. Integer: `[-+]?[0-9]+` (underscores allowed, stripped) ->
   `int`, base 10; `0x[0-9a-fA-F]+` -> hex; `0o[0-7]+` ->
   octal; a leading-zero literal of only `0-7` digits with
   length > 1 (e.g. `023332`) -> legacy octal. A leading-zero
   literal containing `8`/`9` (e.g. `08`) falls back to decimal
   rather than erroring, since it is not a valid octal.
4. Float: `[-+]?` digits with a `.` and/or exponent, plus
   `.inf` / `-.inf` / `+.inf` / `.nan` (any case) ->
   `float('inf')` / `float('-inf')` / `float('nan')`.
5. Anything else -> the string as written (plain scalars are
   stripped of surrounding whitespace; internal whitespace kept).

## Quoted scalars

- Double-quoted: escapes `\0 \a \b \t \n \v \f \r \e \" \\`
  plus `\xHH`, `\uHHHH`, `\UHHHHHHHH`; an unknown escape is an
  error, not passed through silently. A trailing `"` must end
  the value; trailing junk after a quoted scalar is an error.
- Single-quoted: `''` decodes to one `'`; backslashes are
  literal (no escape processing). Same trailing-junk rule.
- A quoted scalar may not span lines (multi-line quoted scalars
  are not supported; an unterminated quote is an error).

## Errors

`YamlError` carries `message` and optional `lineno`. Every
error raised while parsing names a line number: tab
indentation, unexpected indentation, missing mapping colon,
duplicate key, unclosed quote/flow bracket, unsupported
anchor/alias/tag/directive, second document marker, and
explicit-indentation block indicators. The CLI prints
`yaml_parser.py: line N: <message>` to stderr and exits 1.

## Assumptions and simplifications

- Indentation is spaces only; mixed space counts are allowed
  as long as sibling lines share one indent (no fixed 2-space
  rule — the page's 1-space sequence indent requires this).
- Duplicate keys are an error (stricter than YAML).
- Timestamps and sexagesimal numbers stay strings.
- Folded scalars fold more-indented lines with a space
  (YAML would keep their newlines); this is a corner case and
  is not covered by the page's examples.
- One document per input; `---`/`...` are markers, not content.
