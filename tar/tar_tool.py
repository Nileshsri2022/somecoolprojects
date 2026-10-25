#!/usr/bin/env python3
"""tar_tool.py — a minimal UStar tar: create, list, extract.

Python 3 standard library only. The 512-byte header logic is
written by hand; stdlib ``tarfile`` is deliberately NOT used
here (it appears only in the tests, as an oracle).

Usage:
    python3 tar_tool.py -t [-f archive]          # list (stdin if no -f)
    python3 tar_tool.py -tv [-f archive]         # list, verbose
    python3 tar_tool.py -x [-f archive]          # extract (stdin if no -f)
    python3 tar_tool.py -c [-f archive] file...  # create (stdout if no -f)

Flags may be clustered (-tf, -cf, -xf) or separate (-t -f arc).
"""

import grp
import os
import pwd
import stat
import sys
import time
from dataclasses import dataclass

BLOCK = 512
ZERO_BLOCK = b"\x00" * BLOCK


class TarError(Exception):
    """Any malformed archive, unsafe path, or I/O failure."""


def _octal(value, width):
    """Encode value as zero-padded octal ASCII + NUL, total width."""
    text = ("%0*o" % (width - 1, value)).encode("ascii")
    return text + b"\x00"


def _parse_octal(field):
    """Decode an octal field; empty / all-NUL decodes to 0."""
    text = field.split(b"\x00", 1)[0].strip()
    if not text:
        return 0
    try:
        return int(text, 8)
    except ValueError:
        raise TarError("invalid octal field %r" % (field,))


def _field(raw, offset, size):
    return raw[offset:offset + size].split(b"\x00", 1)[0]


def _compute_checksum(header):
    total = 0
    for i, byte in enumerate(header):
        if 148 <= i < 156:
            total += 0x20  # chksum field counts as spaces
        else:
            total += byte
    return total


def _split_name(name_bytes):
    """Split a long name into (prefix, name) at a '/', or raise."""
    if len(name_bytes) <= 100:
        return b"", name_bytes
    # Try every '/' split, longest prefix first that fits both parts.
    for i in range(len(name_bytes) - 1, -1, -1):
        if name_bytes[i:i + 1] != b"/":
            continue
        prefix, name = name_bytes[:i], name_bytes[i + 1:]
        if len(prefix) <= 155 and 0 < len(name) <= 100:
            return prefix, name
    raise TarError("name too long for ustar header: %r"
                   % (name_bytes.decode("utf-8", "surrogateescape"),))


@dataclass
class Header:
    name: str
    mode: int
    uid: int
    gid: int
    size: int
    mtime: int
    typeflag: str
    linkname: str
    uname: str
    gname: str


def build_header(name, mode, uid, gid, size, mtime, typeflag,
                 linkname="", uname="", gname=""):
    name_b = os.fsencode(name)
    prefix, short = _split_name(name_b)
    link_b = os.fsencode(linkname)
    if len(link_b) > 100:
        raise TarError("linkname too long: %r" % (linkname,))
    header = bytearray(BLOCK)
    header[0:len(short)] = short
    header[100:108] = _octal(mode, 8)
    header[108:116] = _octal(uid, 8)
    header[116:124] = _octal(gid, 8)
    header[124:136] = _octal(size, 12)
    header[136:148] = _octal(mtime, 12)
    header[156:157] = typeflag.encode("ascii")
    header[157:157 + len(link_b)] = link_b
    header[257:263] = b"ustar\x00"
    header[263:265] = b"00"
    uname_b = uname.encode("utf-8", "surrogateescape")[:32]
    gname_b = gname.encode("utf-8", "surrogateescape")[:32]
    header[265:265 + len(uname_b)] = uname_b
    header[297:297 + len(gname_b)] = gname_b
    header[329:337] = _octal(0, 8)
    header[337:345] = _octal(0, 8)
    header[345:345 + len(prefix)] = prefix
    checksum = _compute_checksum(bytes(header))
    header[148:156] = ("%06o\x00 " % checksum).encode("ascii")
    return bytes(header)


