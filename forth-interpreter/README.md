# forth-interpreter — Build Your Own Forth Interpreter

Coding Challenges challenge `challenge-forth`, worked in
`somecoolprojects/`. Docs first, then code — see `docs/`.

A Forth-like interpreter in Python 3 (standard library only),
single file `forth.py`: integer stack machine, word definitions,
`if/else/then`, `do/loop` with `i`, I/O words, a REPL, and
script-file execution — enough for the challenge's Fibonacci and
FizzBuzz programs.

## Usage

```sh
python3 forth.py                 # REPL (prompt: ok>, bye to quit)
python3 forth.py examples/fib.forth
python3 forth.py examples/fizzbuzz.forth
python3 forth.py -               # script from stdin, no prompts
```

REPL example:

```
ok> 1 2 2 + +
5 ok> : square dup * ;
ok> 5 square .
25 ok> bye
```

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests drive `Interpreter.run()` programmatically and cover every
challenge step: arithmetic, stack words, I/O, definitions,
conditionals, loops, the Fibonacci and FizzBuzz programs, the
REPL, and every error case. See `docs/TEST_PLAN.md`.
