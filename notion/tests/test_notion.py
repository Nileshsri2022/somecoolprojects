"""Unit + CLI + HTTP tests for the local Notion clone (stdlib only)."""
import io
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notion as N


def fresh_ws(tmp):
    return N.Workspace(os.path.join(tmp, "ws.json"))


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = fresh_ws(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_and_login(self):
        self.ws.register_user("alice", "secret")
        self.assertEqual(self.ws.authenticate("alice", "secret")["username"], "alice")

    def test_duplicate_registration_rejected(self):
        self.ws.register_user("alice", "secret")
        with self.assertRaises(N.NotionError):
            self.ws.register_user("alice", "other")

    def test_wrong_password_and_unknown_user_rejected(self):
        self.ws.register_user("alice", "secret")
        with self.assertRaises(N.NotionError):
            self.ws.authenticate("alice", "nope")
        with self.assertRaises(N.NotionError):
            self.ws.authenticate("mallory", "secret")

    def test_password_not_stored_plaintext_and_salts_differ(self):
        self.ws.register_user("alice", "same")
        self.ws.register_user("bob", "same")
        ha = self.ws.users["alice"]["password_hash"]
        hb = self.ws.users["bob"]["password_hash"]
        self.assertNotIn("same", ha)
        self.assertNotEqual(ha, hb)
        self.assertIn("$", ha)


class PageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = fresh_ws(self.tmp.name)
        self.ws.register_user("alice", "pw")
        self.ws.register_user("bob", "pw")

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_title_untitled(self):
        page = self.ws.create_page("alice")
        self.assertEqual(page["title"], "Untitled")

    def test_nested_listing_order(self):
        a = self.ws.create_page("alice", "A")
        b = self.ws.create_page("alice", "B")
        kid = self.ws.create_page("alice", "Kid", parent_id=a["id"])
        top = self.ws.siblings("alice", None)
        self.assertEqual([p["title"] for p in top], ["A", "B"])
        self.assertEqual([p["title"] for p in self.ws.children_of("alice", a["id"])], ["Kid"])

    def test_per_user_isolation(self):
        mine = self.ws.create_page("alice", "Mine")
        self.assertEqual(self.ws.siblings("bob", None), [])
        with self.assertRaises(N.NotionError):
            self.ws._page_for_user("bob", mine["id"])
        with self.assertRaises(N.NotionError):
            self.ws.create_page("bob", "Sneaky", parent_id=mine["id"])

    def test_update_title(self):
        page = self.ws.create_page("alice", "Old")
        self.ws.update_title("alice", page["id"], "New")
        self.assertEqual(self.ws.pages[page["id"]]["title"], "New")
        with self.assertRaises(N.NotionError):
            self.ws.update_title("alice", page["id"], "")


class BlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = fresh_ws(self.tmp.name)
        self.ws.register_user("alice", "pw")
        self.page = self.ws.create_page("alice", "P")

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_block_types_accepted(self):
        for t in N.BLOCK_TYPES:
            self.ws.add_block("alice", self.page["id"], t, "x")
        self.assertEqual(len(self.ws.pages[self.page["id"]]["blocks"]), 5)

    def test_invalid_block_type_rejected(self):
        with self.assertRaises(N.NotionError):
            self.ws.add_block("alice", self.page["id"], "table", "x")

    def test_edit_delete_move_block(self):
        b1 = self.ws.add_block("alice", self.page["id"], "paragraph", "one")
        b2 = self.ws.add_block("alice", self.page["id"], "paragraph", "two")
        self.ws.edit_block("alice", self.page["id"], b2["id"], text="TWO")
        self.ws.edit_block("alice", self.page["id"], b2["id"], block_type="heading_1")
        blocks = self.ws.pages[self.page["id"]]["blocks"]
        self.assertEqual(blocks[1]["text"], "TWO")
        self.assertEqual(blocks[1]["type"], "heading_1")
        self.ws.move_block("alice", self.page["id"], b2["id"], 0)
        self.assertEqual(self.ws.pages[self.page["id"]]["blocks"][0]["id"], b2["id"])
        self.ws.delete_block("alice", self.page["id"], b1["id"])
        self.assertEqual(len(self.ws.pages[self.page["id"]]["blocks"]), 1)

    def test_block_errors(self):
        with self.assertRaises(N.NotionError):
            self.ws.edit_block("alice", self.page["id"], "nope", text="x")
        b = self.ws.add_block("alice", self.page["id"], "paragraph", "x")
        with self.assertRaises(N.NotionError):
            self.ws.move_block("alice", self.page["id"], b["id"], 5)


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = fresh_ws(self.tmp.name)
        self.ws.register_user("alice", "pw")

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_name_and_blocks(self):
        src = self.ws.create_page("alice", "Notes")
        self.ws.add_block("alice", src["id"], "heading_1", "Hi")
        copy = self.ws.duplicate_page("alice", src["id"])
        self.assertEqual(copy["title"], "Copy of Notes")
        self.assertNotEqual(copy["id"], src["id"])
        self.assertEqual([b["text"] for b in copy["blocks"]], ["Hi"])
        self.assertNotEqual(copy["blocks"][0]["id"], src["blocks"][0]["id"])

    def test_second_duplicate_gets_number(self):
        src = self.ws.create_page("alice", "Notes")
        self.ws.duplicate_page("alice", src["id"])
        copy2 = self.ws.duplicate_page("alice", src["id"])
        self.assertEqual(copy2["title"], "Copy of Notes (1)")

    def test_duplicate_copies_children_recursively(self):
        src = self.ws.create_page("alice", "Parent")
        kid = self.ws.create_page("alice", "Kid", parent_id=src["id"])
        self.ws.add_block("alice", kid["id"], "paragraph", "kid text")
        copy = self.ws.duplicate_page("alice", src["id"])
        kids = self.ws.children_of("alice", copy["id"])
        self.assertEqual(len(kids), 1)
        self.assertEqual(kids[0]["title"], "Kid")
        self.assertEqual(kids[0]["blocks"][0]["text"], "kid text")
        self.assertNotEqual(kids[0]["id"], kid["id"])


class ReorganiseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = fresh_ws(self.tmp.name)
        self.ws.register_user("alice", "pw")
        self.a = self.ws.create_page("alice", "A")
        self.b = self.ws.create_page("alice", "B")
        self.c = self.ws.create_page("alice", "C")

    def tearDown(self):
        self.tmp.cleanup()

    def test_move_page_reparents(self):
        self.ws.move_page("alice", self.c["id"], parent_id=self.a["id"])
        self.assertEqual(self.ws.pages[self.c["id"]]["parent_id"], self.a["id"])
        self.assertEqual([p["title"] for p in self.ws.siblings("alice", None)], ["A", "B"])

    def test_move_page_to_top_and_position(self):
        self.ws.move_page("alice", self.c["id"], parent_id=self.a["id"])
        self.ws.move_page("alice", self.c["id"], parent_id=None, position=0)
        self.assertEqual([p["title"] for p in self.ws.siblings("alice", None)],
                         ["C", "A", "B"])

    def test_cycle_rejected(self):
        kid = self.ws.create_page("alice", "Kid", parent_id=self.a["id"])
        with self.assertRaises(N.NotionError):
            self.ws.move_page("alice", self.a["id"], parent_id=kid["id"])
        with self.assertRaises(N.NotionError):
            self.ws.move_page("alice", self.a["id"], parent_id=self.a["id"])

    def test_reorder_exact_set_required(self):
        self.ws.reorder_siblings("alice", None, [self.c["id"], self.a["id"], self.b["id"]])
        self.assertEqual([p["title"] for p in self.ws.siblings("alice", None)],
                         ["C", "A", "B"])
        with self.assertRaises(N.NotionError):
            self.ws.reorder_siblings("alice", None, [self.a["id"], self.b["id"]])
        with self.assertRaises(N.NotionError):
            self.ws.reorder_siblings("alice", None,
                                     [self.a["id"], self.b["id"], self.c["id"], "x"])

    def test_delete_page_recursive_library_only(self):
        kid = self.ws.create_page("alice", "Kid", parent_id=self.a["id"])
        self.ws.delete_page("alice", self.a["id"])
        self.assertNotIn(self.a["id"], self.ws.pages)
        self.assertNotIn(kid["id"], self.ws.pages)
        self.assertEqual([p["title"] for p in self.ws.siblings("alice", None)], ["B", "C"])


class SearchPersistenceRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "ws.json")
        self.ws = N.Workspace(self.path)
        self.ws.register_user("alice", "pw")
        self.ws.register_user("bob", "pw")

    def tearDown(self):
        self.tmp.cleanup()

    def test_search_title_block_case_insensitive_and_isolated(self):
        p1 = self.ws.create_page("alice", "Shopping")
        self.ws.add_block("alice", p1["id"], "paragraph", "buy MILK")
        p2 = self.ws.create_page("alice", "Other")
        self.ws.create_page("bob", "Shopping")
        self.assertEqual([p["id"] for p in self.ws.search("alice", "shop")], [p1["id"]])
        self.assertEqual([p["id"] for p in self.ws.search("alice", "milk")], [p1["id"]])
        self.assertEqual(self.ws.search("alice", "zzz"), [])

    def test_persistence_round_trip(self):
        p = self.ws.create_page("alice", "Keep")
        kid = self.ws.create_page("alice", "Kid", parent_id=p["id"])
        self.ws.add_block("alice", p["id"], "heading_2", "**bold**")
        reloaded = N.Workspace(self.path)
        self.assertEqual(reloaded.pages[p["id"]]["title"], "Keep")
        self.assertEqual(reloaded.pages[kid["id"]]["parent_id"], p["id"])
        self.assertEqual(reloaded.pages[p["id"]]["blocks"][0]["text"], "**bold**")
        reloaded.authenticate("alice", "pw")

    def test_render_inline_bold_italic_and_escape(self):
        out = N.render_inline("a **bold** b *it* c <script>alert(1)</script> **unclosed")
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>it</em>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("<script>alert", out)
        self.assertIn("**unclosed", out)

    def test_render_page_html_bullets_grouped(self):
        p = self.ws.create_page("alice", "P")
        self.ws.add_block("alice", p["id"], "bulleted_list_item", "one")
        self.ws.add_block("alice", p["id"], "bulleted_list_item", "two")
        self.ws.add_block("alice", p["id"], "paragraph", "after")
        html_out = N.render_page_html(self.ws, "alice", self.ws.pages[p["id"]])
        self.assertIn("<ul>", html_out)
        self.assertIn("<li>one</li>", html_out)
        self.assertIn("<p>after</p>", html_out)


class HttpViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "ws.json")
        ws = N.Workspace(self.path)
        ws.register_user("alice", "pw")
        self.page = ws.create_page("alice", "Hello Page")
        ws.add_block("alice", self.page["id"], "paragraph", "hello body")
        self.server = N.make_server(self.path, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def test_index_and_page_and_404(self):
        index = urllib.request.urlopen("http://127.0.0.1:%d/" % self.port, timeout=5).read().decode()
        self.assertIn("Hello Page", index)
        page = urllib.request.urlopen("http://127.0.0.1:%d/page/%s" % (self.port, self.page["id"]), timeout=5).read().decode()
        self.assertIn("hello body", page)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen("http://127.0.0.1:%d/page/nope" % self.port, timeout=5)
        self.assertEqual(ctx.exception.code, 404)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "ws.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = N.main(["--data", self.data] + argv)
        return code, buf.getvalue()

    def test_cli_end_to_end(self):
        code, _ = self.run_cli(["register", "--user", "alice", "--password", "pw"])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["create-page", "--user", "alice", "--password", "pw",
                                  "--title", "CLI Page"])
        self.assertEqual(code, 0)
        page_id = out.strip()
        code, _ = self.run_cli(["add-block", "--user", "alice", "--password", "pw",
                                "--page", page_id, "--type", "heading_1", "--text", "Head"])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["list-pages", "--user", "alice", "--password", "pw"])
        self.assertIn("CLI Page", out)
        code, out = self.run_cli(["duplicate-page", "--user", "alice", "--password", "pw",
                                  "--page", page_id])
        self.assertEqual(code, 0)
        code, out = self.run_cli(["search", "--user", "alice", "--password", "pw", "CLI"])
        self.assertIn("CLI Page", out)
        self.assertIn("Copy of CLI Page", out)

    def test_cli_bad_credentials_exit_2(self):
        self.run_cli(["register", "--user", "alice", "--password", "pw"])
        code, _ = self.run_cli(["list-pages", "--user", "alice", "--password", "wrong"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