def parse_header(block):
    """Parse and checksum-verify one 512-byte block."""
    if len(block) != BLOCK:
        raise TarError("short header block")
    stored = _parse_octal(block[148:156])
    if _compute_checksum(block) != stored:
        raise TarError("bad header checksum")
    name = _field(block, 0, 100)
    prefix = _field(block, 345, 155)
    if prefix:
        name = prefix + b"/" + name
    typeflag = block[156:157].decode("ascii", "replace")
    return Header(
        name=os.fsdecode(name),
        mode=_parse_octal(block[100:108]),
        uid=_parse_octal(block[108:116]),
        gid=_parse_octal(block[116:124]),
        size=_parse_octal(block[124:136]),
        mtime=_parse_octal(block[136:148]),
        typeflag=typeflag,
        linkname=os.fsdecode(_field(block, 157, 100)),
        uname=os.fsdecode(_field(block, 265, 32)),
        gname=os.fsdecode(_field(block, 297, 32)),
    )


def _read_exact(stream, count):
    chunks = []
    remaining = count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if len(data) != count:
        raise TarError("truncated archive")
    return data


def iter_entries(stream):
    """Yield (Header, data_bytes) for each entry, honouring
    pax/GNU-longname entries and stopping at the zero blocks."""
    pending_name = None
    zero_seen = 0
    while True:
        block = stream.read(BLOCK)
        if not block:
            break
        if len(block) != BLOCK:
            raise TarError("truncated archive")
        if block == ZERO_BLOCK:
            zero_seen += 1
            if zero_seen >= 2:
                break
            continue
        zero_seen = 0
        header = parse_header(block)
        padded = (header.size + BLOCK - 1) // BLOCK * BLOCK
        data = _read_exact(stream, padded)[:header.size]
        if header.typeflag in ("x", "g"):
            continue  # pax extended header: not an entry
        if header.typeflag in ("L", "K"):
            pending_name = data.decode("utf-8", "surrogateescape").rstrip("\x00")
            continue
        if pending_name is not None:
            header.name = pending_name
            pending_name = None
        yield header, data


def _mode_string(mode, typeflag):
    kind = {"5": "d", "2": "l"}.get(typeflag, "-")
    bits = ""
    for shift in (6, 3, 0):
        trio = (mode >> shift) & 0o7
        bits += "r" if trio & 4 else "-"
        bits += "w" if trio & 2 else "-"
        bits += "x" if trio & 1 else "-"
    return kind + bits


def cmd_list(stream, verbose):
    out = sys.stdout
    for header, _data in iter_entries(stream):
        if verbose:
            when = time.strftime("%Y-%m-%d %H:%M",
                                 time.localtime(header.mtime))
            owner = header.uname or str(header.uid)
            group = header.gname or str(header.gid)
            out.write("%s %s/%s %8d %s %s\n" % (
                _mode_string(header.mode, header.typeflag),
                owner, group, header.size, when, header.name))
        else:
            out.write(header.name + "\n")


def _safe_dest(dest, name):
    """Resolve name inside dest; raise TarError if it escapes."""
    if os.path.isabs(name):
        raise TarError("refusing absolute path in archive: %r" % (name,))
    target = os.path.abspath(os.path.join(dest, name))
    dest_abs = os.path.abspath(dest)
    if target != dest_abs and not target.startswith(dest_abs + os.sep):
        raise TarError("refusing path escaping archive: %r" % (name,))
    return target


def _ensure_parent(target):
    parent = os.path.dirname(target)
    if parent:
        # Refuse to create through an existing symlink parent.
        parts = parent.split(os.sep)
        cur = parts[0] or os.sep
        for part in parts[1:]:
            cur = os.path.join(cur, part)
            if os.path.islink(cur):
                raise TarError("refusing to extract through symlink: %r"
                               % (cur,))
        os.makedirs(parent, exist_ok=True)


def cmd_extract(stream, dest="."):
    for header, data in iter_entries(stream):
        target = _safe_dest(dest, header.name)
        if header.typeflag == "5":
            os.makedirs(target, exist_ok=True)
        elif header.typeflag == "2":
            if os.path.isabs(header.linkname):
                raise TarError("refusing absolute symlink target: %r"
                               % (header.linkname,))
            _ensure_parent(target)
            if os.path.lexists(target):
                os.unlink(target)
            os.symlink(header.linkname, target)
            continue
        elif header.typeflag in ("0", "\x00"):
            _ensure_parent(target)
            with open(target, "wb") as fh:
                fh.write(data)
        else:
            raise TarError("unsupported typeflag %r for %r"
                           % (header.typeflag, header.name))
        try:
            os.chmod(target, header.mode & 0o7777)
        except OSError:
            pass
        try:
            os.utime(target, (header.mtime, header.mtime))
        except OSError:
            pass


