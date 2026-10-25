"""CC Password Manager: a stdlib-only CLI password vault.

Challenge: https://codingchallenges.fyi/challenges/challenge-password-manager/
See docs/SPEC.md and docs/DESIGN.md.

SECURITY WARNING: this is NOT production-grade. Python's standard
library has no AES, so the page's recommended AES-256 cannot be built
here. Encryption is PBKDF2-HMAC-SHA256 key derivation + an HMAC-based
stream cipher with an HMAC authentication tag. Wrong passwords and
tampered files are rejected before decryption, but this construction
has not been audited and must not hold real passwords.
"""

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import struct
import sys

FORMAT_VERSION = 1
ITERATIONS = 200_000
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 16
VAULT_SUFFIX = ".ccv"


class VaultError(ValueError):
    """Base class for vault failures (wrong password, corrupt file)."""


class WrongPasswordError(VaultError):
    """The master password does not match this vault."""


class CorruptVaultError(VaultError):
    """The vault file is malformed or its authentication tag failed."""


def validate_vault_name(name):
    """A vault name must be usable as a filename (page, step 1)."""
    if not name or name in (".", ".."):
        raise ValueError("vault name must not be empty, '.' or '..'")
    if "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("vault name must not contain '/', '\\' or NUL")
    return name


def vault_path(vault_dir, name):
    return os.path.join(vault_dir, validate_vault_name(name) + VAULT_SUFFIX)


def _derive_key(password, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=KEY_LEN
    )


