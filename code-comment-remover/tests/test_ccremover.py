"""Tests for ccremover.py (see docs/TEST_PLAN.md)."""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccremover
from ccremover import UnterminatedComment, strip_source

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
SCRIPT = os.path.join(HERE, "..", "ccremover.py")

def read_fixture(name):
    with open(os.path.join(FIXTURES, name)) as handle:
        return handle.read()


def read_text(path):
    with open(path) as handle:
        return handle.read()



def run_cli(args, stdin=""):
    proc = subprocess.run(
        [sys.executable, SCRIPT] + args, input=stdin,
        capture_output=True, text=True, timeout=30)
    return proc


class PythonTests(unittest.TestCase):
    def strip(self, text, **kw):
        return strip_source(text, "python", **kw)

    def test_full_line_and_trailing_comments(self):
        self.assertEqual(
            self.strip("# hi\nx = 1 # note\n"),
            "x = 1\n")

    def test_comment_only_lines_leave_no_blank_line(self):
        self.assertEqual(
            self.strip("a = 1\n# gone\n\nb = 2\n"),
            "a = 1\n\nb = 2\n")

    def test_hash_inside_strings_kept(self):
        self.assertEqual(
            self.strip("a = '# x' # gone\nb = \"# y\"\n"),
            "a = '# x'\nb = \"# y\"\n")

    def test_triple_quoted_string_kept(self):
        self.assertEqual(
            self.strip("s = '''a # b\nc # d'''\nx = 1 # gone\n"),
            "s = '''a # b\nc # d'''\nx = 1\n")

    def test_raw_string_and_escaped_quote(self):
        self.assertEqual(
            self.strip("a = r'# x' # gone\nb = 'it\\'s # y' # gone\n"),
            "a = r'# x'\nb = 'it\\'s # y'\n")

    def test_fstring_hash_kept(self):
        # The f-string body is treated as string content (SPEC limit
        # only bites for 3.12+ f-string expression comments).
        self.assertEqual(
            self.strip("s = f'val {x} # not a comment'\n"),
            "s = f'val {x} # not a comment'\n")

    def test_tool_comment_noqa_kept(self):
        self.assertEqual(
            self.strip("example = lambda: 'example'  # noqa: E731\n"),
            "example = lambda: 'example'  # noqa: E731\n")

    def test_tool_comment_type_ignore_kept(self):
        self.assertEqual(
            self.strip("x = f()  # type: ignore\n"),
            "x = f()  # type: ignore\n")

    def test_tool_comment_opt_out(self):
        self.assertEqual(
            self.strip("x = 1  # noqa: E501\n", keep_tool_comments=False),
            "x = 1\n")

    def test_not_a_tool_comment(self):
        # 'notably' does not start with 'noqa'; 'types' != 'type:'.
        self.assertEqual(
            self.strip("x = 1 # notably fine\n"),
            "x = 1\n")


class JsTests(unittest.TestCase):
    def strip(self, text, **kw):
        return strip_source(text, "js", **kw)

    def test_page_factorial_example(self):
        src = read_fixture("factorial.js")
        expected = read_fixture("factorial.js.expected")
        self.assertEqual(self.strip(src), expected)

    def test_line_and_block_comments(self):
        self.assertEqual(
            self.strip("// gone\nx = 1; // gone\n/* multi\nline */\ny = 2;\n"),
            "x = 1;\ny = 2;\n")

    def test_block_joins_code_on_both_sides(self):
        self.assertEqual(self.strip("a /* x */ b\n"), "a  b\n")

    def test_markers_inside_strings_kept(self):
        self.assertEqual(
            self.strip('u = "http://x"; // gone\n'
                       "s = '/* nope */';\n"),
            'u = "http://x";\ns = \'/* nope */\';\n')

    def test_template_literal_marker_kept(self):
        self.assertEqual(
            self.strip("t = `a // b`;\n"), "t = `a // b`;\n")

    def test_nested_block_closes_at_first_end(self):
        # Documented limit: C-style block comments do not nest.
        self.assertEqual(
            self.strip("a /* outer /* inner */ b\n"),
            "a  b\n")

    def test_unterminated_block_errors_with_start_line(self):
        with self.assertRaises(UnterminatedComment) as ctx:
            self.strip("ok = 1;\n/* never closed\nmore\n")
        self.assertEqual(ctx.exception.line, 2)

    def test_js_regex_literal_is_a_known_limit(self):
        # Pinned implemented behaviour, NOT correct parser behaviour:
        # the regex /\/\// (which matches "//") is truncated because
        # its final two slashes are misread as a comment start.
        # See SPEC.md "Known limits".
        self.assertEqual(
            self.strip("const r = /\\/\\//;\n"),
            "const r = /\\/\\\n")


class CTests(unittest.TestCase):
    def strip(self, text, **kw):
        return strip_source(text, "c", **kw)

    def test_page_factorial_example(self):
        src = read_fixture("factorial.c")
        expected = read_fixture("factorial.c.expected")
        self.assertEqual(self.strip(src), expected)

    def test_char_literal_slash_kept(self):
        self.assertEqual(
            self.strip("char c = '/'; // gone\n"),
            "char c = '/';\n")

    def test_marker_inside_string_kept(self):
        self.assertEqual(
            self.strip('s = "// not a comment";\n'),
            's = "// not a comment";\n')