def _file_info(path):
    st = os.lstat(path)
    try:
        uname = pwd.getpwuid(st.st_uid).pw_name
    except (KeyError, OverflowError):
        uname = ""
    try:
        gname = grp.getgrgid(st.st_gid).gr_name
    except (KeyError, OverflowError):
        gname = ""
    return st, uname, gname


def _write_entry(out, arcname, path):
    st, uname, gname = _file_info(path)
    mode = stat.S_IMODE(st.st_mode)
    mtime = int(st.st_mtime)
    if stat.S_ISLNK(st.st_mode):
        out.write(build_header(arcname, mode, st.st_uid, st.st_gid,
                               0, mtime, "2",
                               linkname=os.readlink(path),
                               uname=uname, gname=gname))
    elif stat.S_ISDIR(st.st_mode):
        name = arcname if arcname.endswith("/") else arcname + "/"
        out.write(build_header(name, mode, st.st_uid, st.st_gid,
                               0, mtime, "5", uname=uname, gname=gname))
        for entry in sorted(os.listdir(path)):
            _write_entry(out, name + entry, os.path.join(path, entry))
    elif stat.S_ISREG(st.st_mode):
        size = st.st_size
        out.write(build_header(arcname, mode, st.st_uid, st.st_gid,
                               size, mtime, "0", uname=uname, gname=gname))
        with open(path, "rb") as fh:
            remaining = size
            while remaining:
                chunk = fh.read(min(BLOCK, remaining))
                if not chunk:
                    raise TarError("file shrank during archiving: %r"
                                   % (path,))
                out.write(chunk)
                remaining -= len(chunk)
        pad = (-size) % BLOCK
        if pad:
            out.write(b"\x00" * pad)
    else:
        raise TarError("unsupported file type: %r" % (path,))


def cmd_create(out, paths):
    for path in paths:
        if not os.path.lexists(path):
            raise TarError("no such file or directory: %r" % (path,))
        arcname = path
        # Archive names are stored without a leading ./ when
        # the user passed one, matching system tar's display.
        if arcname.startswith("./"):
            arcname = arcname[2:]
        _write_entry(out, arcname, path)
    out.write(ZERO_BLOCK * 2)


def parse_args(argv):
    """Return (mode, archive, verbose, operands).

    mode is one of 'c', 't', 'x'. ``archive`` is None for
    stdin/stdout. Raises TarError on bad usage.
    """
    mode = None
    archive = None
    verbose = False
    operands = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            operands.extend(argv[i + 1:])
            break
        if arg.startswith("-") and arg != "-" and not operands:
            j = 1
            while j < len(arg):
                ch = arg[j]
                if ch in "ctx":
                    if mode is not None and mode != ch:
                        raise TarError("only one of -c, -t, -x allowed")
                    mode = ch
                elif ch == "v":
                    verbose = True
                elif ch == "f":
                    rest = arg[j + 1:]
                    if rest:
                        archive = rest
                    else:
                        i += 1
                        if i >= len(argv):
                            raise TarError("-f needs an archive argument")
                        archive = argv[i]
                    break
                else:
                    raise TarError("unknown option: -%s" % (ch,))
                j += 1
        else:
            operands.append(arg)
        i += 1
    if mode is None:
        raise TarError("usage: tar_tool.py -c|-t|-x [-v] [-f archive] "
                       "[files...]")
    if mode == "c" and not operands:
        raise TarError("create needs at least one file")
    if mode in ("t", "x") and operands:
        raise TarError("unexpected operands for -%s: %r" % (mode, operands))
    return mode, archive, verbose, operands


def main(argv):
    try:
        mode, archive, verbose, operands = parse_args(argv)
    except TarError as exc:
        print("tar_tool: %s" % (exc,), file=sys.stderr)
        return 2
    try:
        if mode == "c":
            if archive:
                with open(archive, "wb") as out:
                    cmd_create(out, operands)
            else:
                cmd_create(sys.stdout.buffer, operands)
        elif mode == "t":
            if archive:
                with open(archive, "rb") as stream:
                    cmd_list(stream, verbose)
            else:
                cmd_list(sys.stdin.buffer, verbose)
        else:  # mode == "x"
            if archive:
                with open(archive, "rb") as stream:
                    cmd_extract(stream)
            else:
                cmd_extract(sys.stdin.buffer)
    except TarError as exc:
        print("tar_tool: %s" % (exc,), file=sys.stderr)
        return 1
    except (OSError, BrokenPipeError) as exc:
        print("tar_tool: %s" % (exc,), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
