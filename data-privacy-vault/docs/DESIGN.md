# DESIGN — Data Privacy Vault

## Assumptions (stated before coding, per ponytail rules)

1. One token per field value, generated independently of the value.
   Tokenizing the same value twice yields two different tokens. This
   is genuine tokenization (a random lookup key), not deterministic
   encryption, and it matches the page's example tokens.
2. Tokens are opaque: 12 characters drawn from `[a-z0-9]` with
   `secrets` (CSPRNG). They carry no information about the value and
   are unique within a store (regenerate on collision).
3. Field names are not sensitive; values are. Field names appear in
   audit records; values and full tokens never do.
4. `id` is a caller-supplied request/correlation id, echoed verbatim.
   It is not validated for uniqueness — the page treats it as an echo.
5. The caller, not the vault, owns the mapping from business records
   to tokens. The vault never sees a record id, only field values.
6. Keys and the master key arrive via environment / CLI flags, never
   hardcoded. Tests pass keys explicitly to the constructor.

## Layout

Single file, Python 3 standard library only:

```
data-privacy-vault/
  vault.py          # library + HTTP server + CLI (serve)
  docs/             # SPEC.md, DESIGN.md, TEST_PLAN.md
  tests/test_vault.py
  README.md
```

## Components

### Encryption (stdlib only — honest limits)

Python's stdlib has no AES. Rather than vendor crypto or claim
otherwise, values are protected with:

- Key derivation: `hashlib.pbkdf2_hmac("sha256", master_key, salt,
  210_000)` → 32-byte key. The salt is random per store file and
  stored in the file header (a salt is not secret).
- Stream construction: for each value, a fresh 16-byte nonce from
  `secrets.token_bytes`. Keystream blocks are
  `HMAC-SHA256(key, nonce || counter)` for counter = 0, 1, 2, …;
  ciphertext = plaintext XOR keystream. A fresh nonce per value means
  keystream reuse across values cannot happen by construction.
- Authentication: tag = `HMAC-SHA256(key, nonce || ciphertext)`.
  Decryption verifies the tag with `hmac.compare_digest` before
  unmasking and raises on mismatch (tampered store entry → the token
  detokenizes as not found at the HTTP layer, never as garbage).

Limits, stated plainly: this is a textbook-style construction, not a
reviewed AEAD cipher (no AES-GCM/ChaCha20-Poly1305). It is adequate
for a coding challenge and for learning tokenization, and it must NOT
be presented as production-grade encryption. For production, swap
`encrypt_value`/`decrypt_value` for a real AEAD (e.g. `cryptography`
AES-GCM) behind the same blob format — the token/store/audit layers
do not depend on the construction. The master key is the single point
of failure: anyone with the store file AND the master key can decrypt
everything, so key management (KMS, per the page's Going Further) is
the real production gap, not just the cipher choice.

### Store

JSON file, atomically replaced on each write (write temp file in the
same directory, `os.replace`):

```json
{"salt": "<base64>", "tokens": {"<token>": {"nonce": "<b64>",
 "cipher": "<b64>", "tag": "<b64>"}}}
```

- In-memory mode: `store_path=None` — same code path, no file.
- On load, a corrupt file or a wrong master key surfaces at startup
  (bad tag is detected lazily per value at detokenize time, because
  tags are per value; a structurally corrupt file fails fast at load).
- Concurrency: the HTTP server is a `ThreadingHTTPServer` guarded by
  a single `threading.Lock` around tokenize/detokenize/store writes.
  Correctness over throughput — this is a vault, not a hot path.

### Auth

`Vault` takes `principals: {api_key: {"id": "<actor>", "scopes":
{"tokenize", "detokenize"}}}`. The HTTP layer extracts the bearer
token, looks it up, and enforces the scope for the endpoint.
Comparison uses `hmac.compare_digest` over the key lookup (constant
time per candidate is unnecessary for a dict lookup, but the key
itself is never logged). Unknown actor ids are never echoed back.

Server defaults (CLI): keys come from `--writer-key` / `--reader-key`
/ `--admin-key` flags or `VAULT_WRITER_KEY` / `VAULT_READER_KEY` /
`VAULT_ADMIN_KEY` env vars. If none are supplied, the server refuses
to start rather than running open or with a guessable default key.
The master key comes from `--master-key` or `VAULT_MASTER_KEY`; if
absent, an ephemeral random key is generated and a warning printed —
data then survives only until restart, which is stated at startup.

### Audit

Append-only JSON Lines file (`--audit` / `VAULT_AUDIT_LOG`, default
`<store>.audit.jsonl` next to a file store, or off in memory mode).
One line per request: `{"ts", "op", "request_id", "actor", "fields",
"ok", "found": n, "missing": n}` for detokenize, and the analogous
record for tokenize. No values, no tokens, no keys. A failed audit
write must not fail the request, but it is recorded on stderr.

### HTTP behaviour

- `POST /tokenize`, `POST /detokenize` only. Bodies must be JSON
  objects with string `id` and object `data` of string→string.
  `data` must be non-empty (an empty tokenize is a client bug; an
  empty detokenize is likewise rejected, rather than silently
  succeeding — this is the one judgement call beyond the page, which
  is silent on empty payloads).
- Responses echo `id` verbatim, including on per-field not-found.
- Unknown tokens never leak whether a token prefix is "close" — the
  response is identical for every unknown token.
- `Content-Type: application/json` on all responses; oversized bodies
  (>1 MiB) are rejected with 413 to bound memory use.

## Simplicity notes

- No framework, no Redis, no third-party dependency: `http.server`
  + `json` + `hashlib`/`hmac` + `secrets` + `sqlite`-free JSON store.
  The page allows Redis; a file store keeps the single-file, stdlib
  constraint and is trivially inspectable.
- FPE deliberately omitted (see SPEC.md): it would add a second
  cipher construction for an optional page note, against the
  minimum-code rule. Opaque tokens already satisfy the page's core
  contract.
