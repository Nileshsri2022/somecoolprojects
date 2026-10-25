"""Calculator: one arithmetic expression in, one result out.

Pipeline: tokenize -> shunting yard (infix to postfix) ->
stack evaluation. No use of eval anywhere: parsing is hand-written.

Usage: python3 calc.py '2 * 3'   ->  6
"""

import math
import sys

FUNCTIONS = {"sin": math.sin, "cos": math.cos, "tan": math.tan}
PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}


class CalcError(ValueError):
    """Any user-input error: invalid input, bad parens, div by zero."""


def tokenize(expr):
    """Split an expression into tokens: floats, or str operators,
    parens, and function names. Raises CalcError on bad input."""
    tokens = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit() or ch == ".":
            j = i
            while j < n and expr[j].isdigit():
                j += 1
            if j < n and expr[j] == ".":
                j += 1
                while j < n and expr[j].isdigit():
                    j += 1
            try:
                tokens.append(float(expr[i:j]))
            except ValueError:
                raise CalcError(f"invalid number: {expr[i:j]!r}")
            i = j
        elif ch.isalpha():
            j = i
            while j < n and expr[j].isalpha():
                j += 1
            name = expr[i:j].lower()
            if name not in FUNCTIONS:
                raise CalcError(f"unknown function: {name}")
            tokens.append(name)
            i = j
        elif ch in "+-":
            unary = (not tokens or (isinstance(tokens[-1], str)
                     and (tokens[-1] in PRECEDENCE
                          or tokens[-1] == "("
                          or tokens[-1] in FUNCTIONS
                          or tokens[-1] == "neg")))
            if unary:
                # Fold a sign into a following number. Before '('
                # or a function, '-' becomes a "neg" token (handled
                # like a function by the shunting yard, so that
                # 2 * -(1 + 1) is -4, not 2 * 0 - (1 + 1) = -2);
                # unary '+' there is the identity, so emit nothing.
                j = i + 1
                while j < n and expr[j].isspace():
                    j += 1
                if j < n and (expr[j].isdigit() or expr[j] == "."):
                    k = j
                    while k < n and expr[k].isdigit():
                        k += 1
                    if k < n and expr[k] == ".":
                        k += 1
                        while k < n and expr[k].isdigit():
                            k += 1
                    tokens.append(float(expr[i] + expr[j:k]))
                    i = k
                else:
                    if ch == "-":
                        tokens.append("neg")
                    i += 1
            else:
                tokens.append(ch)
                i += 1
        elif ch in "*/()":
            tokens.append(ch)
            i += 1
        else:
            raise CalcError(f"invalid character: {ch!r}")
    if not tokens:
        raise CalcError("empty expression")
    return tokens


def infix_to_postfix(tokens):
    """Shunting yard: infix tokens -> postfix tokens."""
    output, stack = [], []
    for tok in tokens:
        if isinstance(tok, float):
            output.append(tok)
        elif tok in FUNCTIONS or tok == "neg":
            stack.append(tok)
        elif tok == "(":
            stack.append(tok)
        elif tok == ")":
            while stack and stack[-1] != "(":
                output.append(stack.pop())
            if not stack:
                raise CalcError("mismatched parentheses")
            stack.pop()  # discard '('
            while stack and (stack[-1] in FUNCTIONS
                             or stack[-1] == "neg"):
                output.append(stack.pop())
        else:  # binary operator, all left-associative
            while (stack and stack[-1] in PRECEDENCE
                   and PRECEDENCE[stack[-1]] >= PRECEDENCE[tok]):
                output.append(stack.pop())
            stack.append(tok)
    while stack:
        tok = stack.pop()
        if tok == "(":
            raise CalcError("mismatched parentheses")
        output.append(tok)
    return output


def evaluate_postfix(postfix):
    """Stack evaluation of postfix tokens -> float."""
    stack = []
    for tok in postfix:
        if isinstance(tok, float):
            stack.append(tok)
        elif tok == "neg":
            if not stack:
                raise CalcError("missing operand")
            stack.append(-stack.pop())
        elif tok in FUNCTIONS:
            if not stack:
                raise CalcError("missing operand")
            stack.append(FUNCTIONS[tok](stack.pop()))
        else:  # binary operator
            if len(stack) < 2:
                raise CalcError("missing operand")
            b, a = stack.pop(), stack.pop()
            if tok == "+":
                stack.append(a + b)
            elif tok == "-":
                stack.append(a - b)
            elif tok == "*":
                stack.append(a * b)
            elif tok == "/":
                if b == 0:
                    raise CalcError("division by zero")
                stack.append(a / b)
    if len(stack) != 1:
        raise CalcError("invalid expression")
    return stack[0]


def format_result(value):
    """Integral results print as integers, else as float repr."""
    if value == int(value):
        return str(int(value))
    return repr(value)


def evaluate(expr):
    """Evaluate one expression string -> formatted result string."""
    return format_result(evaluate_postfix(infix_to_postfix(tokenize(expr))))


def main(argv):
    if len(argv) != 2:
        print("usage: calc.py 'expression'", file=sys.stderr)
        return 1
    try:
        print(evaluate(argv[1]))
    except CalcError as exc:
        print(f"calc: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