def _keystream(key, nonce, length):
    """HMAC-SHA256 keystream blocks; see DESIGN.md for the caveats."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(
            key, b"stream" + nonce + struct.pack(">I", counter), hashlib.sha256
        ).digest()
        counter += 1
    return bytes(out[:length])


def _encrypt(key, plaintext):
    nonce = secrets.token_bytes(NONCE_LEN)
    stream = _keystream(key, nonce, len(plaintext))
    ciphertext = bytes(p ^ s for p, s in zip(plaintext, stream))
    tag = hmac.new(key, b"tag" + nonce + ciphertext, hashlib.sha256).digest()
    return nonce, ciphertext, tag


def _decrypt(key, nonce, ciphertext, tag):
    expected = hmac.new(key, b"tag" + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise CorruptVaultError("vault authentication failed (tampered file?)")
    stream = _keystream(key, nonce, len(ciphertext))
    return bytes(c ^ s for c, s in zip(ciphertext, stream))


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _unb64(text, what):
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except Exception as exc:
        raise CorruptVaultError("invalid %s in vault file" % what) from exc


class Vault:
    """An opened vault: records in memory, re-encrypted on each save."""

    def __init__(self, path, key, salt, records):
        self.path = path
        self._key = key
        self._salt = salt
        self.records = records  # {name: {"username": ..., "password": ...}}

    @classmethod
    def create(cls, path, password):
        if not password:
            raise ValueError("master password must not be empty")
        if os.path.exists(path):
            raise FileExistsError("vault already exists: %s" % path)
        salt = secrets.token_bytes(SALT_LEN)
        key = _derive_key(password, salt)
        vault = cls(path, key, salt, {})
        vault._save()
        return vault

    @classmethod
    def open(cls, path, password):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise
        except (OSError, ValueError) as exc:
            raise CorruptVaultError("cannot read vault file: %s" % exc) from exc
        if data.get("format") != FORMAT_VERSION:
            raise CorruptVaultError("unsupported vault format")
        try:
            salt = _unb64(data["salt"], "salt")
            nonce = _unb64(data["nonce"], "nonce")
            verifier = _unb64(data["verifier"], "verifier")
            tag = _unb64(data["tag"], "tag")
            ciphertext = _unb64(data["ciphertext"], "ciphertext")
            iterations = int(data["iterations"])
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, CorruptVaultError):
                raise
            raise CorruptVaultError("missing field in vault file") from exc
        key = _derive_key(password, salt, iterations)
        expected = hmac.new(key, b"verifier", hashlib.sha256).digest()
        if not hmac.compare_digest(expected, verifier):
            raise WrongPasswordError("wrong master password")
        try:
            plaintext = _decrypt(key, nonce, ciphertext, tag)
            payload = json.loads(plaintext.decode("utf-8"))
            records = payload["records"]
        except CorruptVaultError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise CorruptVaultError("vault payload is corrupt") from exc
        return cls(path, key, salt, records)

    def _save(self):
        payload = json.dumps(
            {"records": self.records}, sort_keys=True
        ).encode("utf-8")
        nonce, ciphertext, tag = _encrypt(self._key, payload)
        verifier = hmac.new(self._key, b"verifier", hashlib.sha256).digest()
        data = {
            "format": FORMAT_VERSION,
            "salt": _b64(self._salt),
            "iterations": ITERATIONS,
            "nonce": _b64(nonce),
            "verifier": _b64(verifier),
            "tag": _b64(tag),
            "ciphertext": _b64(ciphertext),
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)

    def add(self, name, username, password):
        if not name:
            raise ValueError("record name must not be empty")
        self.records[name] = {"username": username, "password": password}
        self._save()

    def get(self, name):
        record = self.records.get(name)
        if record is None:
            return None
        return record["username"], record["password"]

    def list_names(self):
        return sorted(self.records)

    def delete(self, name):
        if name not in self.records:
            return False
        del self.records[name]
        self._save()
        return True


# --- interactive menu ------------------------------------------------

MENU = """What would you like to do?
1. Create a new password vault
2. Sign in to a password vault
3. Add a password to a vault
4. Fetch a password from a vault
5. List password records
6. Delete a password record
Quit (enter q or quit)"""


def _prompt_password(prompt):
    """Masked entry on a terminal; plain input when stdin is piped."""
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return input(prompt)


def _require_signed_in(vault):
    if vault is None:
        print("You are not signed in to a vault.")
        return False
    return True


def run_menu(vault_dir):
    print("Welcome to CC Password Manager")
    vault = None
    while True:
        print(MENU)
        try:
            choice = input().strip()
        except EOFError:
            break
        if choice in ("q", "quit"):
            break
        elif choice == "1":
            print("Creating a new vault")
            name = input("Please provide a name for the vault: ").strip()
            password = _prompt_password("Please enter a master password: ")
            confirm = _prompt_password("Please confirm the master password: ")
            if password != confirm:
                print("Error: master passwords do not match.")
                continue
            try:
                Vault.create(vault_path(vault_dir, name), password)
            except (ValueError, FileExistsError, OSError) as exc:
                print("Error: %s" % exc)
                continue
            print("New vault created and saved as: %s%s" % (name, VAULT_SUFFIX))
        elif choice == "2":
            name = input("Enter vault name: ").strip()
            password = _prompt_password(
                "Enter password for the %s vault: " % name
            )
            try:
                vault = Vault.open(vault_path(vault_dir, name), password)
            except FileNotFoundError:
                print("Error: no such vault: %s" % name)
                continue
            except VaultError as exc:
                print("Error: %s" % exc)
                continue
            print("Thank you, you are now signed in.")
        elif choice == "3":
            if not _require_signed_in(vault):
                continue
            print("Adding password")
            name = input("Please enter the record name: ").strip()
            username = input("Please enter the username: ").strip()
            password = _prompt_password("Please enter the password: ")
            try:
                vault.add(name, username, password)
            except ValueError as exc:
                print("Error: %s" % exc)
                continue
            print("Record saved: %s" % name)
        elif choice == "4":
            if not _require_signed_in(vault):
                continue
            print("Fetching password")
            name = input("Please enter the record name: ").strip()
            found = vault.get(name)
            if found is None:
                print("No such record: %s" % name)
                continue
            username, password = found
            print("For %s" % name)
            print("The username: is %s" % username)
            print("The password is: %s" % password)
        elif choice == "5":
            if not _require_signed_in(vault):
                continue
            names = vault.list_names()
            if not names:
                print("(vault is empty)")
            else:
                for name in names:
                    print(name)
        elif choice == "6":
            if not _require_signed_in(vault):
                continue
            name = input("Please enter the record name: ").strip()
            if vault.delete(name):
                print("Deleted record: %s" % name)
            else:
                print("No such record: %s" % name)
        else:
            print("Unknown choice: %s" % choice)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="CC Password Manager")
    parser.add_argument(
        "--dir", default=".", help="directory holding vault files (default: .)"
    )
    args = parser.parse_args(argv)
    return run_menu(args.dir)


if __name__ == "__main__":
    raise SystemExit(main())
