#!/usr/bin/env python3
"""Data Privacy Vault — codingchallenges.fyi challenge-data-privacy-vault.

HTTP tokenisation service (Step 1), persistent encrypted store (Step 2)
and scoped bearer-token auth (Step 3). Python 3 standard library only.

Endpoints (JSON, ``Authorization: Bearer <api-key>`` required):
    POST /tokenize   -> 201 {"id", "data": {field: token}}
    POST /detokenize -> 200 {"id", "data": {field: {"found", "value"}}}
    Unknown tokens detokenize per-field as {"found": false, "value": ""}.

Encryption — honest limits (see docs/DESIGN.md): the stdlib has no AES,
so values are protected with PBKDF2-HMAC-SHA256 key derivation plus an
HMAC-keystream XOR stream construction with an encrypt-then-MAC tag.
This is NOT AES and NOT production-grade; for production, replace
encrypt_value/decrypt_value with a reviewed AEAD (e.g. AES-GCM) behind
the same blob format. Never store real secrets in tests — use synthetic
fixtures only.

Usage:
    python3 vault.py serve [--port 8000] [--store vault.json]
                           [--audit vault.audit.jsonl]
                           [--master-key KEY] [--writer-key KEY]
                           [--reader-key KEY] [--admin-key KEY]
    Keys may also come from VAULT_MASTER_KEY / VAULT_WRITER_KEY /
    VAULT_READER_KEY / VAULT_ADMIN_KEY. The server refuses to start
    with no API keys rather than running open. Without a master key an
    ephemeral one is generated (data lasts only until restart).
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import string
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

__all__ = [
    "Vault",
    "VaultError",
    "encrypt_value",
    "decrypt_value",
    "derive_key",
    "make_server",
]

_TOKEN_ALPHABET = string.ascii_lowercase + string.digits
_TOKEN_LENGTH = 12
_PBKDF2_ITERATIONS = 210_000
_NONCE_LENGTH = 16
_KEY_LENGTH = 32
_MAX_BODY = 1024 * 1024  # 1 MiB


class VaultError(Exception):
    """Raised for tampered/wrong-key blobs and corrupt stores."""


# ---------------------------------------------------------------- crypto


def derive_key(master_key, salt):
    """Derive a 32-byte key from a master-key string and a salt."""
    if isinstance(master_key, str):
        master_key = master_key.encode("utf-8")
    return hashlib.pbkdf2_hmac(
        "sha256", master_key, salt, _PBKDF2_ITERATIONS, dklen=_KEY_LENGTH
    )


def _keystream(key, nonce, length):
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(
            key, nonce + counter.to_bytes(8, "big"), hashlib.sha256
        ).digest()
        counter += 1
    return bytes(out[:length])


def encrypt_value(plaintext, key):
    """Encrypt a string -> blob dict (base64 nonce/cipher/tag).

    Fresh nonce per value, so no keystream is ever reused. The tag
    covers nonce || ciphertext (encrypt-then-MAC).
    """
    data = plaintext.encode("utf-8")
    nonce = secrets.token_bytes(_NONCE_LENGTH)
    cipher = bytes(b ^ k for b, k in zip(data, _keystream(key, nonce, len(data))))
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    return {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "cipher": base64.b64encode(cipher).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }


def decrypt_value(blob, key):
    """Inverse of encrypt_value; raises VaultError on bad tag/format."""
    try:
        nonce = base64.b64decode(blob["nonce"], validate=True)
        cipher = base64.b64decode(blob["cipher"], validate=True)
        tag = base64.b64decode(blob["tag"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise VaultError("malformed encrypted blob") from exc
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise VaultError("authentication tag mismatch")
    plain = bytes(b ^ k for b, k in zip(cipher, _keystream(key, nonce, len(cipher))))
    return plain.decode("utf-8")


# ---------------------------------------------------------------- vault


def _utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Vault:
    """Token store: token -> encrypted value, plus an audit log.

    principals: {api_key: {"id": actor, "scopes": {"tokenize", ...}}}
    """

    def __init__(self, store_path=None, master_key=None, principals=None,
                 audit_path=None):
        self.store_path = store_path
        self.audit_path = audit_path
        self.principals = principals or {}
        self._lock = threading.Lock()
        if master_key is None:
            master_key = secrets.token_hex(32)
            print("warning: no master key supplied; generated an ephemeral "
                  "one — stored tokens will not survive restart",
                  file=sys.stderr)
        self._salt = None
        self._tokens = {}
        if store_path and os.path.exists(store_path):
            self._load()
        if self._salt is None:
            self._salt = secrets.token_bytes(16)
            if store_path:
                self._save_locked()
        self._key = derive_key(master_key, self._salt)

    # -- persistence -------------------------------------------------
    def _load(self):
        with open(self.store_path, "r", encoding="utf-8") as fh:
            try:
                raw = json.load(fh)
                self._salt = base64.b64decode(raw["salt"], validate=True)
                tokens = raw["tokens"]
                if not isinstance(tokens, dict):
                    raise ValueError("tokens is not an object")
                self._tokens = tokens
            except (ValueError, KeyError, TypeError) as exc:
                raise VaultError(
                    "corrupt store file: %s" % self.store_path) from exc

    def _save_locked(self):
        """Caller must hold self._lock. Atomic replace via temp file."""
        raw = {"salt": base64.b64encode(self._salt).decode("ascii"),
               "tokens": self._tokens}
        directory = os.path.dirname(os.path.abspath(self.store_path))
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".vault-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(raw, fh)
            os.replace(tmp, self.store_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- audit -------------------------------------------------------
    def _audit(self, op, request_id, actor, fields, ok, found=None, missing=None):
        if not self.audit_path:
            return
        record = {"ts": _utcnow(), "op": op, "request_id": request_id,
                  "actor": actor, "fields": sorted(fields), "ok": ok}
        if found is not None:
            record["found"] = found
            record["missing"] = missing
        try:
            with open(self.audit_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError as exc:
            print("warning: audit write failed: %s" % exc, file=sys.stderr)

    # -- auth --------------------------------------------------------
    def authorize(self, api_key, scope):
        """Return actor id if key has scope, else None (never raises)."""
        if not api_key:
            return None
        for candidate, info in self.principals.items():
            if hmac.compare_digest(candidate, api_key):
                if scope in info.get("scopes", set()):
                    return info.get("id", "unknown")
                return None
        return None

    # -- core operations ---------------------------------------------
    def _new_token(self):
        while True:
            token = "".join(secrets.choice(_TOKEN_ALPHABET)
                            for _ in range(_TOKEN_LENGTH))
            if token not in self._tokens:
                return token

    def tokenize(self, data, request_id="", actor=""):
        """data: {field: plaintext} -> {field: token}. Persists + audits."""
        with self._lock:
            result = {}
            for field, value in data.items():
                token = self._new_token()
                self._tokens[token] = encrypt_value(value, self._key)
                result[field] = token
            if self.store_path:
                self._save_locked()
        self._audit("tokenize", request_id, actor, data.keys(), True)
        return result

    def detokenize(self, data, request_id="", actor=""):
        """data: {field: token} -> {field: {"found", "value"}}."""
        result = {}
        found = missing = 0
        with self._lock:
            snapshot = dict(self._tokens)
        for field, token in data.items():
            blob = snapshot.get(token)
            if blob is None:
                result[field] = {"found": False, "value": ""}
                missing += 1
                continue
            try:
                result[field] = {"found": True,
                                 "value": decrypt_value(blob, self._key)}
                found += 1
            except VaultError:
                # Tampered entry or wrong master key: never leak garbage.
                result[field] = {"found": False, "value": ""}
                missing += 1
        self._audit("detokenize", request_id, actor, data.keys(), True,
                    found=found, missing=missing)
        return result


# ---------------------------------------------------------------- HTTP


def _validate_payload(body):
    """Return (request_id, data) or raise ValueError with a message."""
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    request_id = body.get("id")
    data = body.get("data")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("field 'id' must be a non-empty string")
    if not isinstance(data, dict) or not data:
        raise ValueError("field 'data' must be a non-empty object")
    for field, value in data.items():
        if not isinstance(value, str):
            raise ValueError("field %r must be a string" % field)
    return request_id, data


def make_server(vault, host="127.0.0.1", port=0):
    """Build a ThreadingHTTPServer bound to vault; port 0 = ephemeral."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep stdout clean
            pass

        def _send(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY:
                self._send(413, {"error": "request body too large"})
                return None
            raw = self.rfile.read(length) if length else b""
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._send(400, {"error": "malformed JSON"})
                return None

        def _auth(self, scope):
            header = self.headers.get("Authorization") or ""
            key = header[7:] if header.startswith("Bearer ") else ""
            actor = vault.authorize(key, scope)
            if not key or actor is None:
                # Distinguish unknown key (401) from wrong scope (403)
                # only when the key itself is recognised.
                known = any(hmac.compare_digest(c, key)
                            for c in vault.principals) if key else False
                self._send(403 if known else 401,
                           {"error": "forbidden" if known
                            else "unauthorized"})
                return None
            return actor

        def _handle(self, scope, func, status):
            actor = self._auth(scope)
            if actor is None:
                return
            body = self._read_body()
            if body is None:
                return
            try:
                request_id, data = _validate_payload(body)
            except ValueError as exc:
                self._send(400, {"error": str(exc)})
                return
            try:
                result = func(data, request_id=request_id, actor=actor)
            except VaultError as exc:
                self._send(500, {"error": str(exc)})
                return
            self._send(status, {"id": request_id, "data": result})

        def do_POST(self):
            if self.path == "/tokenize":
                self._handle("tokenize", vault.tokenize, 201)
            elif self.path == "/detokenize":
                self._handle("detokenize", vault.detokenize, 200)
            else:
                self._send(404, {"error": "unknown path"})

        def _method_not_allowed(self):
            if self.path in ("/tokenize", "/detokenize"):
                self._send(405, {"error": "method not allowed"})
            else:
                self._send(404, {"error": "unknown path"})

        do_GET = _method_not_allowed
        do_PUT = _method_not_allowed
        do_DELETE = _method_not_allowed
        do_PATCH = _method_not_allowed

    return ThreadingHTTPServer((host, port), Handler)


# ---------------------------------------------------------------- CLI


def _principal_set(writer_key, reader_key, admin_key):
    principals = {}
    if writer_key:
        principals[writer_key] = {"id": "writer", "scopes": {"tokenize"}}
    if reader_key:
        principals[reader_key] = {"id": "reader", "scopes": {"detokenize"}}
    if admin_key:
        principals[admin_key] = {"id": "admin",
                                 "scopes": {"tokenize", "detokenize"}}
    return principals


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Data Privacy Vault tokenisation service.")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the HTTP vault service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--store", default=None,
                       help="store file (omit for in-memory only)")
    serve.add_argument("--audit", default=None, help="audit JSONL file")
    serve.add_argument("--master-key",
                       default=os.environ.get("VAULT_MASTER_KEY"))
    serve.add_argument("--writer-key",
                       default=os.environ.get("VAULT_WRITER_KEY"))
    serve.add_argument("--reader-key",
                       default=os.environ.get("VAULT_READER_KEY"))
    serve.add_argument("--admin-key",
                       default=os.environ.get("VAULT_ADMIN_KEY"))
    args = parser.parse_args(argv)
    principals = _principal_set(args.writer_key, args.reader_key,
                                args.admin_key)
    if not principals:
        parser.error("refusing to start with no API keys: pass --writer-key, "
                     "--reader-key or --admin-key (or the VAULT_*_KEY env "
                     "vars).")
    audit = args.audit
    if audit is None and args.store:
        audit = args.store + ".audit.jsonl"
    vault = Vault(store_path=args.store, master_key=args.master_key,
                  principals=principals, audit_path=audit)
    server = make_server(vault, host=args.host, port=args.port)
    print("Data Privacy Vault listening on http://%s:%d (store=%s)"
          % (args.host, server.server_address[1],
             args.store or "in-memory"))
    print("NOTE: plain HTTP for local use only — put a TLS reverse proxy "
          "in front for anything else; encryption here is a stdlib "
          "construction, not production-grade AES (see docs/DESIGN.md).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
