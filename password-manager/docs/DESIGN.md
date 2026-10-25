# password-manager — DESIGN

## Assumptions (stated before coding, per ponytail rules)

- Python 3 standard library only: `hashlib`, `hmac`, `json`,
  `getpass`, `argparse`, `os`, `secrets`. No third-party crypto.
- One vault = one file, one process at a time. No locking, no
  concurrent-writer handling, no migration between formats.
- The master password is never stored. Only a salt, a verifier,
  and authenticated ciphertext live on disk.
- Records are small (a handful of short strings); whole-vault
  re-encryption on every save is acceptable and keeps the code
  minimal.
- Tests use synthetic entries in temporary directories only,
  never real credentials.

## Vault file format (`.ccv`, JSON)

```json
{
  "format": 1,
  "salt": "<base64, 16 random bytes>",
  "iterations": 200000,
  "nonce": "<base64, 16 random bytes>",
  "verifier": "<base64 HMAC>",
  "tag": "<base64 HMAC>",
  "ciphertext": "<base64>"
}
```

## Encryption construction — honest statement

**This is NOT AES-256 / AES-GCM and is NOT production-grade.**
Python's standard library ships no AES, so the page's recommended
cipher cannot be built under the stdlib-only constraint. What is
built instead:

1. **Key derivation:** `PBKDF2-HMAC-SHA256(master_password, salt,
   200_000 iterations)` → 32-byte key. (200k is a pragmatic
   choice: strong enough to be non-trivial, fast enough that the
   test suite stays quick. OWASP's current guidance for
   PBKDF2-HMAC-SHA256 is higher; a real manager would use
   Argon2id or AES-GCM via a vetted library.)
2. **Stream cipher:** keystream blocks are
   `HMAC-SHA256(key, b"stream" || nonce || counter_be32)`,
   XORed with the plaintext. HMAC-SHA256 as a keystream is a
   standard PRF-based construction, but it has no nonce-misuse
   analysis, no hardware acceleration, and no peer review as a
   cipher — do not reuse it for real secrets.
3. **Authentication:** `tag = HMAC-SHA256(key, b"tag" || nonce ||
   ciphertext)`, verified with `hmac.compare_digest` BEFORE
   decryption, so tampered files and wrong passwords are both
   rejected without leaking plaintext. A separate
   `verifier = HMAC-SHA256(key, b"verifier")` lets sign-in fail
   fast on a wrong master password.
4. **Fresh randomness per vault and per save:** a new salt at
   vault creation, a new nonce on every save, via `secrets`.

Consequences, stated plainly: no forward secrecy, no protection
against an attacker who can read process memory (the key lives in
memory while signed in), no idle timeout (page's "Going Further"),
and the HMAC-stream construction has not been audited. Suitable
for the coding challenge; unsuitable for real passwords.

## Plaintext payload

The decrypted bytes are UTF-8 JSON:

```json
{"records": {"<name>": {"username": "...", "password": "..."}}}
```

Record names are the dict keys, so names are unique and add
overwrites. Plaintext JSON is sorted by key for stable output;
nothing plaintext is ever written to disk (verified by test).

## Module layout (single file, `manager.py`)

- `VaultError`, `WrongPasswordError`, `CorruptVaultError`
  (all `ValueError` subclasses, so callers can catch broadly).
- `validate_vault_name(name)` — filename-safety check.
- `_derive_key(password, salt, iterations)`,
  `_encrypt(key, plaintext) -> (nonce, ciphertext, tag)`,
  `_decrypt(key, nonce, ciphertext, tag)` — raises on bad tag.
- `class Vault` — `create(path, password)`, `open(path,
  password)`, `add/get/list_names/delete`, `_save()` (re-encrypts
  and writes atomically-ish via write-to-temp + `os.replace`).
- Interactive layer — `main(argv)`: argparse for `--dir`, the
  menu loop, prompt helpers. `_prompt_password()` uses `getpass`
  on a TTY and plain `input()` when stdin is piped, so scripted
  sessions (and tests) work deterministically.
- `if __name__ == "__main__": raise SystemExit(main())` — the
  module is importable by tests without running the menu.

## Success criteria (verifiable)

- Create → sign in → add → fetch round-trips a record exactly.
- Wrong master password is rejected at sign-in.
- A tampered vault file is rejected, never partially decrypted.
- No record username/password appears anywhere in the vault
  file bytes.
- List shows sorted names; delete removes only that record and
  persists across reopen.
- All tests in `tests/` pass (see TEST_PLAN.md).
