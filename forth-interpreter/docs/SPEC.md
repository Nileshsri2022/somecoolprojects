# SPEC — Forth interpreter

Source: https://codingchallenges.fyi/challenges/challenge-forth/
Slug used: `challenge-forth` (found by web search; the guessed slug
`challenge-forth-interpreter` was not tried — search returned
`challenge-forth` directly, and that page fetched successfully, so no
404 correction was needed).

## What is built

A CLI Forth-like interpreter in Python 3 (standard library only),
single file `forth.py`, sufficient for the page's Step 7 programs:
the Fibonacci sequence and FizzBuzz.

## Challenge steps implemented

- Step 1 — REPL with prompt `ok>`, stack shown bottom-to-top before
  the prompt, `bye` terminates the REPL.
- Step 2 — Integer literals pushed onto the data stack; `+ - * / mod`.
  `/` and `mod` truncate toward zero (standard Forth), not Python's
  floor division.
- Step 3 — Stack words: `dup drop swap over rot`.
- Step 4 — I/O words: `.` (print and pop, followed by a space),
  `emit` (print top as an ASCII character and pop), `cr` (newline),
  `." ..."` (print a string literal).
- Step 5 — Word definitions `: name ... ;`, unknown-word handling
  (prints `<word> ?` and continues), `( ... )` comments.
- Step 6 — Comparisons `< > = <>`, logic `and or invert`
  (true = -1, false = 0), conditionals `if ... else ... then`,
  loops `do ... loop` with the loop index word `i`.
- Step 7 — Running a script file given as a command-line argument;
  the page's Fibonacci and FizzBuzz programs run (see `examples/`).

## Word reference

Stack comments use the page's convention: items are listed
bottom-to-top, so in `( n1 n2 -- r )` `n2` is on top.

| Word | Stack | Meaning |
| --- | --- | --- |
| `+` | `( n1 n2 -- sum )` | `n1 + n2` |
| `-` | `( n1 n2 -- diff )` | `n1 - n2` |
| `*` | `( n1 n2 -- prod )` | `n1 * n2` |
| `/` | `( n1 n2 -- quot )` | `n1 / n2`, truncated toward zero |
| `mod` | `( n1 n2 -- rem )` | `n1 mod n2`, remainder of truncated division |
| `dup` | `( n -- n n )` | duplicate top |
| `drop` | `( n -- )` | pop top |
| `swap` | `( n1 n2 -- n2 n1 )` | swap top two |
| `over` | `( n1 n2 -- n1 n2 n1 )` | copy second item to top |
| `rot` | `( n1 n2 n3 -- n2 n3 n1 )` | rotate top three |
| `.` | `( n -- )` | print top as decimal plus a trailing space, pop |
| `emit` | `( n -- )` | print top as a character, pop |
| `cr` | `( -- )` | print a newline |
| `."` | `( -- )` | print the string up to the next `"` |
| `<` `>` `=` `<>` | `( n1 n2 -- flag )` | compare `n1` with `n2`, -1 if true else 0 |
| `and` `or` | `( n1 n2 -- flag )` | bitwise and / or (-1/0 flags behave as booleans) |
| `invert` | `( n -- flag )` | bitwise not (`invert 0` = -1, `invert -1` = 0) |
| `if else then` | `( flag -- )` | conditional; `else` optional |
| `do loop` | `( limit start -- )` | loop `start .. limit-1`; `i` pushes the index |
| `i` | `( -- n )` | current innermost loop index |
| `:` `;` | | define a word |
| `bye` | | terminate the REPL / stop a script |

## CLI

```sh
python3 forth.py            # REPL on stdin/stdout
python3 forth.py prog.forth # run a script file
python3 forth.py -          # run a script from stdin (no prompts)
```

Errors (stack underflow, division by zero, unterminated definition /
comment / string / control structure, redefining a builtin word)
raise `ForthError`. In the REPL the error is printed as
`error: <message>` and the REPL continues; in file mode it goes to
stderr and the exit code is 1. An unknown word is not an error: it
prints `<word> ?` and execution continues, per Step 5.

## Divergences from the page (deliberate, documented)

1. The page's `/` and `mod` table rows say "n2 / n1" / "remainder of
   n2 / n1", which contradicts its own FizzBuzz program
   (`3 mod` on an input `n` must mean `n mod 3`, and `5 mod`
   likewise). This implementation follows standard Forth and the
   programs: `n1 n2 /` = `n1 / n2`, `n1 n2 mod` = `n1 mod n2`.
   The same bottom-to-top reading is used for `<`, `>`, `=`, `<>`.
2. `do ... loop` is standard Forth: `limit start do` iterates
   `start .. limit-1` (limit exclusive). So the page's
   `25 1 do ... loop` prints FizzBuzz for 1..24, and its `fibn`
   (`10 1 do`) adds 9 numbers after the initial `0 1`. The page's
   loose wording ("next 10 numbers") is not followed literally.
3. Not implemented (not on the page): `+loop`, `j`, `?do`,
   `begin/until`, variables, floating point, `s"` strings,
   `\` line comments, and defining a word inside another word's
   body. Words are case-insensitive (standard Forth practice);
   string literals keep their case.
4. `do` with `start >= limit` (ascending loop) runs zero times
   rather than wrapping; a loop body that never reaches its limit
   cannot occur with the fixed +1 step, so no iteration cap is
   needed beyond that rule.
