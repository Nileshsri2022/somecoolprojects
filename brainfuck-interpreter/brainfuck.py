"""Brainfuck interpreter: compiler to bytecode + small VM.

Coding Challenges, "Build Your Own Brainfuck Interpreter"
(https://www.codingchallenges.fyi/challenges/challenge-brainfuck).

Standard library only. See docs/SPEC.md, docs/DESIGN.md.

Bytecode is a list of (op, arg) tuples:
    RIGHT n, LEFT n, ADD n, SUB n  -- runs collapsed (challenge Step 5)
    OUTPUT, INPUT
    JUMP_IF_ZERO target, JUMP_IF_NONZERO target  -- target = bytecode index
    CLEAR  -- the [-] / [+] clear-loop pattern (challenge Step 6)
"""

import argparse
import sys

DEFAULT_TAPE_SIZE = 30000
COMMANDS = set("><+-.,[]")

# Ops that collapse into a run with a count argument.
_RUN_OPS = {">": "RIGHT", "<": "LEFT", "+": "ADD", "-": "SUB"}
# Full source-character -> bytecode-op mapping.
_OP_NAMES = {**_RUN_OPS, ".": "OUTPUT", ",": "INPUT", "[": "[", "]": "]"}


class BrainfuckError(Exception):
    """Any interpreter error: bad brackets, pointer out of bounds."""


def compile_program(source):
    """Compile Brainfuck source to bytecode.

    Non-command characters are dropped here, so the VM never sees
    comments. Raises BrainfuckError on unmatched brackets, before
    any execution happens.
    """
    # Step 1: filter to commands, collapsing runs of > < + -.
    ops = []
    for ch in source:
        if ch not in COMMANDS:
            continue
        if ch in _RUN_OPS and ops and ops[-1][0] == _RUN_OPS[ch]:
            ops[-1][1] += 1
        else:
            ops.append([_OP_NAMES[ch], 1 if ch in _RUN_OPS else 0])
    # Step 2: recognise clear loops ([-] / [+]) and resolve jumps.
    program = []
    stack = []
    for op, arg in ops:
        if op == "[":
            stack.append(len(program))
            program.append(["JUMP_IF_ZERO", 0])
        elif op == "]":
            if not stack:
                raise BrainfuckError("unmatched ']'")
            start = stack.pop()
            # [-] or [+] : a jump pair around a single SUB/ADD 1.
            if (len(program) == start + 2
                    and program[start + 1][0] in ("SUB", "ADD")
                    and program[start + 1][1] == 1):
                program[start] = ["CLEAR", 0]
                program.pop()  # drop the SUB/ADD; CLEAR replaces the loop
            else:
                program.append(["JUMP_IF_NONZERO", start])
                program[start][1] = len(program) - 1
        else:
            program.append([op, arg])
    if stack:
        raise BrainfuckError("unmatched '['")
    return [(op, arg) for op, arg in program]


def execute(program, input_bytes=b"", tape_size=DEFAULT_TAPE_SIZE):
    """Run compiled bytecode; return output as bytes."""
    tape = bytearray(tape_size)
    ptr = 0
    pc = 0
    input_pos = 0
    out = bytearray()
    while pc < len(program):
        op, arg = program[pc]
        if op == "RIGHT":
            ptr += arg
            if ptr >= tape_size:
                raise BrainfuckError("data pointer moved past end of tape")
        elif op == "LEFT":
            ptr -= arg
            if ptr < 0:
                raise BrainfuckError("data pointer moved before start of tape")
        elif op == "ADD":
            tape[ptr] = (tape[ptr] + arg) % 256
        elif op == "SUB":
            tape[ptr] = (tape[ptr] - arg) % 256
        elif op == "OUTPUT":
            out.append(tape[ptr])
        elif op == "INPUT":
            if input_pos < len(input_bytes):
                tape[ptr] = input_bytes[input_pos]
                input_pos += 1
            else:
                tape[ptr] = 0  # EOF: store 0 (see docs/DESIGN.md)
        elif op == "JUMP_IF_ZERO":
            if tape[ptr] == 0:
                pc = arg
                continue
        elif op == "JUMP_IF_NONZERO":
            if tape[ptr] != 0:
                pc = arg
                continue
        elif op == "CLEAR":
            tape[ptr] = 0
        pc += 1
    return bytes(out)


def run(source, input_bytes=b"", tape_size=DEFAULT_TAPE_SIZE):
    """Compile and execute Brainfuck source; return output bytes."""
    return execute(compile_program(source), input_bytes, tape_size)


def _repl():
    """Step 1 REPL: read a line, interpret it, print its output."""
    while True:
        try:
            line = input("CCBF> ")
        except EOFError:
            print()
            return 0
        try:
            sys.stdout.buffer.write(run(line))
            sys.stdout.buffer.flush()
        except BrainfuckError as exc:
            print(f"error: {exc}", file=sys.stderr)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Brainfuck interpreter (compile to bytecode + VM).")
    parser.add_argument("file", nargs="?",
                        help="Brainfuck program file, or '-' for stdin; "
                             "omit for the REPL")
    parser.add_argument("--tape-size", type=int, default=DEFAULT_TAPE_SIZE,
                        help="number of memory cells (default: 30000)")
    args = parser.parse_args(argv)
    if args.tape_size < 1:
        parser.error("--tape-size must be at least 1")
    if args.file is None:
        return _repl()
    try:
        if args.file == "-":
            source = sys.stdin.read()
        else:
            with open(args.file, encoding="utf-8") as fh:
                source = fh.read()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        # Only consume stdin for ',' input when the program actually
        # uses it; otherwise a terminal session would block at EOF.
        # (A '-' program has already consumed stdin as its source.)
        input_bytes = (sys.stdin.buffer.read()
                       if args.file != "-" and "," in source else b"")
        sys.stdout.buffer.write(run(source, input_bytes, args.tape_size))
        sys.stdout.buffer.flush()
    except BrainfuckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
