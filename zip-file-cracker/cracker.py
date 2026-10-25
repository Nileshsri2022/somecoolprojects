#!/usr/bin/env python3
"""cczipcrack — educational zip file cracker (Coding Challenge #66).

Steps from https://codingchallenges.fyi/challenges/challenge-zip-cracker/
  Step 1: verify zip headers.
  Step 2: dictionary attack (user-supplied wordlist).
  Step 3: brute-force attack (min/max length, charset).
  Step 4: concurrent checking, one worker per CPU core (CLI default).

Only traditional ZipCrypto archives can be cracked: Python's stdlib
``zipfile`` decrypts ZipCrypto but not AES. AES archives are rejected
up front with a clear error instead of failing per candidate.

Educational scope: use ONLY on zip files you created yourself or
are authorised to test. No wordlist is bundled or downloaded.
Standard library only.
"""

import argparse
import itertools
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
AES_METHOD = 99  # compression method for AES-encrypted entries

CHARSET_PRESETS = {
    "lower": "abcdefghijklmnopqrstuvwxyz",
    "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "digits": "0123456789",
    "alpha": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "alnum": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
}


class UnsupportedEncryptionError(ValueError):
    """Raised when the target member uses encryption stdlib cannot handle."""


def has_zip_headers(path):
    """Step 1: True if the file starts with a zip signature."""
    try:
        with open(path, "rb") as f:
            return f.read(4) in ZIP_SIGNATURES
    except OSError:
        return False


def looks_like_zip(data):
    """True if raw bytes start with a zip signature (nested-zip check)."""
    return data[:4] in ZIP_SIGNATURES


def _target_member(path, member):
    """Return the ZipInfo to attack, validating encryption support."""
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if not infos:
            raise ValueError("zip archive is empty: nothing to decrypt")
        if member is None:
            info = infos[0]
        else:
            matches = [i for i in infos if i.filename == member]
            if not matches:
                raise ValueError("no member named %r in archive" % member)
            info = matches[0]
        if info.compress_type == AES_METHOD:
            raise UnsupportedEncryptionError(
                "AES-encrypted zip files are not supported by "
                "Python's stdlib zipfile (only traditional ZipCrypto)"
            )
        if not (info.flag_bits & 0x1):
            return info, False
        return info, True


def try_password(path, password, member=None):
    """Try one password. True only if an encrypted member decrypts.

    Unencrypted members always return False (they need no password,
    so any candidate "succeeding" would be a false positive).
    """
    try:
        info, encrypted = _target_member(path, member)
    except (UnsupportedEncryptionError, ValueError):
        # Empty archive / unknown member / AES: caller errors, not
        # failed attempts. (Attack functions validate up front, so
        # a search never reaches this per candidate.)
        raise
    except (zipfile.BadZipFile, OSError):
        return False
    if not encrypted:
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            zf.read(info.filename, pwd=password.encode("utf-8"))
        return True
    except (RuntimeError, zipfile.BadZipFile, NotImplementedError):
        # RuntimeError "Bad password", BadZipFile (CRC mismatch),
        # or an unsupported method for this entry.
        return False


def read_decrypted(path, password, member=None):
    """Return the decrypted bytes of the target member (or None)."""
    info, encrypted = _target_member(path, member)
    if not encrypted:
        return None
    with zipfile.ZipFile(path) as zf:
        return zf.read(info.filename, pwd=password.encode("utf-8"))


def _search(candidates, path, member, max_attempts, workers):
    """Shared search core. Returns (password_or_None, attempts)."""
    if workers is None or workers <= 1:
        attempts = 0
        for candidate in candidates:
            if max_attempts is not None and attempts >= max_attempts:
                break
            attempts += 1
            if try_password(path, candidate, member):
                return candidate, attempts
        return None, attempts

    # Parallel (Step 4): dispatch in batches; stop after the batch
    # containing the hit. Attempts count dispatched candidates in
    # completed batches, so parallel counts are >= the hit position.
    attempts = 0
    batch_size = max(1, workers * 4)
    batch = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for candidate in candidates:
            if max_attempts is not None and attempts + len(batch) >= max_attempts:
                break
            batch.append(candidate)
            if len(batch) < batch_size:
                continue
            results = list(pool.map(lambda c: try_password(path, c, member), batch))
            attempts += len(batch)
            if True in results:
                return batch[results.index(True)], attempts
            batch = []
        if batch:
            if max_attempts is not None:
                batch = batch[: max(0, max_attempts - attempts)]
            results = list(pool.map(lambda c: try_password(path, c, member), batch))
            attempts += len(batch)
            if True in results:
                return batch[results.index(True)], attempts
    return None, attempts


