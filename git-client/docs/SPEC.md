# git-client — SPEC

Source: Coding Challenges, "Build Your Own Git".
Page: https://codingchallenges.fyi/challenges/challenge-git/
Slug used: `challenge-git` (first guess, no 404, no correction needed).

The page asks for a git client (`ccgit` in its examples) that can
create a repository, add files, and push to GitHub. Its steps:

## Step 0 — setup
Read the Git Internals documentation (objects, index, refs) before
coding. Done via the page itself; no extra dependency is introduced.

## Step 1 — `init`
Create a `.git` directory containing:
- `HEAD` — a reference to the current branch (`ref: refs/heads/master`).
- `config` — repository configuration (format version 0, filemode,
  not bare).
- `description` — the default unnamed-repository text.
- `hooks/` — an (empty) directory for hooks.
- `info/` — a directory containing an `excludes` file.
- `objects/` — the object store (plus `objects/info/` and
  `objects/pack/` for compatibility with real git).
- `refs/` — a directory (`refs/heads/`, `refs/tags/`).

Refuse (non-zero exit, message on stderr) if a repository is
already initialised in the target directory. On success print
`initialized empty repository: <path>`, matching the page's example.

## Step 2 — `add` (hash-object + update-index)
For each given file (or directory, walked recursively):
compute the blob SHA-1 exactly as git does — SHA-1 of
`blob <len>\0<content>` — write the zlib-deflated object to
`objects/xx/<38 hex chars>` if absent, and record the file in the
index (`.git/index`, format version 2, SHA-1 trailer), with the
file's stat data (ctime/mtime/dev/ino/mode/uid/gid/size) and the
blob SHA. The result must be readable by real git: after
`ccgit add hello.txt`, real `git status` must show the file as a
staged new file (this is the page's own acceptance test).

## Step 3 — `status`
Walk the working tree (excluding `.git`), compare each file with
the index, and compare the index with the HEAD tree:
- in index but not in HEAD tree → staged "new file";
  in both with a different blob → staged "modified";
  in HEAD tree but not in index → staged "deleted".
- in index but missing from the tree → unstaged "deleted";
  in index with a different worktree hash → unstaged "modified".
- in the tree but not in the index → "untracked".
Branch name comes from `.git/HEAD`. Output sections mirror the
page's example (`Changes to be committed:`, `Changes not staged
for commit:`, `Untracked files:`); with no changes at all it
reports a clean tree.

## Step 4 — `commit`
Build tree objects from the index (nested directories become
nested trees, entries sorted git-style), write a commit object
`tree / parent(s) / author / committer / message`, point
`refs/heads/<branch>` at it (or detach HEAD if HEAD was
detached), and report `committed to <branch>: <full sha>`,
matching the page's example. Refuse when there is nothing staged
(index tree identical to the HEAD tree). Real `git log` must be
able to read the commit (the page's acceptance test).

## Step 5 — `diff`
Unified diff, git-style headers, for files that changed:
- default: working tree vs index (unstaged changes), as in the
  page's example (`diff --git a/<f> b/<f>`, `index <short>..<short>`,
  `--- a/<f>`, `+++ b/<f>`, `@@` hunks).
- `--cached`: index vs HEAD tree (staged changes).
Untracked files are not shown (as in real git). The page allows
using a diff library; Python's stdlib `difflib` is used.

## Step 6 — `push`
NOT IMPLEMENTED (see DESIGN.md, "Divergences"). The CLI accepts
`push` only to report, on stderr with a non-zero exit, that
pushing is not implemented and why. It never pretends to push.

## Extra commands (not on the page, needed to make the above usable)
- `hash-object [-w] <file>` — print a blob SHA-1, writing the
  object only with `-w` (mirrors real git's split of concerns).
- `cat-file -p|-t|-s <sha>` — print an object's content, type,
  or size. For trees, `-p` prints `mode type sha\tname` lines.
- `log` — walk HEAD parents, printing `commit <sha>`,
  `Author:`, `Date:`, and the indented message, newest first.
- `checkout -- <path>` — restore one file from the index blob.
- `checkout <commit-ish>` — restore the whole tree of a commit
  (branch name, full/short SHA, or `HEAD`), rewrite the index,
  and detach HEAD at that commit (or move to the branch if a
  branch name was given).
