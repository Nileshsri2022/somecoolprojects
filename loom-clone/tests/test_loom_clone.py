#!/usr/bin/env python3
"""Tests for loom_clone.py (stdlib unittest only)."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import loom_clone
from loom_clone import (
    create_recording, create_share, list_devices, list_recordings,
    load_recording, load_settings, make_server, read_media, register_device,
    resolve_share, revoke_share, select_device, set_folder, set_screen_source,
    start_recording, stop_recording, toggle, trim_recording, upload_chunk,
)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self.tmp.name, "recs")

    def tearDown(self):
        self.tmp.cleanup()

    def make_rec(self, **kw):
        return create_recording(self.folder, **kw)


class TestFolderAndSettings(Base):
    def test_set_folder_creates_and_returns_absolute(self):
        out = set_folder(self.folder)
        self.assertTrue(os.path.isdir(out))
        self.assertTrue(os.path.isabs(out))

    def test_set_folder_empty_rejected(self):
        with self.assertRaises(ValueError):
            set_folder("")

    def test_default_settings(self):
        s = load_settings(self.folder)
        self.assertFalse(s["mic_muted"])
        self.assertTrue(s["camera_enabled"])
        self.assertFalse(s["screen_mode"])
        self.assertIsNone(s["microphone"])

    def test_toggle_mic_camera_screen(self):
        self.assertTrue(toggle(self.folder, "mic")["mic_muted"])
        self.assertFalse(toggle(self.folder, "mic")["mic_muted"])
        self.assertFalse(toggle(self.folder, "camera")["camera_enabled"])
        self.assertTrue(toggle(self.folder, "screen")["screen_mode"])
        with self.assertRaises(ValueError):
            toggle(self.folder, "bogus")

    def test_screen_source_enables_screen_mode(self):
        s = set_screen_source(self.folder, "Display 1")
        self.assertTrue(s["screen_mode"])
        self.assertEqual(s["screen_source"], "Display 1")
        with self.assertRaises(ValueError):
            set_screen_source(self.folder, "")


class TestDevices(Base):
    def test_detect_returns_lists(self):
        d = loom_clone.detect_devices()
        self.assertIn("microphones", d)
        self.assertIn("cameras", d)
        self.assertIsInstance(d["microphones"], list)

    def test_register_and_select_device(self):
        register_device(self.folder, "microphone", "USB Mic")
        register_device(self.folder, "camera", "Webcam HD")
        devices = list_devices(self.folder)
        self.assertIn("USB Mic", devices["microphones"])
        self.assertIn("Webcam HD", devices["cameras"])
        s = select_device(self.folder, "microphone", "USB Mic")
        self.assertEqual(s["microphone"], "USB Mic")

    def test_select_unknown_device_rejected(self):
        with self.assertRaises(ValueError):
            select_device(self.folder, "microphone", "No Such Mic")

    def test_register_bad_kind_rejected(self):
        with self.assertRaises(ValueError):
            register_device(self.folder, "speaker", "X")

    def test_register_deduplicates(self):
        register_device(self.folder, "camera", "Cam")
        register_device(self.folder, "camera", "Cam")
        self.assertEqual(list_devices(self.folder)["cameras"].count("Cam"), 1)


class TestLifecycle(Base):
    def test_create_lists_and_loads(self):
        meta = self.make_rec(title="Demo", notes="hello")
        self.assertEqual(meta["status"], "created")
        self.assertEqual(meta["title"], "Demo")
        self.assertTrue(os.path.isfile(os.path.join(self.folder, meta["id"] + ".loomdata")))
        self.assertEqual(len(list_recordings(self.folder)), 1)
        self.assertEqual(load_recording(self.folder, meta["id"])["notes"], "hello")

    def test_unknown_recording_raises_keyerror(self):
        with self.assertRaises(KeyError):
            load_recording(self.folder, "rec-nope")

    def test_start_stop_duration(self):
        meta = self.make_rec()
        started = start_recording(self.folder, meta["id"])
        self.assertEqual(started["status"], "recording")
        stopped = stop_recording(self.folder, meta["id"])
        self.assertEqual(stopped["status"], "completed")
        self.assertIsNotNone(stopped["duration_seconds"])
        self.assertGreaterEqual(stopped["duration_seconds"], 0)

    def test_double_start_and_stop_without_start_rejected(self):
        meta = self.make_rec()
        start_recording(self.folder, meta["id"])
        with self.assertRaises(ValueError):
            start_recording(self.folder, meta["id"])
        with self.assertRaises(ValueError):
            stop_recording(self.folder, self.make_rec()["id"])

    def test_stop_completed_rejected(self):
        meta = self.make_rec()
        start_recording(self.folder, meta["id"])
        stop_recording(self.folder, meta["id"])
        with self.assertRaises(ValueError):
            stop_recording(self.folder, meta["id"])

    def test_start_snapshots_current_settings(self):
        register_device(self.folder, "microphone", "USB Mic")
        select_device(self.folder, "microphone", "USB Mic")
        toggle(self.folder, "mic")
        meta = start_recording(self.folder, self.make_rec()["id"])
        self.assertEqual(meta["microphone"], "USB Mic")
        self.assertTrue(meta["mic_muted"])

    def test_list_newest_first(self):
        a = self.make_rec(title="first")
        b = self.make_rec(title="second")
        ids = [m["id"] for m in list_recordings(self.folder)]
        self.assertEqual(ids[0], b["id"])
        self.assertEqual(ids[1], a["id"])

    def test_settings_and_shares_files_not_listed_as_recordings(self):
        self.make_rec()
        ids = [m["id"] for m in list_recordings(self.folder)]
        self.assertEqual(len(ids), 1)


class TestChunks(Base):
    def _recorded(self):
        meta = self.make_rec()
        start_recording(self.folder, meta["id"])
        upload_chunk(self.folder, meta["id"], 0, b"AAAA")
        upload_chunk(self.folder, meta["id"], 1, b"BBBB")
        upload_chunk(self.folder, meta["id"], 2, b"CC")
        stop_recording(self.folder, meta["id"])
        return meta["id"]

    def test_chunks_concatenate_and_hash(self):
        rec_id = self._recorded()
        self.assertEqual(read_media(self.folder, rec_id), b"AAAABBBBCC")
        meta = load_recording(self.folder, rec_id)
        self.assertEqual(meta["chunks"], 3)
        self.assertEqual(meta["bytes"], 10)
        self.assertEqual(len(meta["sha256"]), 64)

    def test_out_of_order_chunk_rejected(self):
        meta = self.make_rec()
        upload_chunk(self.folder, meta["id"], 0, b"X")
        with self.assertRaises(ValueError):
            upload_chunk(self.folder, meta["id"], 2, b"Y")
        with self.assertRaises(ValueError):
            upload_chunk(self.folder, meta["id"], 0, b"Y")

    def test_chunk_to_unknown_recording_rejected(self):
        with self.assertRaises(KeyError):
            upload_chunk(self.folder, "rec-nope", 0, b"X")

    def test_non_bytes_chunk_rejected(self):
        meta = self.make_rec()
        with self.assertRaises(TypeError):
            upload_chunk(self.folder, meta["id"], 0, "not-bytes")


class TestTrimAndShare(Base):
    def _recorded(self):
        meta = self.make_rec(title="Full")
        start_recording(self.folder, meta["id"])
        for i, chunk in enumerate([b"1111", b"2222", b"3333", b"4444"]):
            upload_chunk(self.folder, meta["id"], i, chunk)
        stop_recording(self.folder, meta["id"])
        return meta["id"]

    def test_trim_middle_chunks(self):
        rec_id = self._recorded()
        trimmed = trim_recording(self.folder, rec_id, 1, 3)
        self.assertEqual(trimmed["trimmed_from"], rec_id)
        self.assertEqual(trimmed["trim_chunks"], [1, 3])
        self.assertEqual(trimmed["chunks"], 2)
        self.assertEqual(read_media(self.folder, trimmed["id"]), b"22223333")
        self.assertEqual(trimmed["status"], "completed")

    def test_trim_invalid_ranges_rejected(self):
        rec_id = self._recorded()
        for start, end in [(2, 2), (3, 1), (-1, 2), (0, 5), (4, 5)]:
            with self.assertRaises(ValueError):
                trim_recording(self.folder, rec_id, start, end)

    def test_share_resolve_and_revoke(self):
        rec_id = self._recorded()
        token = create_share(self.folder, rec_id)
        self.assertTrue(token)
        self.assertEqual(resolve_share(self.folder, token)["id"], rec_id)
        self.assertTrue(revoke_share(self.folder, token))
        with self.assertRaises(KeyError):
            resolve_share(self.folder, token)

    def test_share_unknown_recording_rejected(self):
        with self.assertRaises(KeyError):
            create_share(self.folder, "rec-nope")

    def test_revoke_unknown_token_rejected(self):
        with self.assertRaises(KeyError):
            revoke_share(self.folder, "nope")


class TestServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self.tmp.name, "recs")
        self.server = make_server(self.folder, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def req(self, method, path, body=None, headers=None):
        request = urllib.request.Request(self.url(path), method=method,
                                         data=body, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_home_page_lists_folder(self):
        status, body = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Loom Clone", body)
        self.assertIn(b"Recordings folder", body)

    def test_full_api_flow(self):
        status, body = self.req("POST", "/api/recordings",
                                json.dumps({"title": "API Demo"}).encode(),
                                {"Content-Type": "application/json"})
        self.assertEqual(status, 201)
        rec_id = json.loads(body)["id"]
        status, _ = self.req("POST", "/api/recordings/%s/start" % rec_id, b"")
        self.assertEqual(status, 200)
        status, body = self.req("POST", "/api/recordings/%s/chunks" % rec_id,
                                b"hello ", {"X-Chunk-Index": "0"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["chunks"], 1)
        status, _ = self.req("POST", "/api/recordings/%s/chunks" % rec_id,
                             b"world", {"X-Chunk-Index": "1"})
        self.assertEqual(status, 200)
        status, _ = self.req("POST", "/api/recordings/%s/stop" % rec_id, b"")
        self.assertEqual(status, 200)
        status, body = self.req("GET", "/api/recordings/%s/download" % rec_id)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"hello world")
        status, body = self.req("GET", "/api/recordings")
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)), 1)
        status, body = self.req("POST", "/api/recordings/%s/share" % rec_id, b"")
        self.assertEqual(status, 200)
        token = json.loads(body)["token"]
        status, body = self.req("GET", "/s/" + token)
        self.assertEqual(status, 200)
        self.assertIn(b"Shared recording", body)

    def test_api_out_of_order_chunk_is_400(self):
        _, body = self.req("POST", "/api/recordings",
                           json.dumps({"title": "X"}).encode(),
                           {"Content-Type": "application/json"})
        rec_id = json.loads(body)["id"]
        status, _ = self.req("POST", "/api/recordings/%s/chunks" % rec_id,
                             b"Y", {"X-Chunk-Index": "3"})
        self.assertEqual(status, 400)

    def test_api_unknown_recording_is_404(self):
        status, _ = self.req("GET", "/api/recordings/rec-nope")
        self.assertEqual(status, 404)
        status, _ = self.req("GET", "/s/badtoken")
        self.assertEqual(status, 404)

    def test_api_trim_and_devices_and_settings(self):
        _, body = self.req("POST", "/api/recordings",
                           json.dumps({"title": "T"}).encode(),
                           {"Content-Type": "application/json"})
        rec_id = json.loads(body)["id"]
        for i in (0, 1):
            self.req("POST", "/api/recordings/%s/chunks" % rec_id,
                     b"ab", {"X-Chunk-Index": str(i)})
        status, body = self.req("POST", "/api/recordings/%s/trim" % rec_id,
                                json.dumps({"start_chunk": 1, "end_chunk": 2}).encode(),
                                {"Content-Type": "application/json"})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["bytes"], 2)
        status, body = self.req("GET", "/api/devices")
        self.assertEqual(status, 200)
        self.assertIn("cameras", json.loads(body))
        status, body = self.req("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertIn("mic_muted", json.loads(body))
        status, body = self.req("POST", "/api/settings/toggle",
                                json.dumps({"what": "mic"}).encode(),
                                {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["mic_muted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
