"""Password cracker (educational) — Coding Challenges, challenge-password-cracker.

Steps: hand-rolled MD5, brute-force attack, dictionary attack,
rainbow-table build/lookup, bonus SHA-1/SHA-256/SHA-512 and salting.

EDUCATIONAL USE ONLY, on hashes you generate yourself (see README.md).
Python 3 standard library only.
"""

import argparse
import hashlib
import itertools
import math
import string
import sys

ALGORITHMS = ("md5", "sha1", "sha256", "sha512")
SALT_POSITIONS = ("prefix", "suffix", "none")

CHARSET_PRESETS = {
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
    "digits": string.digits,
    "alpha": string.ascii_letters,
    "alnum": string.ascii_letters + string.digits,
}


# ---------------------------------------------------------------- MD5 (Step 1)
# RFC 1321. Written from the algorithm; verified against hashlib.md5.

_MD5_SHIFTS = (
    [7, 12, 17, 22] * 4
    + [5, 9, 14, 20] * 4
    + [4, 11, 16, 23] * 4
    + [6, 10, 15, 21] * 4
)
# floor(abs(sin(i + 1)) * 2**32), i = 0..63, computed once at import.
_MD5_K = tuple(
    int(abs(math.sin(i + 1)) * (1 << 32)) & 0xFFFFFFFF
    for i in range(64)
)
_MASK = 0xFFFFFFFF


def _left_rotate(x, n):
    return ((x << n) | (x >> (32 - n))) & _MASK


def md5_hex(data: bytes) -> str:
    """MD5 hex digest of *data*, implemented by hand (no hashlib)."""
    # Padding: 0x80, zeroes until length == 56 (mod 64), then
    # 64-bit little-endian bit length.
    msg = bytearray(data)
    bit_len = (len(data) * 8) & 0xFFFFFFFFFFFFFFFF
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += bit_len.to_bytes(8, "little")

    a0, b0, c0, d0 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476

    for offset in range(0, len(msg), 64):
        block = msg[offset : offset + 64]
        words = [int.from_bytes(block[i : i + 4], "little") for i in range(0, 64, 4)]
        a, b, c, d = a0, b0, c0, d0
        for i in range(64):
            if i < 16:
                f = (b & c) | (~b & d)
                g = i
            elif i < 32:
                f = (d & b) | (~d & c)
                g = (5 * i + 1) % 16
            elif i < 48:
                f = b ^ c ^ d
                g = (3 * i + 5) % 16
            else:
                f = c ^ (b | ~d)
                g = (7 * i) % 16
            f = (f + a + _MD5_K[i] + words[g]) & _MASK
            a, d, c, b = d, c, b, (b + _left_rotate(f, _MD5_SHIFTS[i])) & _MASK
        a0 = (a0 + a) & _MASK
        b0 = (b0 + b) & _MASK
        c0 = (c0 + c) & _MASK
        d0 = (d0 + d) & _MASK

    digest = b"".join(x.to_bytes(4, "little") for x in (a0, b0, c0, d0))
    return digest.hex()


# ---------------------------------------------------------------- hashing


def hash_password(password, algo="md5", salt="", salt_position="prefix"):
    """Hex digest of *password* under *algo*, with optional salt.

    salt_position: "prefix" (salt + password), "suffix"
    (password + salt), or "none". An empty salt is ignored.
    """
    if algo not in ALGORITHMS:
        raise ValueError(f"unknown algorithm: {algo!r} (expected one of {ALGORITHMS})")
    if salt_position not in SALT_POSITIONS:
        raise ValueError(
            f"unknown salt position: {salt_position!r} (expected one of {SALT_POSITIONS})"
        )
    if salt and salt_position == "prefix":
        candidate = salt + password
    elif salt and salt_position == "suffix":
        candidate = password + salt
    else:
        candidate = password
    data = candidate.encode("utf-8")
    if algo == "md5":
        return md5_hex(data)
    return hashlib.new(algo, data).hexdigest()


def normalize_hash(target):
    return target.strip().lower()


# ---------------------------------------------------------------- attacks


def _matches(candidate, target, algo, salt, salt_position):
    return hash_password(candidate, algo, salt, salt_position) == target


def dictionary_attack(target, words, algo="md5", salt="", salt_position="prefix",
                      max_attempts=None):
    """Try each word in *words* (iterable). Return (password|None, attempts)."""
    target = normalize_hash(target)
    attempts = 0
    for word in words:
        if max_attempts is not None and attempts >= max_attempts:
            break
        attempts += 1
        if _matches(word, target, algo, salt, salt_position):
            return word, attempts
    return None, attempts


def brute_force_attack(target, charset, min_length, max_length, algo="md5",
                       salt="", salt_position="prefix", max_attempts=None):
    """Try every charset permutation of length min..max, in that order.

    Return (password|None, attempts). Candidates are generated
    lazily, never materialised.
    """
    if not charset:
        raise ValueError("charset must not be empty")
    if min_length < 1:
        raise ValueError("min_length must be >= 1")
    if max_length < min_length:
        raise ValueError("max_length must be >= min_length")
    target = normalize_hash(target)
    attempts = 0
    for length in range(min_length, max_length + 1):
        for combo in itertools.product(charset, repeat=length):
            if max_attempts is not None and attempts >= max_attempts:
                return None, attempts
            attempts += 1
            candidate = "".join(combo)
            if _matches(candidate, target, algo, salt, salt_position):
                return candidate, attempts
    return None, attempts


