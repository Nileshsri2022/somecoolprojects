# Dropbox — ccbox (local-only clone)

A Dropbox-like file storage and sync tool, built for the
Coding Challenges "Build Your Own Dropbox" challenge
(https://codingchallenges.fyi/challenges/challenge-dropbox):
a local server holding per-user virtual drives, plus a CLI
client that uploads, downloads, shares, and syncs folders.

**Local only.** No real Dropbox account, no cloud hosting,
no GUI/web frontend. The server is plain HTTP and must only
run on localhost or a trusted network. See `docs/SPEC.md`
for the challenge steps, deliberate divergences, and everything
not built.

## Run

No dependencies beyond Python 3 (standard library only).

```bash
# Terminal 1: server
python3 ccbox.py server --port 8765 --data-dir ./ccbox-data

# Terminal 2: account + a file
python3 ccbox.py signup --username alice --password secret
python3 ccbox.py login --username alice --password secret
# ^ prints a token; export it for the commands below
export CCBOX_TOKEN=<token-from-login>

python3 ccbox.py mkdir --path docs
python3 ccbox.py upload --local ./report.pdf --remote docs/report.pdf
python3 ccbox.py list --path docs
python3 ccbox.py download --remote docs/report.pdf --local ./report-copy.pdf
python3 ccbox.py share --path docs/report.pdf --public
python3 ccbox.py sync --local-dir ./my-folder        # one pass
python3 ccbox.py sync --local-dir ./my-folder --interval 30   # poll
```

Server URL defaults to `http://127.0.0.1:8765`, overridable
with `--server` or `CCBOX_SERVER_URL`. Tokens come from
`--token` or `CCBOX_TOKEN`. Usernames/passwords here are purely
local accounts on your own server — never a real Dropbox login.

## What it does

- Step 1: signup/login (PBKDF2 password hashes, bearer tokens)
- Step 2: nested folders, one-level and recursive listings
- Step 3: file and whole-folder upload/download
- Step 4: share links — public (no auth) or private (owner only)
- Step 5: CLI sync of a configured local folder: uploads new /
  locally-newer files, downloads remote-only / remotely-newer
  files, by SHA-256 + mtime. Deletions are never propagated
  (delete explicitly with `delete`).

## Layout

```
ccbox.py            # the whole app: server + client + sync
docs/SPEC.md        # steps, divergences, scope limits
docs/DESIGN.md      # storage layout, sync rules, security notes
docs/TEST_PLAN.md   # coverage map
tests/test_ccbox.py # unittest suite (own ephemeral-port server)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

29 tests, all passing (see report for the run). Each test starts
its own server on an ephemeral port with a fresh temp data
directory and shuts it down afterwards.
