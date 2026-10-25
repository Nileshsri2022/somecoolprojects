# password-manager — TEST_PLAN

All tests are `unittest`, in `tests/test_manager.py`, run from the
project directory:

```sh
python3 -m unittest discover -s tests -v
```

All fixtures are synthetic entries (e.g. record `cc test record`,
username `john`, password `secretpassword` — the page's example)
created in `tempfile.TemporaryDirectory` vault dirs. No real
credentials, no files outside the temp dir, no network.

## Library tests (Vault API)

1. **Create/open round-trip:** create a vault, add a record,
   reopen with the same master password, fetch returns the exact
   username and password.
2. **Wrong password rejected:** opening with a different master
   password raises `WrongPasswordError`.
3. **Wrong password at create-confirm is a CLI concern** (see
   CLI tests); the API rejects an empty master password.
4. **Duplicate add overwrites:** adding the same record name
   twice keeps only the second username/password.
5. **Missing record:** `get` returns `None`; `delete` returns
   `False` and leaves other records intact.
6. **List sorted:** names come back sorted regardless of
   insertion order; empty vault lists `[]`.
7. **Delete persists:** delete a record, reopen, it stays gone
   while siblings remain.
8. **Create existing fails:** creating over an existing vault
   file raises `FileExistsError` and does not clobber it.
9. **Open missing file fails:** `FileNotFoundError`.
10. **Unsafe vault names rejected:** ``, `.`, `..`, names
    containing `/` or `\` raise `ValueError`.
11. **No plaintext on disk:** after saving, the vault file bytes
    contain neither the record password nor the username.
12. **Tamper rejected:** flipping a byte of the stored ciphertext
    (or tag) makes `open` raise (`CorruptVaultError` /
    `WrongPasswordError` subclass handling — either rejection
    counts, asserted as `VaultError`).
13. **Different salts, different ciphertext:** two vaults with the
    same master password and same record produce different file
    bytes (fresh random salt/nonce per vault/save).
14. **Empty vault round-trips:** create, reopen, list is empty.

## CLI tests (subprocess, piped stdin)

15. **Full menu session:** create vault (with matching
    confirmation) → sign in → add → fetch → list → delete →
    quit; stdout contains the page's phrases
    (`New vault created and saved as:`, `Thank you, you are now
    signed in.`, `The password is: secretpassword`) and exits 0.
16. **Mismatched confirmation:** create with two different master
    passwords prints an error and creates no file.
17. **Add/fetch without sign-in:** menu options 3–6 before sign-in
    print `You are not signed in to a vault.` and do not crash.
18. **Wrong password at CLI sign-in:** prints an error, stays
    unsigned-in (a following fetch still refuses).
19. **Quit variants:** `q` and `quit` both exit 0; EOF exits 0.

## Out of scope for tests

- Real AES-GCM equivalence (not built — see DESIGN.md).
- Idle timeout / modify-in-place (not built — see SPEC.md).
- Concurrency, permissions hardening, memory scrubbing.
