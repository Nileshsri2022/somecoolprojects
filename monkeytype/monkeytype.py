#!/usr/bin/env python3
"""Monkeytype clone — terminal typing test.

Python 3 standard library only. See README.md and docs/SPEC.md.

Usage:
    python3 monkeytype.py test [--count N] [--prompt TEXT] [--no-curses]
    python3 monkeytype.py history [--user NAME]
    python3 monkeytype.py leaderboard
    python3 monkeytype.py create-user USERNAME
    python3 monkeytype.py login USERNAME
    python3 monkeytype.py logout
    python3 monkeytype.py reset-password USERNAME
    python3 monkeytype.py delete-user USERNAME
    python3 monkeytype.py            # interactive menu

Global option (all subcommands): --data-dir DIR
Default data dir: ~/.local/share/monkeytype/
"""

import argparse
import getpass
import hashlib
import hmac
import json
import os
import random
import secrets
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------- words

COMMON_WORDS = """the be of and a to in he have it that for they with as not on she at by
this we you do but from or which one would all will there say who make when can
more if no man out other so what time up go about than into could state only
new year some take come these know see use get like then first any work now may
such give over think most even find day also after way many must look before
great back through long where much should well people down own just because
good each those feel seem how high too place little world very still nation
hand old life tell write become here show house both between need mean call
develop under last right move thing general school never same another begin
while number part turn real leave might want point form off child few small
since against ask late home interest large person end open public follow during
present without again hold govern around possible head consider word program
problem however lead system set order eye plan run keep face fact group play
stand increase early course change help line city put close case force meet
once water upon round learn month side tree test above book carry light night
young important until children side feet car mile night walk white sea began
grow took river four carry state once book hear stop without second later miss
idea enough eat face watch far indian really almost let above girl sometimes
mountains cut young talk soon list song leave family body music color stand sun
questions fish area mark dog horse birds problem complete room knew since ever
piece told usually didnt friends easy heard order red door sure become top ship
across today during short better best however low hours black products happened
whole measure remember early waves reached listen wind rock space covered fast
several hold himself toward five step morning passed vowel true hundred against
pattern numeral table north slowly money map farm pulled draw voice seen cold
cried plan notice south sing war ground fall king town ill unit figure certain
field travel wood fire upon done english road halt ten fly gave box finally
wait correct oh quickly person became shown minutes strong verb stars front feel
fact inches street decided contain course surface produce building ocean class
note nothing rest carefully scientists inside wheels stay green known island
week less machine base ago stood plane system behind ran round boat game force
bring understand warm common bring explain dry though language shape deep
thousands yes clear equation yet government filled heat full hot check object
am among mother ride""".split()

# Deduplicate defensively while preserving order.
COMMON_WORDS = list(dict.fromkeys(COMMON_WORDS))

DEFAULT_COUNT = 25
MIN_COUNT = 10
MAX_COUNT = 50
LEADERBOARD_LIMIT = 50
MIN_LEADERBOARD_ACCURACY = 90.0
_PBKDF2_ITERATIONS = 200_000


def default_data_dir():
    return os.path.join(os.path.expanduser("~"), ".local", "share", "monkeytype")


# ------------------------------------------------------------ pure logic

def generate_words(pool=None, count=DEFAULT_COUNT, rng=None):
    """Return `count` random words from `pool` (default COMMON_WORDS)."""
    pool = list(pool if pool is not None else COMMON_WORDS)
    if not pool:
        raise ValueError("word pool is empty")
    if count < 1:
        raise ValueError("count must be at least 1")
    rng = rng if rng is not None else random
    if count <= len(pool):
        return rng.sample(pool, count)
    return rng.choices(pool, k=count)


def make_prompt(words):
    return " ".join(words)


def char_results(target, typed):
    """Per-position correctness: True only for exact same-position match."""
    return [
        i < len(target) and typed[i] == target[i]
        for i in range(len(typed))
    ]


def score_test(target, typed, elapsed_seconds):
    """Score a finished test per the challenge definitions.

    WPM = (correct / 5) / minutes; raw WPM = (typed / 5) / minutes;
    accuracy = 100 * correct / typed. Zero/negative elapsed -> 0 WPM.
    """
    results = char_results(target, typed)
    correct = sum(1 for r in results if r)
    total = len(typed)
    minutes = elapsed_seconds / 60.0 if elapsed_seconds > 0 else 0.0
    wpm = (correct / 5.0) / minutes if minutes > 0 else 0.0
    raw_wpm = (total / 5.0) / minutes if minutes > 0 else 0.0
    accuracy = (100.0 * correct / total) if total > 0 else 0.0
    return {
        "wpm": round(wpm, 2),
        "raw_wpm": round(raw_wpm, 2),
        "accuracy": round(accuracy, 2),
        "correct": correct,
        "total": total,
        "incorrect": total - correct,
        "elapsed_seconds": round(float(elapsed_seconds), 4),
    }


