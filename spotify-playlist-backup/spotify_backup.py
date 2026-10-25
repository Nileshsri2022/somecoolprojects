#!/usr/bin/env python3
"""Spotify Playlist Backup Service (CLI).

Backs up Spotify playlists to versioned JSON files on disk, and can
export them as CSV (optionally zipped), diff two backup versions, and
produce (or execute, with a user token) a restore plan.

Python 3 standard library only. No real Spotify credentials are stored
here; credentials come from the environment (SPOTIFY_CLIENT_ID,
SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, SPOTIFY_ACCESS_TOKEN) or
from command-line flags. Tests point the client at a local fake server
via --api-base / --auth-base; the defaults are the real Spotify
endpoints and live use was NOT tested in this build (see README).
"""

import argparse
import base64
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

DEFAULT_API_BASE = "https://api.spotify.com"
DEFAULT_AUTH_BASE = "https://accounts.spotify.com"
CSV_FIELDS = ["position", "track_name", "artists", "album", "track_id",
              "uri", "duration_ms", "added_at"]


class SpotifyApiError(Exception):
    """An HTTP/API failure, carrying status and (truncated) body."""

    def __init__(self, status, body=""):
        self.status = status
        self.body = (body or "")[:500]
        super().__init__(f"Spotify API error {status}: {self.body}")


def parse_playlist_id(text):
    """Accept a bare id, a Spotify URI, or an open.spotify.com URL."""
    if not text or not text.strip():
        raise ValueError("empty playlist reference")
    text = text.strip()
    if text.startswith("spotify:playlist:"):
        pid = text.split(":", 2)[2]
        if pid:
            return pid
        raise ValueError(f"invalid playlist URI: {text!r}")
    if "open.spotify.com/playlist/" in text:
        parsed = urllib.parse.urlparse(text)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "playlist" and parts[1]:
            return parts[1]
        raise ValueError(f"invalid playlist URL: {text!r}")
    if "/" in text or ":" in text or " " in text:
        raise ValueError(f"unrecognised playlist reference: {text!r}")
    return text


def _utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_track_item(item):
    """Normalise one playlist-track item into a backup track record.

    Returns None for items with no usable track object (e.g. a track
    removed from Spotify), so such entries are skipped, not faked.
    """
    track = (item or {}).get("track")
    if not isinstance(track, dict) or not track.get("id"):
        return None
    artists = [a.get("name", "") for a in track.get("artists") or []
               if isinstance(a, dict)]
    album = track.get("album") or {}
    return {
        "track_id": track.get("id"),
        "uri": track.get("uri", ""),
        "track_name": track.get("name", ""),
        "artists": artists,
        "album": album.get("name", "") if isinstance(album, dict) else "",
        "duration_ms": track.get("duration_ms"),
        "added_at": item.get("added_at", ""),
        "added_by": ((item.get("added_by") or {}).get("id", "")
                     if isinstance(item.get("added_by"), dict) else ""),
    }


def track_key(track):
    """Stable identity for diffing: URI, else id, else name key."""
    return track.get("uri") or track.get("track_id") or (
        ";".join(track.get("artists") or []) + " - "
        + track.get("track_name", ""))


