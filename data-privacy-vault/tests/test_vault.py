"""Tests for the Data Privacy Vault. Synthetic fixtures only, all
stores/audit logs in temp directories, HTTP tests on ephemeral
localhost ports. No real secrets anywhere."""

import base64
import json
import os
import re
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vault import (  # noqa: E402
    Vault, VaultError, decrypt_value, derive_key, encrypt_value, make_server,
)

MASTER = "test-master-key-synthetic"
OTHER_MASTER = "different-test-master-key"
ADMIN = "test-admin-key"
WRITER = "test-writer-key"
READER = "test-reader-key"
PRINCIPALS = {
    ADMIN: {"id": "admin", "scopes": {"tokenize", "detokenize"}},
    WRITER: {"id": "writer", "scopes": {"tokenize"}},
    READER: {"id": "reader", "scopes": {"detokenize"}},
}
TOKEN_RE = re.compile(r"^[a-z0-9]{12}$")


def make_vault(tmp, master=MASTER):
    return Vault(store_path=os.path.join(tmp, "vault.json"),
                 master_key=master, principals=PRINCIPALS,
                 audit_path=os.path.join(tmp, "audit.jsonl"))


class TestTokens(unittest.TestCase):
    def test_tokenize_shape_and_uniqueness(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = make_vault(tmp)
            out = v.tokenize({"field1": "value1", "field2": "value2"},
                             request_id="req-1", actor="admin")
            self.assertEqual(set(out), {"field1", "field2"})
            for token in out.values():
                self.assertRegex(token, TOKEN_RE)
            self.assertNotEqual(out["field1"], out["field2"])
            again = v.tokenize({"field1": "value1"})
            self.assertNotEqual(again["field1"], out["field1"])

    def test_detokenize_roundtrip_and_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = make_vault(tmp)
            tokens = v.tokenize({"field1": "value1", "field2": "value2"})
            got = v.detokenize({"field1": tokens["field1"],
                                "field2": tokens["field2"],
                                "field3": "zzzzzzzzzzzz"})
            self.assertEqual(got["field1"], {"found": True, "value": "value1"})
            self.assertEqual(got["field2"], {"found": True, "value": "value2"})
            self.assertEqual(got["field3"], {"found": False, "value": ""})

    def test_memory_mode(self):
        v = Vault(master_key=MASTER, principals=PRINCIPALS)
        tokens = v.tokenize({"name": "Alice Example"})
        self.assertEqual(v.detokenize(tokens)["name"]["value"], "Alice Example")


class TestEncryptionAndStore(unittest.TestCase):
    def test_encrypt_roundtrip_various_lengths(self):
        key = derive_key(MASTER, b"saltsaltsaltsalt")
        for text in ["", "x", "value1", "A" * 32, "B" * 100,
                     "ünïcödé ✓ value"]:
            self.assertEqual(decrypt_value(encrypt_value(text, key), key), text)

    def test_wrong_key_and_flipped_tag_raise(self):
        key = derive_key(MASTER, b"saltsaltsaltsalt")
        other = derive_key(OTHER_MASTER, b"saltsaltsaltsalt")
        blob = encrypt_value("value1", key)
        with self.assertRaises(VaultError):
            decrypt_value(blob, other)
        tampered = dict(blob)
        raw = bytearray(base64.b64decode(tampered["tag"]))
        raw[0] ^= 1
        tampered["tag"] = base64.b64encode(bytes(raw)).decode()
        with self.assertRaises(VaultError):
            decrypt_value(tampered, key)

    def test_store_file_contains_no_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = make_vault(tmp)
            v.tokenize({"card": "4111111111111111", "name": "Alice Example"})
            with open(os.path.join(tmp, "vault.json"), "rb") as fh:
                raw = fh.read()
            self.assertNotIn(b"4111111111111111", raw)
            self.assertNotIn(b"Alice Example", raw)

    def test_persistence_same_key_and_wrong_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = make_vault(tmp)
            tokens = v.tokenize({"field1": "value1"})
            reopened = make_vault(tmp)
            self.assertEqual(reopened.detokenize(tokens)["field1"]["value"],
                             "value1")
            wrong = make_vault(tmp, master=OTHER_MASTER)
            self.assertEqual(wrong.detokenize(tokens)["field1"],
                             {"found": False, "value": ""})

    def test_tampered_ciphertext_is_not_found_not_garbage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "vault.json")
            v = Vault(store_path=path, master_key=MASTER, principals=PRINCIPALS)
            tokens = v.tokenize({"field1": "value1"})
            token = tokens["field1"]
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            blob = raw["tokens"][token]
            cipher = bytearray(base64.b64decode(blob["cipher"]))
            cipher[0] ^= 1
            blob["cipher"] = base64.b64encode(bytes(cipher)).decode()
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh)
            reopened = Vault(store_path=path, master_key=MASTER,
                             principals=PRINCIPALS)
            self.assertEqual(reopened.detokenize({"field1": token})["field1"],
                             {"found": False, "value": ""})