def dictionary_attack(path, wordlist_path, member=None, max_attempts=None,
                      workers=1):
    """Step 2: try each line of wordlist_path in order."""
    # Validate the target up front so a bad archive / AES file fails
    # fast instead of once per word.
    _target_member(path, member)
    try:
        wordlist = open(wordlist_path, "r", encoding="utf-8", errors="replace")
    except OSError:
        raise

    def candidates():
        with wordlist:
            for line in wordlist:
                word = line.rstrip("\r\n")
                if word == "":
                    continue
                yield word

    return _search(candidates(), path, member, max_attempts, workers)


def brute_force_attack(path, charset="abcdefghijklmnopqrstuvwxyz",
                       min_length=1, max_length=4, member=None,
                       max_attempts=None, workers=1):
    """Step 3: try all combinations of charset, shortest first."""
    # De-duplicate preserving order.
    seen = set()
    chars = []
    for ch in charset:
        if ch not in seen:
            seen.add(ch)
            chars.append(ch)
    if not chars:
        raise ValueError("charset must not be empty")
    if min_length < 1:
        raise ValueError("min length must be at least 1")
    if max_length < min_length:
        raise ValueError("max length must be >= min length")
    _target_member(path, member)

    def candidates():
        for length in range(min_length, max_length + 1):
            for combo in itertools.product(chars, repeat=length):
                yield "".join(combo)

    return _search(candidates(), path, member, max_attempts, workers)


def _default_workers():
    return os.cpu_count() or 1


def build_parser():
    p = argparse.ArgumentParser(
        prog="cczipcrack",
        description="Educational zip file cracker. "
                    "Use only on archives you created or are authorised to test.")
    p.add_argument("zipfile", help="zip archive to check / crack")
    p.add_argument("-dict", "--dict", dest="dict", action="store_true",
                   help="dictionary attack (requires --wordlist)")
    p.add_argument("-brute", "--brute", dest="brute", action="store_true",
                   help="brute-force attack")
    p.add_argument("--wordlist", default=None,
                   help="wordlist file for -dict (one password per line)")
    p.add_argument("-min", "--min-length", dest="min_length", type=int, default=1,
                   help="brute-force minimum length (default 1)")
    p.add_argument("-max", "--max-length", dest="max_length", type=int, default=4,
                   help="brute-force maximum length (default 4)")
    p.add_argument("--charset", default=None,
                   help="brute-force charset (overrides --charset-preset)")
    p.add_argument("--charset-preset", default="lower",
                   choices=sorted(CHARSET_PRESETS),
                   help="brute-force charset preset (default lower)")
    p.add_argument("--member", default=None,
                   help="archive member to decrypt (default: first member)")
    p.add_argument("--workers", type=int, default=None,
                   help="parallel workers (default: one per CPU core)")
    p.add_argument("--max-attempts", type=int, default=None,
                   help="stop after this many attempts")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    path = args.zipfile

    if not args.dict and not args.brute:
        # Step 1 only, exactly the page's output.
        if has_zip_headers(path):
            print("Has zip headers.")
            return 0
        print("Does not have zip headers.")
        return 1

    if args.dict and args.wordlist is None:
        print("error: -dict requires --wordlist (no wordlist is bundled)",
              file=sys.stderr)
        return 2
    if args.workers is not None and args.workers < 1:
        print("error: --workers must be at least 1", file=sys.stderr)
        return 2
    workers = args.workers if args.workers is not None else _default_workers()

    try:
        found = None
        if args.dict:
            # Dictionary first, as the page recommends (Step 2 before 3).
            found, _attempts = dictionary_attack(
                path, args.wordlist, member=args.member,
                max_attempts=args.max_attempts, workers=workers)
        if found is None and args.brute:
            charset = args.charset
            if charset is None:
                charset = CHARSET_PRESETS[args.charset_preset]
            found, _attempts = brute_force_attack(
                path, charset=charset,
                min_length=args.min_length, max_length=args.max_length,
                member=args.member, max_attempts=args.max_attempts,
                workers=workers)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except (ValueError, UnsupportedEncryptionError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except zipfile.BadZipFile:
        print("error: %s is not a valid zip archive" % path, file=sys.stderr)
        return 2

    if found is None:
        print("Password not found.")
        return 1
    print("Password found: %s" % found)
    # Going Further (partial): note a nested zip, do not recurse.
    try:
        data = read_decrypted(path, found, member=args.member)
        if data is not None and looks_like_zip(data):
            print("Note: decrypted content also has zip headers "
                  "(nested zip — not cracked recursively).")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
