# data-privacy-vault — Build Your Own Data Privacy Vault

Coding Challenges #39, worked in `somecoolprojects/`.
Docs first, then code — see `docs/` (`SPEC.md`, `DESIGN.md`,
`TEST_PLAN.md`).

An HTTP tokenisation service: send sensitive fields, get back opaque
tokens; only an authorised reader can turn tokens back into values.
Python 3 standard library only, single main file.

## What it implements (challenge steps)

- **Step 1** — `POST /tokenize` → 201 `{"id", "data": {field: token}}`;
  `POST /detokenize` → 200 `{"id", "data": {field: {"found", "value"}}}`,
  unknown tokens → `{"found": false, "value": ""}` per field.
- **Step 2** — persistent JSON store holding only encrypted blobs
  (never plaintext). Restart with the same store + master key and old
  tokens still work.
- **Step 3** — bearer-key auth with separate scopes: a writer-only key
  cannot detokenize, a reader-only key cannot tokenize (401 unknown
  key, 403 wrong scope). Append-only audit log records operations,
  actors and field names — never values or tokens.

Encryption is an honest stdlib construction (PBKDF2-HMAC-SHA256 +
HMAC-keystream XOR + encrypt-then-MAC tag), **not** AES and **not**
production-grade — see `docs/DESIGN.md` for the limits and the
production swap-out. Format-preserving encryption, HTTPS termination,
IdP/KMS integration are documented divergences (page presents FPE as
optional; the rest are Going Further items).

## Usage

```sh
python3 vault.py serve --port 8000 --store vault.json \
  --master-key "$VAULT_MASTER_KEY" --admin-key "$VAULT_ADMIN_KEY"
# or writer/reader split: --writer-key ... --reader-key ...
```

Then (keys via `Authorization: Bearer <key>`):

```sh
curl -s -X POST localhost:8000/tokenize -H "Authorization: Bearer $KEY" \
  -d '{"id": "req-12345", "data": {"field1": "value1"}}'
# {"id": "req-12345", "data": {"field1": "xguv7lb8m0ba"}}

curl -s -X POST localhost:8000/detokenize -H "Authorization: Bearer $KEY" \
  -d '{"id": "req-33445", "data": {"field1": "xguv7lb8m0ba"}}'
# {"id": "req-33445", "data": {"field1": {"found": true, "value": "value1"}}}
```

The server refuses to start with no API keys. Without a master key it
generates an ephemeral one (data lasts only until restart). Plain
HTTP is for local use — put a TLS reverse proxy in front for
anything else.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

15 tests: token shape/uniqueness, round-trip + unknown tokens,
encryption round-trips, no-plaintext store file, persistence with the
right/wrong master key, tamper → not-found (never garbage), audit
contents, the full HTTP flow, the auth matrix, bad-input codes,
routing, and restart persistence. All fixtures are synthetic; test
stores live in temp directories.
