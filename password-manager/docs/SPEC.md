# password-manager — SPEC

Coding Challenges: Build Your Own Password Manager
(https://codingchallenges.fyi/challenges/challenge-password-manager/)
Slug used: `challenge-password-manager` — fetched directly, no 404,
no slug correction needed.

## What it is

A command-line password manager. One vault = one file named
`<vault-name>.ccv` in the vault directory (current directory by
default, `--dir DIR` to change it). A vault holds records; each
record has a name (identifier), a username, and a password.

```sh
python3 manager.py
python3 manager.py --dir ~/vaults
```

## Challenge steps (from the page)

- **Step 1 — Create a vault.** The user provides a vault name and a
  master password (entered twice, must match). The vault is saved
  as `<name>.ccv`. Password entry is masked on a terminal
  (`getpass`); when stdin is piped (tests, scripts) it falls back
  to plain `input()` so scripted sessions work.
- **Step 2 — Create a password record within a vault.** Minimum
  fields: record name, username, password. Records are stored
  encrypted (see DESIGN.md for the honest construction).
- **Step 3 — Sign in to a vault.** The user names a vault and
  provides its master password; once signed in, records can be
  added and fetched without re-entering the password.
- **Step 4 — Retrieve a password record.** The user enters the
  record name; the manager prints the username and password.

## Interactive menu (page wording kept where it fits)

```
Welcome to CC Password Manager
What would you like to do?
1. Create a new password vault
2. Sign in to a password vault
3. Add a password to a vault
4. Fetch a password from a vault
5. List password records
6. Delete a password record
Quit (enter q or quit)
```

Key prompts, matching the page:

- Create: `Please provide a name for the vault: `,
  `Please enter a master password: `,
  `Please confirm the master password: `,
  then `New vault created and saved as: <name>.ccv`
- Sign in: `Enter vault name: `,
  `Enter password for the <name> vault: `,
  then `Thank you, you are now signed in.`
- Fetch: `Please enter the record name: `, then
  ```
  For <name>
  The username: is <username>
  The password is: <password>
  ```
  (the page's "The username: is ..." phrasing is reproduced verbatim)

## Supported operations

- `create <name> <master-password>` — new empty vault; fails if the
  file already exists, if the master password is empty, if the two
  confirmation entries differ, or if the vault name is not
  filename-safe (empty, `.` / `..`, or containing `/`, `\`, NUL).
- `sign in` — opens an existing vault; a wrong master password is
  rejected (the stored verifier and ciphertext tag both fail).
- `add` — adds a record to the signed-in vault and saves at once.
  Adding a record whose name already exists overwrites it.
- `fetch` — prints username and password for a record name, or
  `No such record: <name>` if absent.
- `list` — prints one record name per line, sorted, or
  `(vault is empty)`.
- `delete` — removes a record and saves at once, or reports
  `No such record: <name>`.

Add/fetch/list/delete require a signed-in vault; otherwise the
manager prints `You are not signed in to a vault.` and does
nothing. Quitting is `q` or `quit` at the menu prompt; EOF also
exits cleanly.

## Divergences / extensions (documented, not hidden)

1. **List and delete are extensions.** The page's four steps cover
   create/sign-in/add/fetch; "Going Further" suggests modify/update
   and an idle timeout. List and delete are added here because the
   task requires them; modify/update and idle timeout are NOT
   built (overwrite-via-add covers the update case minimally).
2. **Static menu.** The page's example menu grows as features are
   unlocked (step 1 shows only option 1). This build always shows
   options 1–6; options 3–6 refuse politely until signed in.
3. **Encryption is NOT AES-256.** The page recommends AES-256 or
   Twofish, but Python's standard library has no AES. The build
   uses PBKDF2-HMAC-SHA256 + an HMAC-based stream cipher with an
   HMAC authentication tag (see DESIGN.md). It is a learning
   construction, NOT production-grade AES-GCM, and must not be
   presented as such.
4. **Whole-vault encryption.** The page allows encrypting either
   the whole vault or individual fields; this build encrypts the
   whole vault payload (one JSON blob of all records).
