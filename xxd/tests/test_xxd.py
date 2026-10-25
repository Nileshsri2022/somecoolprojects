"""Tests for xxd.py. Temp files only; no system xxd required."""

import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xxd  # noqa: E402

XXD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "xxd.py")


def dump_bytes(data, **kw):
    out = io.StringIO()
    xxd.dump(io.BytesIO(data), out,
             cols=kw.get("cols", 16),
             groupsize=kw.get("groupsize", 2),
             little_endian=kw.get("little_endian", False),
             length=kw.get("length"),
             seek=kw.get("seek"))
    return out.getvalue()


def revert_text(text, **kw):
    out = io.BytesIO()
    xxd.revert(io.StringIO(text), out,
               groupsize=kw.get("groupsize", 2),
               little_endian=kw.get("little_endian", False),
               length=kw.get("length"),
               seek=kw.get("seek"))
    return out.getvalue()


# Page Step 1 fixture: "file1.txt" followed by NULs, as in files.tar.
TAR_HEAD = b"file1.txt" + b"\x00" * 7


class TestDefaultDump(unittest.TestCase):
    def test_step1_first_line_verbatim(self):
        self.assertEqual(
            dump_bytes(TAR_HEAD + b"\x00" * 144).splitlines()[0],
            "00000000: 6669 6c65 312e 7478 7400 0000 0000 0000  "
            "file1.txt.......")

    def test_step1_second_line_all_dots(self):
        lines = dump_bytes(TAR_HEAD + b"\x00" * 144).splitlines()
        self.assertEqual(
            lines[1],
            "00000010: 0000 0000 0000 0000 0000 0000 0000 0000  "
            "................")

    def test_nonprintable_and_del_are_dots(self):
        out = dump_bytes(bytes([0x00, 0x1f, 0x20, 0x7e, 0x7f, 0x80, 0xff]))
        self.assertTrue(out.endswith("  .. ~...\n"), out)

    def test_empty_input_is_empty_output(self):
        self.assertEqual(dump_bytes(b""), "")

    def test_short_final_line_ascii_aligned(self):
        out = dump_bytes(b"AB")
        # Hex field padded to a full 16-byte line's width (39 chars).
        self.assertEqual(out, "00000000: 4142" + " " * 37 + "AB\n")

    def test_offset_grows_past_16_bytes(self):
        out = dump_bytes(b"A" * 17)
        self.assertTrue(out.splitlines()[1].startswith("00000010: "))


class TestLittleEndianAndGrouping(unittest.TestCase):
    def test_step2_e_first_line(self):
        out = dump_bytes(TAR_HEAD + b"\x00" * 144,
                         little_endian=True, groupsize=4)
        self.assertEqual(
            out.splitlines()[0],
            "00000000: 656c6966 78742e31 00000074 00000000  "
            "file1.txt.......")

    def test_step2_e_g8_first_line(self):
        out = dump_bytes(TAR_HEAD + b"\x00" * 144,
                         little_endian=True, groupsize=8)
        self.assertEqual(
            out.splitlines()[0],
            "00000000: 78742e31656c6966 0000000000000074  "
            "file1.txt.......")

    def test_group_1(self):
        self.assertEqual(
            dump_bytes(b"ABC", cols=3, groupsize=1),
            "00000000: 41 42 43  ABC\n")

    def test_group_larger_than_cols_is_one_group(self):
        self.assertEqual(
            dump_bytes(b"ABCD", cols=4, groupsize=8),
            "00000000: 41424344  ABCD\n")

    def test_partial_final_group(self):
        self.assertEqual(
            dump_bytes(b"ABCDE", cols=5, groupsize=2),
            "00000000: 4142 4344 45  ABCDE\n")

    def test_invalid_group_values(self):
        for bad in ("0", "3", "5", "6", "-2", "512", "abc"):
            with self.assertRaises(xxd.XxdError, msg=bad):
                xxd.parse_groupsize(bad)
        for good in ("1", "2", "4", "8", "16"):
            self.assertEqual(xxd.parse_groupsize(good), int(good))


class TestColumnsLengthSeek(unittest.TestCase):
    def test_step3_c4_l16_verbatim(self):
        data = TAR_HEAD
        out = dump_bytes(data, cols=4, length=16)
        self.assertEqual(out, (
            "00000000: 6669 6c65  file\n"
            "00000004: 312e 7478  1.tx\n"
            "00000008: 7400 0000  t...\n"
            "0000000c: 0000 0000  ....\n"))

    def test_step3_l16_only(self):
        out = dump_bytes(TAR_HEAD + b"EXTRA", length=16)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertTrue(out.startswith("00000000: 6669 6c65"))

    def test_length_zero(self):
        self.assertEqual(dump_bytes(b"ABC", length=0), "")

    def test_length_truncates_mid_line(self):
        self.assertEqual(dump_bytes(b"ABCDEF", length=3),
                         "00000000: 4142 43" + " " * 34 + "ABC\n")

    def test_step4_seek_512(self):
        data = b"\x00" * 512 + b"File 1 contents\n"
        out = dump_bytes(data, seek=512, length=16)
        self.assertEqual(
            out,
            "00000200: 4669 6c65 2031 2063 6f6e 7465 6e74 730a  "
            "File 1 contents.\n")

    def test_step4_seek_124_length_12(self):
        data = bytearray(136)
        data[124:136] = b"00000000020 "
        out = dump_bytes(bytes(data), seek=124, length=12)
        # Hex field "3030 ... 3020" is 29 chars, padded to 39, then
        # 2 spaces; the ASCII field ends with the 0x20 byte itself.
        self.assertEqual(
            out,
            "0000007c: 3030 3030 3030 3030 3032 3020"
            + " " * 12 + "00000000020 \n")

    def test_seek_past_eof_is_empty(self):
        self.assertEqual(dump_bytes(b"ABC", seek=100), "")

    def test_negative_seek_from_eof(self):
        out = dump_bytes(b"0123456789", seek=-4)
        self.assertTrue(out.startswith("00000006: "), out)

    def test_invalid_cols(self):
        for bad in ("0", "257", "-1"):
            with self.assertRaises(xxd.XxdError, msg=bad):
                xxd.parse_cols(bad)


