# git-client — DESIGN

## Assumptions (stated before coding, per ponytail rules)
- Python 3 standard library only. No subprocess calls to system
  git anywhere in `git_client.py` — system git is used solely as
  a test oracle in `tests/`, never by the implementation.
- One file, `git_client.py`, CLI + importable library functions.
  `main(argv)` returns an exit code; `if __name__ == "__main__"`
  calls `sys.exit(main())`.
- Repositories are local, non-bare, working-tree repos. The repo
  is found by walking up from the current directory looking for
  a `.git` directory (the same rule real git uses, minus
  worktrees, submodules, and `.git` files).
- Default branch is `master`, as in the page's examples (real
  git's default is now often `main`; the page consistently uses
  `master`, so `master` is kept).
- Author/committer identity: `GIT_AUTHOR_NAME` /
  `GIT_AUTHOR_EMAIL` (and the `GIT_COMMITTER_*` equivalents),
  else `[user] name/email` from `.git/config`, else
  `ccgit <ccgit@example.com>`. Timestamps are "now", unless
  `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` hold a unix
  timestamp (used by tests for reproducibility). Timezone is the
  local offset, formatted `±HHMM`.
- Only regular files, executables, and symlinks are tracked.
  Symlinks store their target as blob content with mode `120000`;
  directory traversal does not follow symlinked directories.
- No `.gitignore` handling, no hooks execution, no merge, no
  reflog, no packfiles (loose objects only), no fsck. The page
  does not require any of these for steps 1–5, and adding them
  would violate "minimum code, nothing speculative".

## Object store
- `write_object(type, data)`: SHA-1 of `"<type> <len>\0" + data`,
  zlib-compressed into `objects/<sha[:2]>/<sha[2:]>`, never
  overwriting an existing object (same SHA ⇒ same content).
- `read_object(sha)`: decompress, split the header at the first
  NUL, verify `"<type> <len>"` matches the payload length.
- Blob: raw file bytes. Tree: binary entries
  `"<mode> <name>\0<20-byte sha>"`, mode `100644` / `100755` /
  `120000` for files, `40000` for trees. Commit: text header
  lines `tree`, `parent` (zero or more), `author`, `committer`,
  a blank line, then the message (a trailing newline is added
  if the message lacks one, matching real git).

## Trees
`build_tree(entries)` groups index entries by directory and
recurses. Tree entries are sorted by name, with directories
sorted as if their name had a trailing `/` (git's rule), so a
directory `a/` sorts before a file `a.txt` but after a file `a`.
`flatten_tree(sha)` reverses this for `log`/`status`/`checkout`.

## Index (version 2)
Layout: `DIRC`, version 2, entry count; then per entry
ctime-sec, ctime-nsec, mtime-sec, mtime-nsec, dev, ino, mode,
uid, gid, size (ten 4-byte big-endian words), 20-byte blob SHA,
2-byte flags (name length, capped at `0xFFF`), the name, and
NUL padding to a multiple of 8 bytes from the entry start
(at least one NUL); then a 20-byte SHA-1 trailer over everything
before it. Entries are sorted by name bytes.
Reading tolerates what real git may have written after an
oracle run: extension blocks between the last entry and the
trailer are skipped by signature+length, and the v3 extended
flag (an extra flags word) is consumed if set. The trailer
checksum is verified on read.

## Commands and their core loops
- `init`: refuse if `<dir>/.git` already exists (or, with no
  argument, if the current directory is already inside a repo's
  root — checked via `<cwd>/.git`); otherwise create the layout
  from SPEC.md step 1 and print the success line.
- `add`: for each path, resolve files (a directory is walked),
  hash + write the blob, then rebuild the whole index from the
  old entries with the new/updated ones merged in (simplest
  correct rewrite; the index is small in this challenge's scope).
- `status`: three maps — worktree hashes (hashed, not read
  through the object store), index entries, HEAD-tree blobs —
  diffed pairwise as specified in SPEC.md step 3.
- `commit`: tree from the index; if it equals the HEAD tree
  (or the index is empty with no parent), refuse; else write
  the commit, update the branch ref (or HEAD, if detached).
- `diff`: for each changed path, `difflib.unified_diff` over
  split lines (kept with endings; a missing trailing newline is
  reported as `\ No newline at end of file`, as in real git).
  Short SHAs are the first 7 hex chars of the two blob SHAs.
- `checkout`: `-- <path>` restores one blob over the worktree
  file; a commit-ish restores every blob in that commit's tree,
  removes files tracked in the old index but absent from the
  new tree, rewrites the index from the new tree, and updates
  HEAD (detached SHA, or the branch ref when a branch name was
  given).
- `log`: follow first parents from HEAD until a commit has no
  parent or cannot be read; dates are rendered from the author
  timestamp + timezone, e.g. `Wed Sep  6 19:36:00 2023 +0000`
  (day space-padded, as in real git).

## Divergences from the page (honest list)
1. Step 6 (`push` to GitHub over HTTPS with a personal access
   token, smart-HTTP upload-pack protocol) is NOT implemented.
   Reason: it needs network access and a real GitHub account /
   token, which this offline build cannot and should not invent;
   implementing the pack protocol half-way and claiming a push
   would be faking the step. `push` exits non-zero with a plain
   explanation. Everything in steps 1–5 is implemented.
2. Default branch `master` (page's examples) rather than the
   modern git default `main`.
3. `hooks/` ships empty instead of git's sample hooks, and
   `info/exclude` ships with comment lines only; neither affects
   `git status` / `git log` compatibility.
4. Extra commands (`hash-object`, `cat-file`, `log`,
   `checkout`) are not separate page steps; they are the page's
   own vocabulary (it names `hash-object` and `update-index`,
   and shows `git log` output as the commit check) plus the
   `checkout` the task brief asks for, implemented minimally.
5. No `.gitignore`, merge, or packfile support (see Assumptions).
