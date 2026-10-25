# qr-code-generator — Build Your Own QR Code Generator

Coding Challenges #32, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

Generates QR codes from scratch in pure Python 3 standard
library: mode detection, bit encoding and padding,
Reed–Solomon error correction over GF(256), interleaving,
function patterns, all 8 data masks with penalty evaluation,
format/version information, and rendering as ASCII art, SVG,
or PNG (hand-written with `zlib` — no Pillow, no `qrcode`).

Versions 1–10, error-correction levels L/M/Q/H, numeric /
alphanumeric / byte modes. Kanji is not implemented (byte
mode covers the same text); see `docs/DESIGN.md` for the
documented divergences from the challenge page, including
its arithmetically inconsistent version-4 Q block row.

## Usage

```sh
python3 qr_code.py 'HELLO WORLD'
python3 qr_code.py 'HELLO WORLD' --ec Q --svg out.svg --png out.png
python3 qr_code.py '12345' --version 4 --mask 0
```

ASCII art goes to stdout; `--svg` / `--png` write files.
`--scale` sets pixels per module (default 10); the default
output includes the 4-module quiet zone (`--no-quiet-zone`
omits it). Bad EC level, version, or mask, and input that
does not fit the chosen version, exit non-zero with a
message on stderr.

Library use:

```python
from qr_code import generate
qr = generate("HELLO WORLD", ec="M")
print(qr.to_ascii())
qr.to_svg()          # SVG string
qr.to_png_bytes()    # PNG bytes
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests cover the challenge steps (mode detection, the page's
`HELLO CC WORLD` bit example, padding, Reed–Solomon
syndromes, finder/timing/alignment/dark-module structure,
format/version bits, masking, renderers, CLI) plus an
independent decoder round-trip. During development the
matrices were also verified byte-for-byte against the
independent `qrcode` package on 584 cases (10 inputs × 4
EC levels × 8 masks, plus all forced versions 1–10) — that
package is verification-only and is never imported by the
shipped code.

## Files

- `qr_code.py` — the generator (GF(256), Reed–Solomon,
  matrix builder, masks, renderers, CLI).
- `docs/SPEC.md` — challenge spec and scope.
- `docs/DESIGN.md` — pipeline, tables, assumptions, divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_qr_code.py` — the test suite.