class TestReverse(unittest.TestCase):
    def test_roundtrip_text(self):
        data = b"Hello, xxd!\nSecond line.\x00\xff"
        self.assertEqual(revert_text(dump_bytes(data)), data)

    def test_roundtrip_all_byte_values(self):
        data = bytes(range(256)) * 3
        self.assertEqual(revert_text(dump_bytes(data)), data)

    def test_roundtrip_empty(self):
        self.assertEqual(revert_text(dump_bytes(b"")), b"")

    def test_roundtrip_little_endian(self):
        data = bytes(range(256))
        dumped = dump_bytes(data, little_endian=True, groupsize=4)
        self.assertEqual(
            revert_text(dumped, little_endian=True, groupsize=4), data)

    def test_revert_page_style_lines(self):
        text = ("00000000: 6669 6c65 312e 7478 7400 0000 0000 0000  "
                "file1.txt.......\n")
        self.assertEqual(revert_text(text), TAR_HEAD)

    def test_ascii_column_that_looks_like_hex_is_ignored(self):
        # File whose text is "dead": dump, revert must not append
        # 0xde 0xad from the ASCII column.
        self.assertEqual(revert_text(dump_bytes(b"dead")), b"dead")

    def test_plain_hex_no_offsets(self):
        self.assertEqual(revert_text("66696c65\n"), b"file")

    def test_blank_lines_skipped_uppercase_ok(self):
        self.assertEqual(revert_text("\n6669 6C65\n\n"), b"file")

    def test_odd_hex_is_error(self):
        with self.assertRaises(xxd.XxdError):
            revert_text("666\n")

    def test_nonhex_token_is_error(self):
        with self.assertRaises(xxd.XxdError):
            revert_text("66zz\n")

    def test_reverse_length_limit(self):
        self.assertEqual(revert_text("66696c65\n", length=2), b"fi")

    def test_reverse_seek_pads_nuls(self):
        out = revert_text("41\n", seek=2)
        self.assertEqual(out, b"\x00\x00A")


class TestCLI(unittest.TestCase):
    def run_cli(self, args, stdin_data=None):
        return subprocess.run(
            [sys.executable, XXD] + args, input=stdin_data,
            capture_output=True, timeout=30)

    def test_file_dump_and_revert_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "in.bin")
            hexf = os.path.join(tmp, "in.hex")
            back = os.path.join(tmp, "back.bin")
            data = bytes(range(256))
            with open(src, "wb") as f:
                f.write(data)
            r = self.run_cli([src, hexf])
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.run_cli(["-r", hexf, back])
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(back, "rb") as f:
                self.assertEqual(f.read(), data)

    def test_stdin_dump(self):
        r = self.run_cli([], stdin_data=b"file")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"6669 6c65", r.stdout)

    def test_e_cli_defaults_to_group_4(self):
        r = self.run_cli(["-e"], stdin_data=TAR_HEAD)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith(
            b"00000000: 656c6966 78742e31"), r.stdout)

    def test_invalid_group_cli(self):
        r = self.run_cli(["-g", "3"], stdin_data=b"x")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(b"grouping", r.stderr)

    def test_invalid_cols_cli(self):
        r = self.run_cli(["-c", "0"], stdin_data=b"x")
        self.assertNotEqual(r.returncode, 0)

    def test_missing_file_cli(self):
        r = self.run_cli(["/nonexistent/nope.bin"])
        self.assertNotEqual(r.returncode, 0)

    def test_tarball_page_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in (1, 2, 3):
                with open(os.path.join(tmp, f"file{i}.txt"), "w") as f:
                    f.write(f"File {i} contents\n")
            tarpath = os.path.join(tmp, "files.tar")
            with tarfile.open(tarpath, "w",
                              format=tarfile.USTAR_FORMAT) as tar:
                for i in (1, 2, 3):
                    tar.add(os.path.join(tmp, f"file{i}.txt"),
                            arcname=f"file{i}.txt")
            r = self.run_cli([tarpath])
            self.assertEqual(r.returncode, 0, r.stderr)
            first = r.stdout.decode().splitlines()[0]
            self.assertEqual(
                first,
                "00000000: 6669 6c65 312e 7478 7400 0000 0000 0000  "
                "file1.txt.......")
            r2 = self.run_cli(["-s", "512", "-l", "16", tarpath])
            self.assertIn(b"File 1 contents.", r2.stdout)


if __name__ == "__main__":
    unittest.main()
