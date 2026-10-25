# SPEC — Data Privacy Vault (somecoolprojects entry 39)

Source challenge page (read first, built from its steps, not memory):
https://codingchallenges.fyi/challenges/challenge-data-privacy-vault/
Slug used: `challenge-data-privacy-vault` (found via web search; the
first-guess URL matched the search result exactly — no 404, no correction).

## What the page asks for

- Step 0: an HTTP service in the language of choice.
- Step 1: a tokenisation service, initially in-memory, with two endpoints:
  - `POST /tokenize` — request `{"id": "<req-id>", "data": {"field1":
    "value1", ...}}`; success response HTTP 201 with the same `id` and
    `data` mapping each field to a random-looking token
    (e.g. `"field1": "t6yh4f6"`). Appropriate error codes for bad input.
  - `POST /detokenize` — request with tokens in place of values; response
    `{"id": "<req-id>", "data": {"field1": {"found": true, "value":
    "value1"}, ...}}`. A token that is not found yields
    `{"found": false, "value": ""}` for that field, not an HTTP error.
- Step 2: a persistent store, with all stored data encrypted. The page
  suggests Redis (or a home-built one) and notes format-preserving
  encryption (FPE) as an option that keeps a value's format/length
  (e.g. a phone number stays phone-number-shaped).
- Step 3: authenticated access, service-to-service, where the reader may
  not be the writer: verify the caller may create tokens (refuse
  otherwise) and may detokenize (error otherwise). Production traffic
  should be over HTTPS.
- Going Further (not required): per-payload format spec, IdP/IAM
  integration, KMS integration, websockets/gRPC, deployable service.

## What this build implements

- `POST /tokenize` → 201, `{"id", "data": {field: token}}`.
- `POST /detokenize` → 200, `{"id", "data": {field: {"found", "value"}}}`,
  unknown tokens → `{"found": false, "value": ""}` per field.
- Persistent store: a JSON file on disk holding only encrypted blobs
  (never plaintext values). In-memory mode when no store path is given
  (Step 1 behaviour). Restarting the server with the same store file
  and the same master key recovers all tokens.
- Encryption (stdlib only — see DESIGN.md for the honest limits):
  PBKDF2-HMAC-SHA256 key derivation + an HMAC-keystream XOR stream
  construction with an HMAC-SHA256 authentication tag
  (encrypt-then-MAC). This is NOT AES and is NOT claimed to be
  production-grade.
- Authentication (Step 3): `Authorization: Bearer <api-key>` on both
  endpoints. Each key carries scopes: `tokenize`, `detokenize`, or both.
  A writer-only key cannot detokenize and vice versa. Missing/invalid
  key → 401; valid key without the needed scope → 403.
- Audit log: append-only JSON Lines, one record per request, containing
  timestamp, request id, operation, actor (key id), field names and
  outcome — never plaintext values and never full tokens.
- Error codes: 400 malformed JSON / missing or mistyped `id` / `data` /
  non-string field values / empty `data`; 401 missing or unknown bearer
  key; 403 key lacks the scope; 404 unknown path; 405 wrong method on a
  known path; 500 store/encryption failure (no internals leaked).

## What this build deliberately does NOT implement

- Format-preserving encryption: the page presents FPE as an option
  ("for some services…"), not a required step. Tokens here are opaque
  random strings, which is the page's main token model. See DESIGN.md.
- HTTPS termination, IdP/IAM, KMS, websockets/gRPC, deployable
  packaging: listed under Going Further / the Step 3 HTTPS note. The
  server binds plain HTTP on localhost by default; put a TLS reverse
  proxy (e.g. Caddy/nginx) in front for anything beyond local use.
- No real secrets anywhere in the repo or tests: all fixtures are
  synthetic (e.g. `value1`, `Alice Example`), and test stores live in
  temporary directories.