class SpotifyClient:
    """Minimal Spotify Web API client (pluggable base URLs)."""

    def __init__(self, api_base=DEFAULT_API_BASE,
                 auth_base=DEFAULT_AUTH_BASE, client_id=None,
                 client_secret=None, access_token=None):
        self.api_base = api_base.rstrip("/")
        self.auth_base = auth_base.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token

    # -- low-level -------------------------------------------------
    def _request(self, method, url, data=None, headers=None, form=False):
        req_headers = dict(headers or {})
        if self.access_token and "Authorization" not in req_headers:
            req_headers["Authorization"] = f"Bearer {self.access_token}"
        body = None
        if data is not None:
            if form:
                body = urllib.parse.urlencode(data).encode()
                req_headers["Content-Type"] = \
                    "application/x-www-form-urlencoded"
            else:
                body = json.dumps(data).encode()
                req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=req_headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise SpotifyApiError(
                exc.code, exc.read().decode("utf-8", "replace"))
        except urllib.error.URLError as exc:
            raise SpotifyApiError(0, str(exc.reason))
        return json.loads(raw) if raw.strip() else {}

    def _get(self, path, params=None):
        url = self.api_base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return self._request("GET", url)

    def _post_token(self, form_data):
        if not self.client_id or not self.client_secret:
            raise ValueError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET "
                             "are required for token requests")
        creds = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()).decode()
        url = self.auth_base + "/api/token"
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(form_data).encode(),
            headers={"Authorization": f"Basic {creds}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise SpotifyApiError(
                exc.code, exc.read().decode("utf-8", "replace"))
        token = payload.get("access_token")
        if not token:
            raise SpotifyApiError(0, "token response had no access_token")
        self.access_token = token
        return payload

    # -- auth ------------------------------------------------------
    def get_client_credentials_token(self):
        """Step 1: client-credentials flow for public playlists."""
        return self._post_token({"grant_type": "client_credentials"})

    def exchange_code(self, code, redirect_uri):
        """Step 5 helper: Authorization Code grant (not live-tested)."""
        return self._post_token({"grant_type": "authorization_code",
                                 "code": code,
                                 "redirect_uri": redirect_uri})

    @staticmethod
    def build_auth_url(client_id, redirect_uri, scope="",
                       state="", auth_base=DEFAULT_AUTH_BASE):
        """Step 5 helper: URL the user visits to log in as themselves."""
        params = {"response_type": "code", "client_id": client_id,
                  "redirect_uri": redirect_uri}
        if scope:
            params["scope"] = scope
        if state:
            params["state"] = state
        return (auth_base.rstrip("/") + "/authorize?" +
                urllib.parse.urlencode(params))

    # -- playlists -------------------------------------------------
    def get_playlist(self, playlist_id):
        return self._get(f"/v1/playlists/{playlist_id}")

    def get_playlist_tracks(self, playlist_id, page_size=100):
        """All track items, following pagination via `next`."""
        items, offset = [], 0
        while True:
            page = self._get(f"/v1/playlists/{playlist_id}/tracks",
                             {"limit": page_size, "offset": offset})
            items.extend(page.get("items") or [])
            if not page.get("next"):
                break
            offset += len(page.get("items") or []) or page_size
        return items

    def fetch_playlist(self, playlist_id):
        """Metadata + normalised tracks for one playlist."""
        meta = self.get_playlist(playlist_id)
        tracks = [t for t in (normalize_track_item(i)
                              for i in self.get_playlist_tracks(playlist_id))
                  if t is not None]
        owner = meta.get("owner") or {}
        return {
            "playlist_id": meta.get("id", playlist_id),
            "name": meta.get("name", ""),
            "description": meta.get("description", ""),
            "owner_id": owner.get("id", "") if isinstance(owner, dict) else "",
            "public": meta.get("public"),
            "snapshot_id": meta.get("snapshot_id", ""),
            "track_count": len(tracks),
            "tracks": tracks,
        }

    def get_user_playlists(self, page_size=50):
        """All of the current user's playlists (Step 5), paginated."""
        playlists, offset = [], 0
        while True:
            page = self._get("/v1/me/playlists",
                             {"limit": page_size, "offset": offset})
            playlists.extend(page.get("items") or [])
            if not page.get("next"):
                break
            offset += len(page.get("items") or []) or page_size
        return playlists

    def create_playlist(self, user_id, name, description="", public=False):
        return self._request(
            "POST", self.api_base + f"/v1/users/{user_id}/playlists",
            {"name": name, "description": description, "public": public})

    def add_tracks(self, playlist_id, uris):
        """Add URIs in batches of 100 (the API's per-request limit)."""
        added = 0
        for start in range(0, len(uris), 100):
            self._request("POST",
                          self.api_base +
                          f"/v1/playlists/{playlist_id}/tracks",
                          {"uris": uris[start:start + 100]})
            added += len(uris[start:start + 100])
        return added