def read_wordlist(path):
    """Yield candidates from a wordlist file: one per line, blank lines skipped."""
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            word = line.rstrip("\r\n")
            if word == "":
                continue
            yield word


# ---------------------------------------------------------------- rainbow table


def build_rainbow_table(passwords, algo="md5", salt="", salt_position="prefix"):
    """Return {hash: password} for *passwords*; first password wins on collision."""
    table = {}
    for password in passwords:
        digest = hash_password(password, algo, salt, salt_position)
        table.setdefault(digest, password)
    return table


def write_rainbow_table(path, table):
    with open(path, "w", encoding="utf-8") as fh:
        for digest, password in table.items():
            fh.write(f"{digest}\t{password}\n")


def load_rainbow_table(path):
    """Load a hash<TAB>password file; malformed lines are skipped."""
    table = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if "\t" not in line:
                continue
            digest, password = line.split("\t", 1)
            if digest == "":
                continue
            table.setdefault(digest, password)
    return table


def crack(target, mode, algo="md5", salt="", salt_position="prefix",
          wordlist=None, charset=None, min_length=1, max_length=4,
          table=None, max_attempts=None):
    """Dispatch an attack. *wordlist* is an iterable (dict mode);
    *table* is a {hash: password} dict (rainbow mode)."""
    target = normalize_hash(target)
    if mode == "dict":
        if wordlist is None:
            raise ValueError("dict mode requires a wordlist")
        found, attempts = dictionary_attack(
            target, wordlist, algo, salt, salt_position, max_attempts)
        return found, attempts
    if mode == "brute":
        if charset is None:
            raise ValueError("brute mode requires a charset")
        return brute_force_attack(
            target, charset, min_length, max_length,
            algo, salt, salt_position, max_attempts)
    if mode == "rainbow":
        if table is None:
            raise ValueError("rainbow mode requires a table")
        found = table.get(target)
        return found, (1 if found is not None else 0)
    raise ValueError(f"unknown mode: {mode!r} (expected dict, brute, or rainbow)")


# ---------------------------------------------------------------- CLI


def _resolve_charset(args):
    if args.charset is not None:
        return args.charset
    return CHARSET_PRESETS[args.charset_preset]


def _common_args(parser):
    parser.add_argument("--algo", default="md5", choices=ALGORITHMS)
    parser.add_argument("--salt", default="")
    parser.add_argument("--salt-position", default="prefix", choices=SALT_POSITIONS)
    parser.add_argument("--max-attempts", type=int, default=None)


def _candidates_from(args):
    """Yield candidates for build-table: wordlist file, brute-force set, or both."""
    seen = set()
    if args.wordlist:
        for word in read_wordlist(args.wordlist):
            if word not in seen:
                seen.add(word)
                yield word
    if args.brute:
        charset = _resolve_charset(args)
        for length in range(args.min_length, args.max_length + 1):
            for combo in itertools.product(charset, repeat=length):
                candidate = "".join(combo)
                if candidate not in seen:
                    seen.add(candidate)
                    yield candidate


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="cracker",
        description="Educational password cracker: use only on hashes "
                    "you generated yourself (see README.md).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_hash = sub.add_parser("hash", help="crack one hash by dict or brute force")
    p_hash.add_argument("target")
    p_hash.add_argument("--mode", default="brute", choices=("dict", "brute"))
    p_hash.add_argument("--wordlist")
    p_hash.add_argument("--charset")
    p_hash.add_argument("--charset-preset", default="lower", choices=CHARSET_PRESETS)
    p_hash.add_argument("--min-length", type=int, default=1)
    p_hash.add_argument("--max-length", type=int, default=4)
    _common_args(p_hash)

    p_build = sub.add_parser("build-table", help="build a rainbow table file")
    p_build.add_argument("--wordlist")
    p_build.add_argument("--brute", action="store_true",
                         help="also generate brute-force candidates")
    p_build.add_argument("--charset")
    p_build.add_argument("--charset-preset", default="lower", choices=CHARSET_PRESETS)
    p_build.add_argument("--min-length", type=int, default=1)
    p_build.add_argument("--max-length", type=int, default=3)
    p_build.add_argument("--output", required=True)
    _common_args(p_build)

    p_lookup = sub.add_parser("lookup", help="look a hash up in a rainbow table")
    p_lookup.add_argument("target")
    p_lookup.add_argument("--table", required=True)

    args = parser.parse_args(argv)

    try:
        if args.command == "hash":
            if args.mode == "dict":
                if not args.wordlist:
                    parser.error("dict mode requires --wordlist")
                words = read_wordlist(args.wordlist)
                found, attempts = crack(
                    args.target, "dict", args.algo, args.salt,
                    args.salt_position, wordlist=words,
                    max_attempts=args.max_attempts)
            else:
                found, attempts = crack(
                    args.target, "brute", args.algo, args.salt,
                    args.salt_position, charset=_resolve_charset(args),
                    min_length=args.min_length, max_length=args.max_length,
                    max_attempts=args.max_attempts)
            if found is not None:
                print(f"Password found: {found} (after {attempts} attempts)")
                return 0
            print(f"Password not found (after {attempts} attempts)")
            return 1

        if args.command == "build-table":
            table = build_rainbow_table(
                _candidates_from(args), args.algo, args.salt, args.salt_position)
            write_rainbow_table(args.output, table)
            print(f"Wrote {len(table)} entries to {args.output}")
            return 0

        # lookup
        table = load_rainbow_table(args.table)
        found, _ = crack(args.target, "rainbow", table=table)
        if found is not None:
            print(f"Password found: {found}")
            return 0
        print("Password not found")
        return 1
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
