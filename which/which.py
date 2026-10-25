#!/usr/bin/env python3
"""which — locate a program file in the user's path.

Build Your Own Which (codingchallenges.fyi, challenge-which):
search PATH directories in order for each given program name,
printing the first match (or every match with -a). A candidate
matches only if it is a regular file and executable. Names
containing '/' are checked as given, without searching PATH.

Exit status: 0 if every program was found, 1 if any program
was not found (or none was given), 2 on an unknown option.
Python 3 standard library only.
"""

import os
import sys


class UsageError(Exception):
    """An unknown option character, e.g. 'x' in '-x'."""

    def __init__(self, option):
        super().__init__(option)
        self.option = option


def parse_args(argv):
    """Split argv into (all_matches, silent, programs).

    Flag parsing stops at the first non-flag argument or at
    '--'; everything after that is a program name, even if
    it starts with '-'. A lone '-' is a program name.
    """
    all_matches = False
    silent = False
    programs = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            programs.extend(argv[i + 1:])
            break
        if len(arg) > 1 and arg.startswith("-"):
            for ch in arg[1:]:
                if ch == "a":
                    all_matches = True
                elif ch == "s":
                    silent = True
                else:
                    raise UsageError(ch)
            i += 1
            continue
        programs.extend(argv[i:])
        break
    return all_matches, silent, programs


def _qualifies(path):
    """True if path is a regular file (symlinks followed) and executable."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def find_matches(name, path_dirs, all_matches):
    """Return the matching paths for one program name, in order."""
    if "/" in name:
        # Relative or absolute path: checked as given, PATH ignored.
        return [name] if _qualifies(name) else []
    matches = []
    for directory in path_dirs:
        # An empty PATH element means the current directory,
        # printed as './name' (matching system which).
        candidate = os.path.join(directory if directory else ".", name)
        if _qualifies(candidate):
            matches.append(candidate)
            if not all_matches:
                break
    return matches


def main(argv, environ=None):
    """Run which; argv excludes the program name. Returns exit status."""
    if environ is None:
        environ = os.environ
    try:
        all_matches, silent, programs = parse_args(argv)
    except UsageError as exc:
        # Same split as system which: usage to stdout, error to stderr.
        print("Usage: %s [-as] args" % sys.argv[0])
        print("Illegal option -%s" % exc.option, file=sys.stderr)
        return 2
    if "PATH" in environ:
        path_dirs = environ["PATH"].split(os.pathsep)
    else:
        path_dirs = []
    found_all = True
    for program in programs:
        matches = find_matches(program, path_dirs, all_matches)
        if not matches:
            found_all = False
        elif not silent:
            for match in matches:
                print(match)
    if not programs:
        return 1
    return 0 if found_all else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
