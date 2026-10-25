#!/usr/bin/env python3
"""Loom Clone (local core) -- screen-recording / video-messaging tool.

Python 3 standard library only. No real screen capture, camera capture,
microphone capture, video encoding, or cloud hosting is implemented:
this machine has no guaranteed capture hardware or codec toolchain, and
the challenge allows a web or desktop app, so this build implements the
working local core honestly:

* a home page served locally (folder selection, device selection,
  mic/camera toggles, screen mode, recording list, playback download,
  share links),
* recording-session metadata (start/stop, duration, devices, toggles,
  screen source, notes),
* chunked upload of recording bytes to the local server, stored as one
  concatenated ``.loomdata`` file per recording (raw uploaded bytes, NOT
  a playable MP4/WebM -- see SPEC.md),
* listing, download/playback-by-download, share links, and chunk-range
  trimming of stored recordings.

Usage:
    python3 loom_clone.py serve [--folder DIR] [--port PORT] [--host HOST]
    python3 loom_clone.py devices [--folder DIR]
    python3 loom_clone.py list [--folder DIR]
    python3 loom_clone.py info ID [--folder DIR]
    python3 loom_clone.py share ID [--folder DIR]
    python3 loom_clone.py trim ID START_CHUNK END_CHUNK [--folder DIR]

The server stores everything under the recordings folder:
``<folder>/<id>.loomdata`` (media bytes) and ``<folder>/<id>.json``
(metadata). ``<folder>/settings.json`` holds folder/device/toggle
choices. Share tokens live in ``<folder>/shares.json``.
"""

import argparse
import glob
import hashlib
import html
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

VERSION = "1.0.0"


# ---------------------------------------------------------------- settings

DEFAULT_SETTINGS = {
    "microphone": None,
    "camera": None,
    "mic_muted": False,
    "camera_enabled": True,
    "screen_mode": False,
    "screen_source": None,
}


def settings_path(folder):
    return os.path.join(folder, "settings.json")