class GoTests(unittest.TestCase):
    def strip(self, text, **kw):
        return strip_source(text, "go", **kw)

    def test_page_factorial_with_doc_and_directive(self):
        src = read_fixture("factorial.go")
        expected = read_fixture("factorial.go.expected")
        self.assertEqual(self.strip(src), expected)

    def test_doc_comment_above_package_kept(self):
        self.assertEqual(
            self.strip("// Package foo does things.\npackage foo\n"),
            "// Package foo does things.\npackage foo\n")

    def test_doc_comment_above_type_and_var_kept(self):
        self.assertEqual(
            self.strip("// Thing is a thing.\ntype Thing struct{}\n"
                       "// Count is a count.\nvar Count = 1\n"),
            "// Thing is a thing.\ntype Thing struct{}\n"
            "// Count is a count.\nvar Count = 1\n")

    def test_ordinary_comment_above_blank_line_removed(self):
        self.assertEqual(
            self.strip("// just a note\n\nx := 1\n"),
            "\nx := 1\n")

    def test_ordinary_comment_above_code_removed(self):
        self.assertEqual(
            self.strip("// just a note\nx := 1\n"),
            "x := 1\n")

    def test_block_doc_comment_above_func_kept(self):
        self.assertEqual(
            self.strip("/* Does work. */\nfunc work() {}\n"),
            "/* Does work. */\nfunc work() {}\n")

    def test_no_go_doc_opt_out(self):
        self.assertEqual(
            self.strip("// Doc.\nfunc f() {}\n", go_doc=False),
            "func f() {}\n")

    def test_go_directives_kept(self):
        self.assertEqual(
            self.strip("//go:generate echo hi\n//go:build ignore\n"
                       "// +build linux\n"),
            "//go:generate echo hi\n//go:build ignore\n// +build linux\n")

    def test_spaced_go_directive_is_not_a_directive(self):
        self.assertEqual(
            self.strip("// go:generate echo hi\n"),
            "")

    def test_go_raw_string_kept(self):
        self.assertEqual(
            self.strip("s := `a // b\n/* c */`;\n"),
            "s := `a // b\n/* c */`;\n")

    def test_go_directive_opt_out(self):
        self.assertEqual(
            self.strip("//go:generate echo hi\n", keep_tool_comments=False),
            "")


class EdgeTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(strip_source("", "python"), "")
        self.assertEqual(strip_source("", "js"), "")

    def test_only_comments(self):
        self.assertEqual(strip_source("# a\n# b\n", "python"), "")
        self.assertEqual(strip_source("// a\n/* b */\n", "js"), "")

    def test_crlf_normalised_to_lf(self):
        self.assertEqual(
            strip_source("x = 1 # c\r\ny = 2\r\n", "python"),
            "x = 1\ny = 2\n")

    def test_unterminated_string_kept_to_eof(self):
        # Documented tolerance, not a parser error.
        self.assertEqual(
            strip_source("s = 'abc\n", "python"), "s = 'abc\n")

    def test_no_trailing_newline_input(self):
        self.assertEqual(
            strip_source("x = 1 # c", "python"), "x = 1\n")

    def test_unknown_language(self):
        with self.assertRaises(Exception):
            strip_source("x", "ruby")


class FixtureTests(unittest.TestCase):
    def test_all_fixtures(self):
        cases = [
            ("python_example.py", "python", {}),
            ("strings_py.py", "python", {}),
            ("factorial.js", "js", {}),
            ("strings_js.js", "js", {}),
            ("factorial.c", "c", {}),
            ("factorial.go", "go", {}),
        ]
        for name, lang, kw in cases:
            with self.subTest(fixture=name):
                src = read_fixture(name)
                expected = read_fixture(name + ".expected")
                self.assertEqual(strip_source(src, lang, **kw), expected)


class CliTests(unittest.TestCase):
    def test_stdin_requires_lang(self):
        proc = run_cli([], stdin="x = 1 # c\n")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("stdin", proc.stderr)

    def test_stdin_python(self):
        proc = run_cli(["--lang", "python"], stdin="x = 1 # c\n")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "x = 1\n")

    def test_file_auto_infers_extension(self):
        path = os.path.join(FIXTURES, "factorial.js")
        expected = read_text(path + ".expected")
        proc = run_cli([path])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, expected)

    def test_unknown_extension_errors(self):
        proc = run_cli(["/tmp/definitely-not-a-real-file.xyz"])
        self.assertEqual(proc.returncode, 2)

    def test_missing_file_errors(self):
        proc = run_cli(["/tmp/definitely-not-a-real-file.py"])
        self.assertEqual(proc.returncode, 2)

    def test_multiple_files_concatenated(self):
        proc = run_cli(["--lang", "python",
                        os.path.join(FIXTURES, "python_example.py"),
                        os.path.join(FIXTURES, "python_example.py")])
        self.assertEqual(proc.returncode, 0)
        expected = read_fixture("python_example.py.expected")
        self.assertEqual(proc.stdout, expected * 2)

    def test_unterminated_block_cli_exit_2(self):
        proc = run_cli(["--lang", "js"], stdin="/* never\n")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("unterminated", proc.stderr)

    def test_help_exits_zero(self):
        proc = run_cli(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("ccremover", proc.stdout)

    def test_no_in_place_option(self):
        proc = run_cli(["--in-place", "--lang", "python"])
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
