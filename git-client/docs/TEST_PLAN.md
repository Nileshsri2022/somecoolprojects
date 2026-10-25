# git-client — TEST PLAN

All tests live in `tests/test_git_client.py` (unittest) and run
from the project directory with:

```sh
python3 -m unittest discover -s tests -v
```

Every test repo is created in a `tempfile.TemporaryDirectory`;
no test ever touches the somecoolprojects working copy's own
git state or any real repository. System git is used only as an
oracle (tests skip the oracle assertions when `git` is absent
from PATH); the implementation never shells out to it.

## Cases
1. init — creates `.git` with HEAD (`ref: refs/heads/master`),
   config, description, hooks/, info/exclude, objects/, refs/;
   prints `initialized empty repository: <dir>`; a second init
   in the same directory fails.
2. init — oracle: real `git status` succeeds in the new repo
   and reports branch master with no commits yet.
3. hash-object — blob SHA equals SHA-1 of `blob <len>\0<data>`
   for a known file, and equals real `git hash-object` output;
   without `-w` no object file is created, with `-w` it is.
4. add — adds a file to the index; re-reading the index shows
   the right name, blob SHA, and mode; oracle: real `git status`
   shows the file as a staged new file.
5. add — nested path (`sub/dir/file.txt`) is stored with its
   full relative path; adding a directory walks it recursively.
6. status — untracked file listed under "Untracked files";
   staged file under "Changes to be committed"; modified file
   under "Changes not staged for commit"; file deleted from the
   tree under "Changes not staged for commit" as deleted;
   a fully clean tree reports clean.
7. commit — first commit: object readable via `cat-file -p`,
   ref `refs/heads/master` points at it, oracle: real
   `git log --format=%s` prints the message; second commit's
   parent is the first commit.
8. commit — committing with nothing staged fails.
9. commit — nested files produce nested trees readable by
   `cat-file -p` and by the oracle `git log` / `git ls-tree`.
10. log — prints newest first, with `commit <sha>`, `Author:`,
    `Date:`, and both messages, in order.
11. cat-file — `-t` returns blob/tree/commit; `-p` on a blob
    prints its content, on a tree prints `mode type sha\tname`
    lines, on a commit prints the raw commit text; unknown SHA
    fails.
12. diff — after modifying a staged file, output has the
    `diff --git`, `index <short>..<short>`, `--- a/`, `+++ b/`
    headers and the added line; `--cached` shows a staged
    change; untracked files are not shown.
13. checkout — after two commits, checking out the first
    commit's SHA restores the old file content and detaches
    HEAD; checking out the second restores the new content.
14. checkout -- — restoring one modified file from the index
    reverts it to the staged content.
15. push — exits non-zero and reports that push is not
    implemented (documented divergence, not a silent stub).
16. object round-trip — `write_object`/`read_object` for blob,
    tree, and commit data, including that writing the same
    object twice is a no-op and a corrupt object is rejected.

## Success criteria
All tests pass (`OK`, zero failures/errors). Oracle assertions
must pass wherever `git` is present; a failure there means the
on-disk format is wrong, not that the oracle is optional.