def load_settings(folder):
    """Return persisted settings merged over defaults (never raises)."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(folder), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            for key in DEFAULT_SETTINGS:
                if key in data:
                    settings[key] = data[key]
            # User-registered device names are not a default setting,
            # but must survive a load or registration silently vanishes.
            if isinstance(data.get("custom_devices"), dict):
                settings["custom_devices"] = data["custom_devices"]
    except (OSError, ValueError):
        pass
    return settings


def save_settings(folder, settings):
    os.makedirs(folder, exist_ok=True)
    with open(settings_path(folder), "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, sort_keys=True)


def set_folder(folder):
    """Validate/select a recordings folder (Step 1). Creates it if needed."""
    if not folder:
        raise ValueError("folder must not be empty")
    os.makedirs(folder, exist_ok=True)
    if not os.path.isdir(folder):
        raise ValueError("folder is not a directory: %r" % folder)
    return os.path.abspath(folder)


# ---------------------------------------------------------------- devices

def detect_devices():
    """Detect capture devices present on this machine, honestly.

    On Linux, video devices are /dev/video* nodes and audio inputs are
    probed via /dev/snd (names are node paths, not friendly labels --
    stdlib has no portable device-enumeration API). On any other
    platform, or when nothing is found, the list is empty: the caller
    must not invent devices. Users/tests may register a named device
    explicitly with register_device() (e.g. a USB mic they know exists).
    Returns {"microphones": [...], "cameras": [...]}.
    """
    cameras = sorted(glob.glob("/dev/video*"))
    microphones = []
    snd = "/dev/snd"
    if os.path.isdir(snd):
        microphones = sorted(
            os.path.join(snd, name)
            for name in os.listdir(snd)
            if name.startswith("pcmC") and name.endswith("c")
        )
    return {"microphones": microphones, "cameras": cameras}


def register_device(folder, kind, name):
    """Register a user-named device (kind: microphone|camera)."""
    if kind not in ("microphone", "camera"):
        raise ValueError("kind must be 'microphone' or 'camera'")
    if not name:
        raise ValueError("device name must not be empty")
    settings = load_settings(folder)
    key = "custom_devices"
    custom = settings.get(key) or {}
    items = custom.get(kind + "s", [])
    if name not in items:
        items.append(name)
    custom[kind + "s"] = items
    settings[key] = custom
    save_settings(folder, settings)
    return settings


def list_devices(folder):
    """Detected devices plus any user-registered names, de-duplicated."""
    detected = detect_devices()
    settings = load_settings(folder)
    custom = settings.get("custom_devices") or {}
    out = {}
    for kind in ("microphones", "cameras"):
        seen, merged = set(), []
        for name in detected[kind] + list(custom.get(kind, [])):
            if name not in seen:
                seen.add(name)
                merged.append(name)
        out[kind] = merged
    return out


def select_device(folder, kind, name):
    """Select a microphone/camera; must be a known (detected/registered) device."""
    if kind not in ("microphone", "camera"):
        raise ValueError("kind must be 'microphone' or 'camera'")
    known = list_devices(folder)["microphones" if kind == "microphone" else "cameras"]
    if name not in known:
        raise ValueError("unknown %s device: %r (known: %s)" % (kind, name, known))
    settings = load_settings(folder)
    settings[kind] = name
    save_settings(folder, settings)
    return settings


def toggle(folder, what):
    """Toggle mic mute / camera enable / screen mode. Returns settings."""
    settings = load_settings(folder)
    mapping = {"mic": "mic_muted", "camera": "camera_enabled", "screen": "screen_mode"}
    if what not in mapping:
        raise ValueError("toggle must be one of: mic, camera, screen")
    settings[mapping[what]] = not settings[mapping[what]]
    save_settings(folder, settings)
    return settings


def set_screen_source(folder, source):
    if not source:
        raise ValueError("screen source must not be empty")
    settings = load_settings(folder)
    settings["screen_mode"] = True
    settings["screen_source"] = source
    save_settings(folder, settings)
    return settings


# ------------------------------------------------------------- recordings

def _recording_id():
    return "rec-%d-%s" % (int(time.time()), secrets.token_hex(4))


def _meta_path(folder, rec_id):
    return os.path.join(folder, rec_id + ".json")


def _media_path(folder, rec_id):
    return os.path.join(folder, rec_id + ".loomdata")


def create_recording(folder, title=None, notes=None):
    """Create a recording entry (not yet started). Returns its metadata."""
    folder = set_folder(folder)
    settings = load_settings(folder)
    rec_id = _recording_id()
    meta = {
        "id": rec_id,
        "title": title or rec_id,
        "notes": notes or "",
        "status": "created",
        "created_at": time.time(),
        "started_at": None,
        "stopped_at": None,
        "duration_seconds": None,
        "microphone": settings["microphone"],
        "camera": settings["camera"],
        "mic_muted": settings["mic_muted"],
        "camera_enabled": settings["camera_enabled"],
        "screen_mode": settings["screen_mode"],
        "screen_source": settings["screen_source"],
        "chunks": 0,
        "bytes": 0,
        "sha256": None,
        "media_file": rec_id + ".loomdata",
        "trimmed_from": None,
        "trim_chunks": None,
    }
    with open(_meta_path(folder, rec_id), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    # Empty media file so list/download work even before any chunk lands.
    open(_media_path(folder, rec_id), "wb").close()
    return meta


def load_recording(folder, rec_id):
    path = _meta_path(folder, rec_id)
    if not os.path.isfile(path):
        raise KeyError("unknown recording: %r" % rec_id)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_recording(folder, meta):
    with open(_meta_path(folder, meta["id"]), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    return meta


def list_recordings(folder):
    """All recordings in folder, newest first."""
    folder = set_folder(folder)
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        name = os.path.basename(path)
        if name in ("settings.json", "shares.json"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            if isinstance(meta, dict) and "id" in meta:
                out.append(meta)
        except (OSError, ValueError):
            continue
    out.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    return out


def start_recording(folder, rec_id):
    meta = load_recording(folder, rec_id)
    if meta["status"] == "recording":
        raise ValueError("recording %s is already recording" % rec_id)
    if meta["status"] == "completed":
        raise ValueError("recording %s is already completed" % rec_id)
    # Snapshot current device/toggle choices at start time.
    settings = load_settings(folder)
    for key in ("microphone", "camera", "mic_muted", "camera_enabled",
                "screen_mode", "screen_source"):
        meta[key] = settings[key]
    meta["status"] = "recording"
    meta["started_at"] = time.time()
    meta["stopped_at"] = None
    meta["duration_seconds"] = None
    return save_recording(folder, meta)


def stop_recording(folder, rec_id):
    meta = load_recording(folder, rec_id)
    if meta["status"] != "recording":
        raise ValueError("recording %s is not recording (status=%s)"
                         % (rec_id, meta["status"]))
    meta["status"] = "completed"
    meta["stopped_at"] = time.time()
    meta["duration_seconds"] = round(meta["stopped_at"] - meta["started_at"], 3)
    return save_recording(folder, meta)


def upload_chunk(folder, rec_id, index, data):
    """Append one chunk. Chunks must arrive in order (0, 1, 2, ...).

    Returns updated metadata. Rejects out-of-order chunks instead of
    silently reordering, so a broken uploader is visible, not hidden.
    """
    meta = load_recording(folder, rec_id)
    if index != meta["chunks"]:
        raise ValueError("expected chunk %d, got %d" % (meta["chunks"], index))
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("chunk data must be bytes")
    with open(_media_path(folder, rec_id), "ab") as fh:
        fh.write(bytes(data))
    meta["chunks"] += 1
    meta["bytes"] += len(data)
    digest = hashlib.sha256()
    with open(_media_path(folder, rec_id), "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    meta["sha256"] = digest.hexdigest()
    return save_recording(folder, meta)


def read_media(folder, rec_id):
    load_recording(folder, rec_id)  # raises KeyError if unknown
    with open(_media_path(folder, rec_id), "rb") as fh:
        return fh.read()


def trim_recording(folder, rec_id, start_chunk, end_chunk):
    """Create a new recording from chunks [start_chunk, end_chunk).

    Chunk boundaries are the only honest trim points for the raw
    concatenated-chunk format: there is no codec, so time-based trimming
    would be fake precision. The new recording keeps a trimmed_from link.
    """
    meta = load_recording(folder, rec_id)
    if not (0 <= start_chunk < end_chunk <= meta["chunks"]):
        raise ValueError("trim range [%d, %d) invalid for %d chunks"
                         % (start_chunk, end_chunk, meta["chunks"]))
    # Chunk sizes are not stored separately, so chunk-boundary trimming
    # requires equal-sized chunks; refuse rather than guess boundaries.
    # Uploaded chunks in this implementation are tracked only by count,
    # so we store per-chunk sizes in a sidecar at upload time.
    sizes = _chunk_sizes(folder, rec_id)
    if len(sizes) != meta["chunks"]:
        raise ValueError("cannot trim: chunk size index is incomplete")
    data = read_media(folder, rec_id)
    start_byte = sum(sizes[:start_chunk])
    end_byte = sum(sizes[:end_chunk])
    new = create_recording(folder, title=meta["title"] + " (trimmed)",
                           notes=meta.get("notes", ""))
    new.update({
        "status": "completed",
        "trimmed_from": rec_id,
        "trim_chunks": [start_chunk, end_chunk],
        "microphone": meta["microphone"], "camera": meta["camera"],
        "mic_muted": meta["mic_muted"],
        "camera_enabled": meta["camera_enabled"],
        "screen_mode": meta["screen_mode"],
        "screen_source": meta["screen_source"],
    })
    with open(_media_path(folder, new["id"]), "wb") as fh:
        fh.write(data[start_byte:end_byte])
    new["chunks"] = end_chunk - start_chunk
    new["bytes"] = end_byte - start_byte
    new["sha256"] = hashlib.sha256(data[start_byte:end_byte]).hexdigest()
    _write_chunk_sizes(folder, new["id"], sizes[start_chunk:end_chunk])
    return save_recording(folder, new)


def _sizes_path(folder, rec_id):
    return os.path.join(folder, rec_id + ".chunks.json")


def _chunk_sizes(folder, rec_id):
    try:
        with open(_sizes_path(folder, rec_id), "r", encoding="utf-8") as fh:
            sizes = json.load(fh)
        return sizes if isinstance(sizes, list) else []
    except (OSError, ValueError):
        return []


def _write_chunk_sizes(folder, rec_id, sizes):
    with open(_sizes_path(folder, rec_id), "w", encoding="utf-8") as fh:
        json.dump(sizes, fh)


# Patch upload_chunk to also record chunk sizes (kept separate so the
# function above stays readable; see _upload_chunk_sizes below).
_orig_upload_chunk = upload_chunk


def upload_chunk(folder, rec_id, index, data):  # noqa: F811 -- intentional
    meta = _orig_upload_chunk(folder, rec_id, index, data)
    sizes = _chunk_sizes(folder, rec_id)
    sizes.append(len(data))
    _write_chunk_sizes(folder, rec_id, sizes)
    return meta


# ------------------------------------------------------------------ shares

def _shares_path(folder):
    return os.path.join(folder, "shares.json")


def load_shares(folder):
    try:
        with open(_shares_path(folder), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def create_share(folder, rec_id):
    load_recording(folder, rec_id)  # raises KeyError if unknown
    shares = load_shares(folder)
    token = secrets.token_urlsafe(16)
    shares[token] = {"recording_id": rec_id, "created_at": time.time()}
    os.makedirs(folder, exist_ok=True)
    with open(_shares_path(folder), "w", encoding="utf-8") as fh:
        json.dump(shares, fh, indent=2, sort_keys=True)
    return token


def resolve_share(folder, token):
    shares = load_shares(folder)
    entry = shares.get(token)
    if not entry:
        raise KeyError("unknown or revoked share token")
    return load_recording(folder, entry["recording_id"])


def revoke_share(folder, token):
    shares = load_shares(folder)
    if token not in shares:
        raise KeyError("unknown share token")
    del shares[token]
    with open(_shares_path(folder), "w", encoding="utf-8") as fh:
        json.dump(shares, fh, indent=2, sort_keys=True)
    return True


# ------------------------------------------------------------------- server

def _esc(value):
    return html.escape("" if value is None else str(value))


def home_html(folder, settings, devices, recordings):
    rows = "".join(
        '<li><a href="/recordings/%s">%s</a> (%s, %d bytes, %d chunks, %s)'
        " <a href=\"/api/recordings/%s/download\">download</a></li>"
        % (_esc(m["id"]), _esc(m["title"]), _esc(m["status"]),
           m.get("bytes", 0), m.get("chunks", 0),
           _esc(m.get("screen_source") or m.get("camera") or "-"),
           _esc(m["id"]))
        for m in recordings
    ) or "<li>(no recordings yet)</li>"
    return """<!doctype html><html><head><meta charset="utf-8">