class TestAudit(unittest.TestCase):
    def test_audit_lines_have_no_values_or_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            v = make_vault(tmp)
            tokens = v.tokenize({"field1": "value1"}, request_id="req-9",
                                actor="admin")
            v.detokenize({"field1": tokens["field1"],
                          "fieldX": "zzzzzzzzzzzz"},
                         request_id="req-10", actor="reader")
            with open(os.path.join(tmp, "audit.jsonl"), encoding="utf-8") as fh:
                lines = [json.loads(line) for line in fh]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["op"], "tokenize")
            self.assertEqual(lines[0]["request_id"], "req-9")
            self.assertEqual(lines[1]["found"], 1)
            self.assertEqual(lines[1]["missing"], 1)
            with open(os.path.join(tmp, "audit.jsonl"),
                      encoding="utf-8") as fh:
                blob = fh.read()
            self.assertNotIn("value1", blob)
            self.assertNotIn(tokens["field1"], blob)


# ------------------------------------------------------------ HTTP tests


class HttpVaultCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = make_vault(self.tmp.name)
        self.server = make_server(self.vault, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post(self, path, payload, key=None, raw=None, method="POST"):
        data = raw if raw is not None else json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if key:
            req.add_header("Authorization", "Bearer " + key)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_tokenize_detokenize_flow(self):
        status, body = self.post("/tokenize",
                                 {"id": "req-12345",
                                  "data": {"field1": "value1",
                                           "field2": "value2"}},
                                 key=ADMIN)
        self.assertEqual(status, 201)
        self.assertEqual(body["id"], "req-12345")
        self.assertRegex(body["data"]["field1"], TOKEN_RE)
        status, body = self.post("/detokenize",
                                 {"id": "req-33445", "data": body["data"]},
                                 key=ADMIN)
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["field1"]["value"], "value1")

    def test_detokenize_unknown_token_per_field(self):
        status, body = self.post("/detokenize",
                                 {"id": "req-33445",
                                  "data": {"field3": "invalid token"}},
                                 key=ADMIN)
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["field3"],
                         {"found": False, "value": ""})

    def test_auth_matrix(self):
        cases = [
            (None, "/tokenize", 401), ("nope", "/tokenize", 401),
            (READER, "/tokenize", 403), (WRITER, "/detokenize", 403),
        ]
        for key, path, expected in cases:
            status, _ = self.post(path, {"id": "r", "data": {"f": "v"}},
                                  key=key)
            self.assertEqual(status, expected, (key, path))
        status, _ = self.post("/tokenize", {"id": "r", "data": {"f": "v"}},
                              key=WRITER)
        self.assertEqual(status, 201)
        status, _ = self.post("/detokenize",
                              {"id": "r", "data": {"f": "zzzzzzzzzzzz"}},
                              key=READER)
        self.assertEqual(status, 200)

    def test_bad_input(self):
        bad = [
            ({"data": {"f": "v"}}, 400),                       # missing id
            ({"id": "r", "data": "nope"}, 400),                 # data not obj
            ({"id": "r", "data": {"f": 42}}, 400),              # non-str value
            ({"id": "r", "data": {}}, 400),                     # empty data
            ({"id": "", "data": {"f": "v"}}, 400),              # empty id
        ]
        for payload, expected in bad:
            status, _ = self.post("/tokenize", payload, key=ADMIN)
            self.assertEqual(status, expected, payload)
        status, _ = self.post("/tokenize", None, key=ADMIN, raw=b"{not json")
        self.assertEqual(status, 400)

    def test_routing(self):
        status, _ = self.post("/nope", {"id": "r", "data": {"f": "v"}},
                              key=ADMIN)
        self.assertEqual(status, 404)
        status, _ = self.post("/tokenize", {"id": "r", "data": {"f": "v"}},
                              key=ADMIN, method="GET")
        self.assertEqual(status, 405)

    def test_persistence_across_restart(self):
        _, body = self.post("/tokenize",
                            {"id": "r1", "data": {"field1": "value1"}},
                            key=ADMIN)
        token = body["data"]["field1"]
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        vault2 = make_vault(self.tmp.name)
        server2 = make_server(vault2, port=0)
        thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
        thread2.start()
        self.addCleanup(server2.shutdown)
        self.addCleanup(server2.server_close)
        base2 = "http://127.0.0.1:%d" % server2.server_address[1]
        req = urllib.request.Request(
            base2 + "/detokenize",
            data=json.dumps({"id": "r2", "data": {"field1": token}}).encode(),
            method="POST")
        req.add_header("Authorization", "Bearer " + ADMIN)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body2 = json.loads(resp.read().decode())
        self.assertEqual(body2["data"]["field1"]["value"], "value1")
        thread2.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
