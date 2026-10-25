# yq — DESIGN

Single file: `ccyq.py` (Python 3 standard library only; imports are
`sys` and `re` only).
Layout, in order:

1. `YQError(Exception)` — every user-visible failure.
2. Scalar typing (`parse_scalar_token`): quoted → str; `null`/`~`/
   empty → None; bool spellings → bool; int (dec/hex/octal, signs,
   underscores stripped); float (incl. `.inf`/`.nan`); else str.
3. Comment stripping (`strip_comment`): scans a line tracking single/
   double quote state; a `#` preceded by whitespace (or at position 0)
   outside quotes ends the line. Quotes inside plain scalars do not
   toggle state unless they open the scalar — handled by checking
   whether the quote is at a scalar start; conservative rule: a quote
   toggles only when the previous non-space char is `:`, `-`, `[`,
   `{`, `,`, or start-of-line, which covers real quoted scalars and
   keeps apostrophes in plain text (e.g. `Tailor's`) intact.
4. Flow parser (`parse_flow`): small recursive-descent over a string
   with an index cursor; handles `[...]`, `{...}`, quoted strings,
   plain tokens up to `,]}:` boundaries, and nested flows. A flow
   value must fit on one logical line in block context.
5. Block parser: lines are pre-processed into `(indent, text, raw)`
   triples with tabs-in-indent rejected. `parse_block(lines, i, indent)`
   dispatches on whether the first line starts with `- ` / `-` at that
   indent (sequence) or contains a top-level `:` (mapping) or is a
   bare scalar (single-line document). `parse_mapping` and
   `parse_sequence` recurse:
   - Mapping value present on the same line → scalar/flow/block
     scalar, or (if it is a `>`/`|` header) a block scalar consumed
     from the following more-indented lines.
   - Mapping value absent → look ahead: next block with indent
     greater than the key's indent is the nested value; a sequence
     block at indent >= the key's indent is an indentless sequence.
   - Sequence item `- <text>`: the text may itself be `key: value`
     (start of an inline mapping whose continuation lines are
     indented beyond the dash) — handled by rewriting the item line
     as a virtual mapping line at indent `dash_indent + 2` and
     parsing a mapping from it plus following lines. A `- - nested`
     item is handled by the same rewrite for sequences.
   - Block scalars: consume lines with indent > parent indent (or
     blank lines); folded joins lines with a space, literal keeps
     newlines; chomping applied at the end; explicit indent indicator
     overrides the detected content indent.
   - Multi-line plain scalars: a continuation line more-indented than
     the key, which is not a new key/sequence item, is folded onto
     the previous plain scalar with a space.
6. Query parser (`parse_filter`): splits on top-level `|` (depth and
   quote aware), then each stage is parsed into steps:
   `.` alone → identity; `.name` → key step; `.[...]` → key (quoted
   or bare) or index (integer) step; `[]` → iterate step; a trailing
   `?` on a step marks it optional. `[filter]` as a whole stage is an
   array-constructor step wrapping an inner filter. Steps after the
   first in a stage need no leading dot when they follow a bracket
   (`.quotes[0]`), but a stage must start with `.` or `[`.
7. Query evaluator (`eval_filter`): works on lists of values, so pipes
   and iteration compose naturally. Each step maps a value list to a
   new value list: key/index steps map 1→1 (null on missing key /
   out-of-range, error on wrong type unless optional); iterate maps
   1→N; constructor maps N→1 (a list of all outputs so far — in
   practice it re-runs its inner filter on the stage input and wraps
   the result list); pipe feeds stage outputs as the next stage's
   inputs. A constructor as a non-final stage feeds its single list
   value onward, which is the natural jq-like behaviour.
8. Emitter (`dump_yaml`): recursive; mappings `key: value` with
   nested blocks indented 2 spaces; sequences `- item` with the item's
   nested content indented to align after `- `; scalars via
   `format_scalar`: plain when safe (checked against a conservative
   regex plus the typed-scalar recogniser — a string that would
   re-parse as bool/null/number is quoted), double-quoted with
   escapes when it contains `:`+space, ` #`, leading indicator chars,
   or control characters, `""` for empty, and literal block `|-`
   for multi-line strings (lines indented 2 under the key/dash).
   `None` → `null`, `True`/`False` → `true`/`false`, floats via
   `repr` (with `.inf`/`.nan` spellings normalised back).
9. CLI (`main`): argument disambiguation (see SPEC), read file or
   stdin, parse, evaluate, print. Multi-output results (bare `[]`
   final stage) are joined with `---` separator lines. Errors print
   `ccyq: <message>` to stderr and exit 2.

## Testing approach

`tests/test_ccyq.py` is a `unittest` suite that drives the tool in
two ways: (a) direct import of parser/evaluator/emitter functions for
fine-grained cases, and (b) subprocess runs of `ccyq.py` for CLI
behaviour (exit codes, stdout/stderr separation). Fixture
`tests/quotes.yaml` reconstructs the page's five quotes. Round-trip
tests (parse → emit → parse) guard the emitter against changing
values. No network, no servers, no ports are involved.