<title>Loom Clone (local)</title></head><body>
<h1>Loom Clone &mdash; local core</h1>
<p>Recordings folder: <b>%s</b></p>
<p><b>Honest scope:</b> no real screen/camera/mic capture, no video
encoding, no cloud. Uploaded chunks are stored raw as
<code>.loomdata</code>; playback here is download of those bytes.</p>
<h2>Devices</h2><p>Microphones: %s<br>Cameras: %s</p>
<p>Selected mic: %s | camera: %s | mic muted: %s | camera on: %s |
screen mode: %s | screen source: %s</p>
<h2>Recordings</h2><ul>%s</ul>
<h2>API</h2><p>POST /api/recordings (JSON title/notes) &rarr; create;
POST /api/recordings/ID/start, /stop; POST /api/recordings/ID/chunks
with X-Chunk-Index header and raw body; GET /api/recordings;
GET /api/recordings/ID/download; POST /api/recordings/ID/share;
POST /api/recordings/ID/trim (JSON start_chunk/end_chunk);
GET /s/TOKEN (shared view).</p>
</body></html>""" % (
        _esc(folder),
        _esc(", ".join(devices["microphones"]) or "(none detected)"),
        _esc(", ".join(devices["cameras"]) or "(none detected)"),
        _esc(settings["microphone"]), _esc(settings["camera"]),
        settings["mic_muted"], settings["camera_enabled"],
        settings["screen_mode"], _esc(settings["screen_source"]), rows)


class Handler(BaseHTTPRequestHandler):
    folder = "."
    protocol_version = "HTTP/1.1"

    # -- helpers ------------------------------------------------------
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body, status=200):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ValueError("request body is not valid JSON")
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    def log_message(self, *args):  # keep test output clean
        pass

    # -- routing ------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/":
                self._html(home_html(self.folder, load_settings(self.folder),
                                     list_devices(self.folder),
                                     list_recordings(self.folder)))
            elif path == "/api/recordings":
                self._json(list_recordings(self.folder))
            elif path == "/api/devices":
                self._json(list_devices(self.folder))
            elif path == "/api/settings":
                self._json(load_settings(self.folder))
            elif path.startswith("/api/recordings/") and path.endswith("/download"):
                rec_id = path[len("/api/recordings/"):-len("/download")].strip("/")
                data = read_media(self.folder, rec_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path.startswith("/api/recordings/"):
                rec_id = path[len("/api/recordings/"):].strip("/")
                self._json(load_recording(self.folder, rec_id))
            elif path.startswith("/recordings/"):
                rec_id = path[len("/recordings/"):].strip("/")
                meta = load_recording(self.folder, rec_id)
                self._html("<h1>%s</h1><p>Status: %s, %d bytes, %d chunks. "
                           '<a href="/api/recordings/%s/download">Download '
                           ".loomdata</a></p>" % (_esc(meta["title"]),
                           _esc(meta["status"]), meta.get("bytes", 0),
                           meta.get("chunks", 0), _esc(rec_id)))
            elif path.startswith("/s/"):
                meta = resolve_share(self.folder, path[len("/s/"):].strip("/"))
                self._html("<h1>Shared recording: %s</h1><p>Status: %s, "
                           "%d bytes. <a href=\"/api/recordings/%s/download\">"
                           "Download</a></p>" % (_esc(meta["title"]),
                           _esc(meta["status"]), meta.get("bytes", 0),
                           _esc(meta["id"])))
            else:
                self._json({"error": "not found"}, status=404)
        except KeyError as exc:
            self._json({"error": str(exc)}, status=404)
        except (ValueError, OSError) as exc:
            self._json({"error": str(exc)}, status=400)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/recordings":
                data = self._read_json()
                meta = create_recording(self.folder, data.get("title"),
                                        data.get("notes"))
                self._json(meta, status=201)
            elif path.startswith("/api/recordings/") and path.endswith("/start"):
                rec_id = path[len("/api/recordings/"):-len("/start")].strip("/")
                self._json(start_recording(self.folder, rec_id))
            elif path.startswith("/api/recordings/") and path.endswith("/stop"):
                rec_id = path[len("/api/recordings/"):-len("/stop")].strip("/")
                self._json(stop_recording(self.folder, rec_id))
            elif path.startswith("/api/recordings/") and path.endswith("/chunks"):
                rec_id = path[len("/api/recordings/"):-len("/chunks")].strip("/")
                try:
                    index = int(self.headers.get("X-Chunk-Index", ""))
                except ValueError:
                    raise ValueError("X-Chunk-Index header must be an integer")
                length = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(length) if length else b""
                self._json(upload_chunk(self.folder, rec_id, index, data))
            elif path.startswith("/api/recordings/") and path.endswith("/share"):
                rec_id = path[len("/api/recordings/"):-len("/share")].strip("/")
                token = create_share(self.folder, rec_id)
                self._json({"token": token, "url_path": "/s/" + token})
            elif path.startswith("/api/recordings/") and path.endswith("/trim"):
                rec_id = path[len("/api/recordings/"):-len("/trim")].strip("/")
                data = self._read_json()
                meta = trim_recording(self.folder, rec_id,
                                      int(data["start_chunk"]),
                                      int(data["end_chunk"]))
                self._json(meta, status=201)
            elif path == "/api/settings/toggle":
                data = self._read_json()
                self._json(toggle(self.folder, data["what"]))
            elif path == "/api/settings/screen":
                data = self._read_json()
                self._json(set_screen_source(self.folder, data["source"]))
            elif path == "/api/settings/device":
                data = self._read_json()
                self._json(select_device(self.folder, data["kind"],
                                         data["name"]))
            else:
                self._json({"error": "not found"}, status=404)
        except KeyError as exc:
            self._json({"error": str(exc)}, status=404)
        except (ValueError, TypeError, OSError) as exc:
            self._json({"error": str(exc)}, status=400)


def make_server(folder, host, port):
    folder = set_folder(folder)
    handler = type("BoundHandler", (Handler,), {"folder": folder})
    return ThreadingHTTPServer((host, port), handler)


# ---------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(prog="loom_clone")
    parser.add_argument("--folder", default="recordings",
                        help="recordings folder (default: recordings)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="serve the local home page + API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0,
                       help="0 = ephemeral port (printed on startup)")

    devices_p = sub.add_parser("devices", help="list detected + registered devices")
    list_p = sub.add_parser("list", help="list recordings")
    info = sub.add_parser("info", help="show one recording")
    info.add_argument("id")
    share = sub.add_parser("share", help="create a share link for a recording")
    share.add_argument("id")
    trim = sub.add_parser("trim", help="trim by chunk range into a new recording")
    trim.add_argument("id")
    trim.add_argument("start_chunk", type=int)
    trim.add_argument("end_chunk", type=int)
    # --folder must also work after the subcommand (the documented form
    # is `loom_clone.py serve --folder DIR`); argparse only accepts a
    # global option before the subcommand otherwise.
    for subparser in (serve, devices_p, list_p, info, share, trim):
        # SUPPRESS (not None): a plain default would overwrite a
        # --folder given before the subcommand with the default.
        subparser.add_argument("--folder", default=argparse.SUPPRESS)

    args = parser.parse_args(argv)
    folder = set_folder(args.folder)
    if args.cmd == "serve":
        server = make_server(folder, args.host, args.port)
        print("Loom Clone (local core) serving %s at http://%s:%d/"
              % (folder, args.host, server.server_address[1]))
        print("Press Ctrl-C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.cmd == "devices":
        print(json.dumps(list_devices(folder), indent=2))
    elif args.cmd == "list":
        print(json.dumps(list_recordings(folder), indent=2))
    elif args.cmd == "info":
        print(json.dumps(load_recording(folder, args.id), indent=2))
    elif args.cmd == "share":
        token = create_share(folder, args.id)
        print("/s/" + token)
    elif args.cmd == "trim":
        meta = trim_recording(folder, args.id, args.start_chunk, args.end_chunk)
        print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
