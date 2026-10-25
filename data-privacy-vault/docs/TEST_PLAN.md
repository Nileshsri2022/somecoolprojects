# TEST_PLAN — Data Privacy Vault

Run from the project directory:

```sh
python3 -m unittest discover -s tests -v
```

All tests use synthetic fixtures only (e.g. `value1`, `Alice Example`)
and temporary directories (`tempfile.TemporaryDirectory`) for stores
and audit logs. No real secrets, no network beyond localhost, no
writes outside the temp dir.

## Library tests (`Vault`, encryption)

1. Tokenize returns one token per field, tokens are 12-char
   `[a-z0-9]`, distinct across fields, and distinct for the same
   value tokenized twice.
2. Detokenize round-trips every field; unknown token → `found False,
   value ""` mixed with found fields in one request.
3. Store file contains no plaintext: the raw file bytes do not contain
   any fixture value, and no token maps to plaintext on disk.
4. Persistence: new `Vault` on the same store file + same master key
   detokenizes old tokens; a different master key fails to recover
   them (tamper/wrong-key → not found, never garbage).
5. Tampered ciphertext (flipped byte in the store file) → token
   detokenizes as not found (tag verification), not as corrupted text.
6. Encryption unit: `decrypt(encrypt(x)) == x` for empty, short,
   long (> one keystream block, i.e. > 32 bytes), and non-ASCII
   values; wrong key and flipped tag both raise.
7. Audit log: tokenize/detokenize append one JSON line each with the
   expected fields, and neither line contains a fixture value or a
   full token.

## HTTP tests (live server on an ephemeral localhost port)

8. `POST /tokenize` with the admin key → 201, echoed `id`, tokens per
   field; followed by `POST /detokenize` → 200 with found values.
9. Unknown token via HTTP → per-field `found False`, HTTP 200.
10. Auth: no header → 401; unknown key → 401; writer-only key on
    `/detokenize` → 403; reader-only key on `/tokenize` → 403;
    writer-only key on `/tokenize` and reader-only on `/detokenize`
    succeed.
11. Bad input: malformed JSON → 400; missing `id` → 400; `data` not
    an object → 400; non-string value → 400; empty `data` → 400.
12. Routing: unknown path → 404; `GET /tokenize` → 405.
13. Persistence over HTTP: restart the server on the same store +
    master key; previously issued tokens still detokenize.

## Success criteria

All tests pass (`OK`, zero failures/errors). The store-file
plaintext check (3) and the tamper check (5) are the security
regression gates: if either regresses, the vault is not shippable
even if the API tests pass.