def summarise_results(results):
    if not results:
        return {"count": 0, "best_wpm": 0.0, "avg_wpm": 0.0, "avg_accuracy": 0.0}
    wpms = [r["wpm"] for r in results]
    accs = [r["accuracy"] for r in results]
    return {
        "count": len(results),
        "best_wpm": round(max(wpms), 2),
        "avg_wpm": round(sum(wpms) / len(wpms), 2),
        "avg_accuracy": round(sum(accs) / len(accs), 2),
    }


def format_result(result):
    return (
        "\n=== Results ===\n"
        f"WPM:        {result['wpm']}\n"
        f"Raw WPM:    {result['raw_wpm']}\n"
        f"Accuracy:   {result['accuracy']}%\n"
        f"Characters: {result['correct']} correct / "
        f"{result['total']} typed "
        f"({result['incorrect']} incorrect)\n"
        f"Time:       {result['elapsed_seconds']}s\n"
    )


# ------------------------------------------------------- accounts/store

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, hash_hex):
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    _, digest_hex = hash_password(password, salt)
    return hmac.compare_digest(digest_hex, hash_hex)


class UserStore:
    """Local JSON account + result store."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "users.json")
        self._data = None

    def _load(self):
        if self._data is not None:
            return self._data
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {"users": {}}
        return self._data

    def _save(self):
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._load(), f, indent=2)
        os.replace(tmp, self.path)

    def create_user(self, username, password):
        if not username or not username.strip():
            raise ValueError("username must not be empty")
        if not password:
            raise ValueError("password must not be empty")
        data = self._load()
        if username in data["users"]:
            raise ValueError(f"user '{username}' already exists")
        salt, digest = hash_password(password)
        data["users"][username] = {
            "salt": salt, "password_hash": digest, "results": [],
        }
        self._save()

    def verify_user(self, username, password):
        user = self._load()["users"].get(username)
        if user is None:
            return False
        return verify_password(password, user["salt"], user["password_hash"])

    def user_exists(self, username):
        return username in self._load()["users"]

    def reset_password(self, username, old_password, new_password):
        data = self._load()
        user = data["users"].get(username)
        if user is None:
            raise ValueError(f"unknown user '{username}'")
        if not verify_password(old_password, user["salt"], user["password_hash"]):
            raise ValueError("old password is incorrect")
        if not new_password:
            raise ValueError("new password must not be empty")
        salt, digest = hash_password(new_password)
        user["salt"], user["password_hash"] = salt, digest
        self._save()

    def delete_user(self, username):
        data = self._load()
        if username not in data["users"]:
            raise ValueError(f"unknown user '{username}'")
        del data["users"][username]
        self._save()

    def add_result(self, username, result):
        data = self._load()
        user = data["users"].get(username)
        if user is None:
            raise ValueError(f"unknown user '{username}'")
        user["results"].append(result)
        self._save()

    def results_for(self, username):
        user = self._load()["users"].get(username)
        return list(user["results"]) if user else []

    def leaderboard(self, limit=LEADERBOARD_LIMIT):
        entries = []
        for username, user in self._load()["users"].items():
            for r in user["results"]:
                if r.get("accuracy", 0.0) >= MIN_LEADERBOARD_ACCURACY:
                    entry = dict(r)
                    entry["username"] = username
                    entries.append(entry)
        entries.sort(key=lambda e: (-e["wpm"], e.get("date", "")))
        return entries[:limit]


def session_path(data_dir):
    return os.path.join(data_dir, "session.json")


def current_user(data_dir):
    path = session_path(data_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("username")
    except (json.JSONDecodeError, OSError):
        return None


def set_current_user(data_dir, username):
    os.makedirs(data_dir, exist_ok=True)
    with open(session_path(data_dir), "w", encoding="utf-8") as f:
        json.dump({"username": username}, f)


def clear_current_user(data_dir):
    path = session_path(data_dir)
    if os.path.exists(path):
        os.remove(path)


# ------------------------------------------------------------ terminal UI

def run_line_test(prompt):
    print("\nType the following text, then press Enter:\n")
    print(prompt)
    print()
    start = time.monotonic()
    typed = input("> ")
    elapsed = time.monotonic() - start
    return typed, elapsed


def run_curses_test(prompt):
    """Curses typing UI. Returns (typed, elapsed) or None if abandoned."""
    import curses

    outcome = {}

    def _main(stdscr):
        curses.curs_set(1)
        try:
            curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)
        except curses.error:
            pass
        typed = []
        start = None
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            # Draw char by char, wrapping at terminal width.
            y, x = 0, 0
            for i, ch in enumerate(prompt):
                if x >= width - 1:
                    y += 1
                    x = 0
                if y >= height - 3:
                    break
                if i < len(typed):
                    colour = curses.color_pair(1) if typed[i] == ch \
                        else curses.color_pair(2)
                else:
                    colour = curses.A_DIM
                if i == len(typed):
                    colour |= curses.A_REVERSE
                try:
                    stdscr.addch(y, x, ch, colour)
                except curses.error:
                    pass
                x += 1
            correct = sum(1 for i, c in enumerate(typed)
                          if i < len(prompt) and c == prompt[i])
            footer = (f"{correct}/{len(typed)} correct  "
                      f"(Esc to quit, Backspace to correct)")
            try:
                stdscr.addstr(height - 1, 0, footer[: width - 1])
            except curses.error:
                pass
            stdscr.refresh()
            key = stdscr.getch()
            if key == 27:  # Esc
                outcome["result"] = None
                return
            if key in (curses.KEY_BACKSPACE, 127, 8):
                if typed:
                    typed.pop()
                continue
            if 32 <= key <= 126:
                if start is None:
                    start = time.monotonic()
                typed.append(chr(key))
                if len(typed) >= len(prompt):
                    outcome["result"] = (
                        "".join(typed), time.monotonic() - start)
                    return

    curses.wrapper(_main)
    return outcome.get("result")


def do_test(store, data_dir, count, prompt_text, no_curses):
    prompt = prompt_text or make_prompt(
        generate_words(count=count))
    print(f"\nTest: {len(prompt)} characters. "
          "Timer starts on your first keystroke.")
    result = None
    if no_curses:
        typed, elapsed = run_line_test(prompt)
        result = (typed, elapsed)
    else:
        try:
            result = run_curses_test(prompt)
        except Exception as exc:  # curses unavailable / no TTY
            print(f"(curses unavailable: {exc}; using line input)")
            typed, elapsed = run_line_test(prompt)
            result = (typed, elapsed)
    if result is None:
        print("Test abandoned — nothing saved.")
        return None
    typed, elapsed = result
    scored = score_test(prompt, typed, elapsed)
    scored["date"] = datetime.now(timezone.utc).isoformat()
    scored["prompt_length"] = len(prompt)
    print(format_result(scored))
    user = current_user(data_dir)
    if user and store.user_exists(user):
        store.add_result(user, scored)
        print(f"Saved to {user}'s history.")
    elif user:
        print(f"(Logged-in user '{user}' no longer exists; not saved.)")
    else:
        print("(Not logged in — log in to save results to an account.)")
    return scored


# ------------------------------------------------------------------ CLI

def build_parser():
    parser = argparse.ArgumentParser(
        description="Monkeytype clone — terminal typing test.")
    parser.add_argument("--data-dir", default=None,
                        help="data directory (default: ~/.local/share/monkeytype/)")
    sub = parser.add_subparsers(dest="command")
    # --data-dir is also accepted after the subcommand (SUPPRESS default
    # so it does not clobber the value given before the subcommand).
    for name, help_text in [
            ("test", "take a typing test"),
            ("history", "show saved results"),
            ("leaderboard", "show top 50 (accuracy >= 90%)"),
            ("create-user", "create an account"),
            ("login", "log in"),
            ("logout", "log out"),
            ("reset-password", "reset a password"),
            ("delete-user", "delete an account")]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--data-dir", default=argparse.SUPPRESS)
        if name == "test":
            p.add_argument("--count", type=int, default=DEFAULT_COUNT)
            p.add_argument("--prompt", default=None)
            p.add_argument("--no-curses", action="store_true")
        elif name == "history":
            p.add_argument("--user", default=None)
        elif name in ("create-user", "login", "reset-password",
                      "delete-user"):
            p.add_argument("username")
    return parser


def interactive_menu(store, data_dir):
    while True:
        user = current_user(data_dir)
        print("\n=== Monkeytype (terminal) ===")
        print(f"Logged in as: {user or '(nobody)'}")
        print("1. Take a typing test")
        print("2. History")
        print("3. Leaderboard")
        print("4. Create account")
        print("5. Log in")
        print("6. Log out")
        print("7. Reset password")
        print("8. Delete account")
        print("9. Quit")
        choice = input("Choose: ").strip()
        try:
            if choice == "1":
                do_test(store, data_dir, DEFAULT_COUNT, None, False)
            elif choice == "2":
                name = user or input("Username: ").strip()
                show_history(store, name)
            elif choice == "3":
                show_leaderboard(store)
            elif choice == "4":
                name = input("New username: ").strip()
                store.create_user(name, getpass.getpass("Password: "))
                print(f"Account '{name}' created.")
            elif choice == "5":
                name = input("Username: ").strip()
                if store.verify_user(name, getpass.getpass("Password: ")):
                    set_current_user(data_dir, name)
                    print(f"Logged in as {name}.")
                else:
                    print("Login failed.")
            elif choice == "6":
                clear_current_user(data_dir)
                print("Logged out.")
            elif choice == "7":
                name = input("Username: ").strip()
                store.reset_password(name, getpass.getpass("Old password: "),
                                     getpass.getpass("New password: "))
                print("Password reset.")
            elif choice == "8":
                name = input("Username to delete: ").strip()
                if input(f"Delete '{name}' and all its results? [y/N] "
                         ).strip().lower() == "y":
                    store.delete_user(name)
                    if current_user(data_dir) == name:
                        clear_current_user(data_dir)
                    print("Account deleted.")
            elif choice == "9":
                return 0
            else:
                print("Unknown choice.")
        except ValueError as exc:
            print(f"Error: {exc}")
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
    return 0


def show_history(store, username):
    if not username:
        print("No user given and nobody logged in.")
        return
    results = store.results_for(username)
    if not results:
        print(f"No results for '{username}'.")
        return
    summary = summarise_results(results)
    print(f"\nHistory for {username}: {summary['count']} tests, "
          f"best {summary['best_wpm']} WPM, "
          f"avg {summary['avg_wpm']} WPM, "
          f"avg accuracy {summary['avg_accuracy']}%")
    for r in results:
        print(f"  {r.get('date', '?')}  WPM {r['wpm']}  "
              f"raw {r['raw_wpm']}  acc {r['accuracy']}%  "
              f"{r['correct']}/{r['total']} chars")


def show_leaderboard(store):
    entries = store.leaderboard()
    if not entries:
        print("Leaderboard is empty (need results with accuracy >= 90%).")
        return
    print("\n=== Leaderboard (top 50, accuracy >= 90%) ===")
    for i, e in enumerate(entries, 1):
        print(f"{i:2}. {e['username']:<20} {e['wpm']:>7} WPM  "
              f"{e['accuracy']}%  {e.get('date', '')}")


def main(argv=None):
    args = build_parser().parse_args(argv)
    data_dir = args.data_dir or default_data_dir()
    store = UserStore(data_dir)
    if args.command is None:
        return interactive_menu(store, data_dir)
    try:
        if args.command == "test":
            if not (MIN_COUNT <= args.count <= MAX_COUNT) \
                    and args.prompt is None:
                print(f"Count must be {MIN_COUNT}-{MAX_COUNT}.")
                return 1
            do_test(store, data_dir, args.count, args.prompt, args.no_curses)
        elif args.command == "history":
            show_history(store, args.user or current_user(data_dir))
        elif args.command == "leaderboard":
            show_leaderboard(store)
        elif args.command == "create-user":
            store.create_user(args.username,
                              getpass.getpass("Password: "))
            print(f"Account '{args.username}' created.")
        elif args.command == "login":
            if store.verify_user(args.username,
                                 getpass.getpass("Password: ")):
                set_current_user(data_dir, args.username)
                print(f"Logged in as {args.username}.")
            else:
                print("Login failed.")
                return 1
        elif args.command == "logout":
            clear_current_user(data_dir)
            print("Logged out.")
        elif args.command == "reset-password":
            store.reset_password(args.username,
                                 getpass.getpass("Old password: "),
                                 getpass.getpass("New password: "))
            print("Password reset.")
        elif args.command == "delete-user":
            store.delete_user(args.username)
            if current_user(data_dir) == args.username:
                clear_current_user(data_dir)
            print("Account deleted.")
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