# -- backup store ----------------------------------------------------

def backup_folder(backup_dir, playlist_id):
    return os.path.join(backup_dir, playlist_id)


def _scan_versions(folder):
    versions = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if (name.startswith("v") and name.endswith(".json")
                    and name[1:-5].isdigit()):
                versions.append(int(name[1:-5]))
    return sorted(versions)


def _read_manifest(folder):
    path = os.path.join(folder, "manifest.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def next_version(folder):
    manifest = _read_manifest(folder)
    if manifest and manifest.get("versions"):
        nums = [v["version"] for v in manifest["versions"]
                if isinstance(v.get("version"), int)]
        if nums:
            return max(nums) + 1
    scanned = _scan_versions(folder)
    return (max(scanned) + 1) if scanned else 1


def write_backup(backup_dir, backup):
    """Write a versioned backup; returns (version, file path)."""
    folder = backup_folder(backup_dir, backup["playlist_id"])
    os.makedirs(folder, exist_ok=True)
    version = next_version(folder)
    record = dict(backup)
    record["version"] = version
    record["backed_up_at"] = _utcnow()
    fname = f"v{version:03d}.json"
    path = os.path.join(folder, fname)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    manifest = _read_manifest(folder) or {
        "playlist_id": backup["playlist_id"], "versions": []}
    manifest["versions"] = [v for v in manifest.get("versions", [])
                            if v.get("version") != version]
    manifest["versions"].append({
        "version": version, "file": fname,
        "backed_up_at": record["backed_up_at"],
        "tracks": record["track_count"]})
    manifest["versions"].sort(key=lambda v: v["version"])
    with open(os.path.join(folder, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    with open(os.path.join(folder, "latest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    return version, path


def load_backup(backup_dir, playlist_id, version=None):
    folder = backup_folder(backup_dir, playlist_id)
    if version is None:
        path = os.path.join(folder, "latest.json")
    else:
        path = os.path.join(folder, f"v{int(version):03d}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"no backup found: playlist {playlist_id!r} "
            f"version {version or 'latest'} in {backup_dir!r}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_backups(backup_dir):
    """One row per backed-up playlist: id, versions, latest info."""
    rows = []
    if not os.path.isdir(backup_dir):
        return rows
    for pid in sorted(os.listdir(backup_dir)):
        folder = os.path.join(backup_dir, pid)
        if not os.path.isdir(folder):
            continue
        manifest = _read_manifest(folder)
        versions = ([v["version"] for v in manifest["versions"]]
                    if manifest and manifest.get("versions")
                    else _scan_versions(folder))
        latest = None
        if os.path.exists(os.path.join(folder, "latest.json")):
            try:
                latest = load_backup(backup_dir, pid)
            except (json.JSONDecodeError, OSError):
                latest = None
        rows.append({"playlist_id": pid, "versions": sorted(versions),
                     "name": latest.get("name", "") if latest else "",
                     "tracks": latest.get("track_count") if latest else None})
    return rows


# -- diff / export / restore ------------------------------------------

def diff_backups(old, new):
    old_by_key = {track_key(t): t for t in old.get("tracks", [])}
    new_by_key = {track_key(t): t for t in new.get("tracks", [])}
    return {
        "added": [new_by_key[k] for k in new_by_key if k not in old_by_key],
        "removed": [old_by_key[k] for k in old_by_key if k not in new_by_key],
        "unchanged": [new_by_key[k] for k in new_by_key if k in old_by_key],
    }


def csv_text(backup):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for pos, track in enumerate(backup.get("tracks", []), start=1):
        writer.writerow({
            "position": pos,
            "track_name": track.get("track_name", ""),
            "artists": "; ".join(track.get("artists") or []),
            "album": track.get("album", ""),
            "track_id": track.get("track_id", ""),
            "uri": track.get("uri", ""),
            "duration_ms": track.get("duration_ms", ""),
            "added_at": track.get("added_at", ""),
        })
    return buf.getvalue()


def export_csv(backup, path):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(csv_text(backup))
    return path


def export_zip_csv(backup, path):
    csv_name = f"{backup['playlist_id']}.csv"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_name, csv_text(backup))
    return path


def restore_plan(backup):
    return {
        "playlist_id": backup["playlist_id"],
        "playlist_name": backup.get("name", ""),
        "track_count": backup.get("track_count", len(backup["tracks"])),
        "tracks": [{"uri": t.get("uri", ""),
                    "track_name": t.get("track_name", ""),
                    "artists": t.get("artists") or []}
                   for t in backup.get("tracks", [])],
    }


# -- CLI ---------------------------------------------------------------

def _client(args):
    return SpotifyClient(
        api_base=args.api_base, auth_base=args.auth_base,
        client_id=args.client_id or os.environ.get("SPOTIFY_CLIENT_ID"),
        client_secret=args.client_secret or
        os.environ.get("SPOTIFY_CLIENT_SECRET"),
        access_token=args.access_token or
        os.environ.get("SPOTIFY_ACCESS_TOKEN"))


def _require_token(client, why):
    if not client.access_token:
        if client.client_id and client.client_secret:
            client.get_client_credentials_token()
        else:
            raise ValueError(
                f"{why}: set SPOTIFY_ACCESS_TOKEN or SPOTIFY_CLIENT_ID / "
                "SPOTIFY_CLIENT_SECRET")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="spotify_backup",
        description="Back up Spotify playlists to versioned JSON on disk.")
    parser.add_argument("--backup-dir", default="./backups")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--auth-base", default=DEFAULT_AUTH_BASE)
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--client-secret", default=None)
    parser.add_argument("--access-token", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("auth-url", help="Print the user-login URL (Step 5)")
    p.add_argument("--redirect-uri", required=True)
    p.add_argument("--scope", default="playlist-read-private "
                   "playlist-modify-public playlist-modify-private")
    p.add_argument("--state", default="")

    sub.add_parser("token", help="Fetch a client-credentials token (Step 1)")

    p = sub.add_parser("backup", help="Back up one playlist")
    p.add_argument("playlist")

    sub.add_parser("backup-all",
                   help="Back up all of the current user's playlists")

    sub.add_parser("list", help="List backups on disk")

    p = sub.add_parser("show", help="Show a backup's track listing")
    p.add_argument("playlist")
    p.add_argument("--version", type=int, default=None)

    p = sub.add_parser("diff", help="Diff two backup versions")
    p.add_argument("playlist")
    p.add_argument("old_version", type=int)
    p.add_argument("new_version", type=int)

    p = sub.add_parser("export", help="Export a backup as CSV (Step 4)")
    p.add_argument("playlist")
    p.add_argument("--version", type=int, default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--zip", action="store_true",
                   help="write a zipped CSV instead")

    p = sub.add_parser("restore-plan",
                       help="Write the track list needed to recreate a "
                       "playlist, from a backup on disk")
    p.add_argument("playlist")
    p.add_argument("--version", type=int, default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--format", choices=["json", "csv"], default="json")

    p = sub.add_parser("restore",
                       help="Create a playlist on Spotify from a backup")
    p.add_argument("playlist")
    p.add_argument("--version", type=int, default=None)
    p.add_argument("--user-id", required=True)
    p.add_argument("--name", default=None)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = _client(args)
    try:
        if args.command == "auth-url":
            cid = client.client_id or os.environ.get("SPOTIFY_CLIENT_ID")
            if not cid:
                raise ValueError("auth-url needs SPOTIFY_CLIENT_ID "
                                 "(or --client-id)")
            print(SpotifyClient.build_auth_url(
                cid, args.redirect_uri, scope=args.scope,
                state=args.state, auth_base=args.auth_base))
            return 0

        if args.command == "token":
            payload = client.get_client_credentials_token()
            print(f"token_type={payload.get('token_type')} "
                  f"expires_in={payload.get('expires_in')}")
            return 0

        if args.command == "backup":
            _require_token(client, "backup")
            pid = parse_playlist_id(args.playlist)
            version, path = write_backup(
                args.backup_dir, client.fetch_playlist(pid))
            print(f"backed up {pid} as version {version} -> {path}")
            return 0

        if args.command == "backup-all":
            if not client.access_token:
                raise ValueError(
                    "backup-all needs a user token: set "
                    "SPOTIFY_ACCESS_TOKEN (log in via auth-url first)")
            count = 0
            for summary in client.get_user_playlists():
                pid = summary.get("id")
                if not pid:
                    continue
                version, _ = write_backup(
                    args.backup_dir, client.fetch_playlist(pid))
                print(f"backed up {pid} as version {version}")
                count += 1
            print(f"backed up {count} playlist(s)")
            return 0

        if args.command == "list":
            rows = list_backups(args.backup_dir)
            if not rows:
                print("no backups yet")
                return 0
            for row in rows:
                print(f"{row['playlist_id']}  versions={row['versions']}  "
                      f"name={row['name']!r} tracks={row['tracks']}")
            return 0

        if args.command == "show":
            backup = load_backup(args.backup_dir,
                                 parse_playlist_id(args.playlist),
                                 args.version)
            print(f"{backup.get('name', '')} "
                  f"({backup['playlist_id']}, "
                  f"version {backup.get('version')}, "
                  f"{backup.get('track_count')} tracks)")
            for pos, track in enumerate(backup.get("tracks", []), start=1):
                print(f"{pos}. {'; '.join(track.get('artists') or [])} - "
                      f"{track.get('track_name', '')} "
                      f"[{track.get('album', '')}]")
            return 0

        if args.command == "diff":
            pid = parse_playlist_id(args.playlist)
            old = load_backup(args.backup_dir, pid, args.old_version)
            new = load_backup(args.backup_dir, pid, args.new_version)
            result = diff_backups(old, new)
            for label in ("added", "removed", "unchanged"):
                print(f"{label} ({len(result[label])}):")
                for track in result[label]:
                    print(f"  {'; '.join(track.get('artists') or [])} - "
                          f"{track.get('track_name', '')}")
            return 0

        if args.command == "export":
            backup = load_backup(args.backup_dir,
                                 parse_playlist_id(args.playlist),
                                 args.version)
            version = backup.get("version")
            if args.zip:
                out = args.out or f"{backup['playlist_id']}-v{version}.zip"
                export_zip_csv(backup, out)
            else:
                out = args.out or f"{backup['playlist_id']}-v{version}.csv"
                export_csv(backup, out)
            print(f"exported -> {out}")
            return 0

        if args.command == "restore-plan":
            backup = load_backup(args.backup_dir,
                                 parse_playlist_id(args.playlist),
                                 args.version)
            plan = restore_plan(backup)
            if args.format == "csv":
                out = args.out or f"{backup['playlist_id']}-restore.csv"
                with open(out, "w", encoding="utf-8", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["position", "track_name", "artists",
                                     "uri"])
                    for pos, track in enumerate(plan["tracks"], start=1):
                        writer.writerow([pos, track["track_name"],
                                         "; ".join(track["artists"]),
                                         track["uri"]])
            else:
                out = args.out or f"{backup['playlist_id']}-restore.json"
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(plan, fh, indent=2)
            print(f"restore plan -> {out} ({plan['track_count']} tracks)")
            return 0

        if args.command == "restore":
            if not client.access_token:
                raise ValueError(
                    "restore needs a user token: set SPOTIFY_ACCESS_TOKEN")
            backup = load_backup(args.backup_dir,
                                 parse_playlist_id(args.playlist),
                                 args.version)
            created = client.create_playlist(
                args.user_id, args.name or backup.get("name", "Restored"),
                description=f"Restored from backup of "
                f"{backup['playlist_id']}", public=False)
            uris = [t["uri"] for t in backup.get("tracks", []) if t.get("uri")]
            added = client.add_tracks(created["id"], uris)
            print(f"created playlist {created['id']} with {added} track(s)")
            return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (SpotifyApiError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
