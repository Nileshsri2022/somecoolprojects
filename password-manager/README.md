# password-manager — Build Your Own Password Manager

Coding Challenges, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A command-line password manager: create a vault protected by a
master password, sign in, and add / fetch / list / delete
password records. One vault is one `<name>.ccv` file.

```sh
python3 manager.py
python3 manager.py --dir ~/vaults
```

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

Example session (prompts follow the challenge page):

```
1
Please provide a name for the vault: cctest
Please enter a master password:
Please confirm the master password:
New vault created and saved as: cctest.ccv
2
Enter vault name: cctest
Enter password for the cctest vault:
Thank you, you are now signed in.
3
Please enter the record name: cc test record
Please enter the username: john
Please enter the password:
4
Please enter the record name: cc test record
For cc test record
The username: is john
The password is: secretpassword
```

Passwords are masked on a terminal (`getpass`); piped stdin
falls back to plain input so scripted sessions work.

## Security — read this before trusting it

**NOT production-grade.** The challenge page recommends AES-256,
but Python's standard library has no AES, so this build uses
PBKDF2-HMAC-SHA256 key derivation plus an HMAC-based stream
cipher with an HMAC authentication tag (wrong passwords and
tampered files are rejected before any decryption). See
`docs/DESIGN.md` for the full honest construction and its limits.
Do not store real passwords in it.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use synthetic entries in temporary directories only, never
real credentials. They cover the challenge steps (create, sign
in, add, fetch), list/delete, wrong-password and tamper
rejection, no-plaintext-on-disk, and full CLI menu sessions.

## Files

- `manager.py` — vault crypto, `Vault` class, interactive menu.
- `docs/SPEC.md` — challenge spec and supported operations.
- `docs/DESIGN.md` — vault format, crypto construction, limits.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_manager.py` — the test suite.
