"""Smoke tests for the Selah Bible app.

Run from the project root:

    python -m unittest discover -s tests
    # or
    python tests/test_app.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Point the app at a throw-away database before importing anything.
_TMP = Path(tempfile.mkdtemp(prefix="selah-test-"))
os.environ["SELAH_DB"] = str(_TMP / "test_bible.db")

import db as database  # noqa: E402
import seed  # noqa: E402

seed.build(db_path=database.DB_PATH, source=ROOT / "data" / "kjv.json")

from app import app  # noqa: E402


def verse_id_of(slug: str, chapter: int, verse: int, translation: str = "kjv") -> int:
    conn = database.connect(database.DB_PATH)
    try:
        row = conn.execute(
            "SELECT v.id FROM verses v JOIN books b ON b.id = v.book_id "
            "WHERE b.slug = ? AND v.chapter = ? AND v.verse = ? AND v.translation = ?",
            (slug, chapter, verse, translation),
        ).fetchone()
        return int(row["id"])
    finally:
        conn.close()


class SelahTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP, ignore_errors=True)

    # -- pages ------------------------------------------------------------
    def test_home_redirects_to_default_chapter(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/read/john/1", resp.headers["Location"])

    def test_full_page_render(self):
        resp = self.client.get("/read/john/3")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn('id="chapter-outlet"', html)
        self.assertIn("For God so loved the world", html)
        self.assertIn("John 3", html)

    def test_book_grid_static_include(self):
        html = self.client.get("/read/john/3").get_data(as_text=True)
        self.assertIn("/read/genesis/1", html)   # book picker must list books
        self.assertIn("/read/revelation/1", html)

    def test_htmx_request_gets_partial(self):
        resp = self.client.get("/read/john/3", headers={"HX-Request": "true"})
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("<!doctype html>", html.lower())
        self.assertIn('data-book="john"', html)
        self.assertIn('data-chapter="3"', html)

    def test_history_restore_gets_full_page(self):
        resp = self.client.get(
            "/read/john/4",
            headers={"HX-Request": "true", "HX-History-Restore-Request": "true"},
        )
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<!doctype html>", html.lower())

    def test_focus_marks_verse(self):
        resp = self.client.get("/read/john/3?focus=16", headers={"HX-Request": "true"})
        html = resp.get_data(as_text=True)
        self.assertIn("verse-focus", html)
        self.assertIn('id="v16"', html)

    def test_focus_ignores_unknown_verse(self):
        resp = self.client.get("/read/john/3?focus=9999", headers={"HX-Request": "true"})
        self.assertNotIn("verse-focus", resp.get_data(as_text=True))

    def test_invalid_chapter_404s(self):
        self.assertEqual(self.client.get("/read/genesis/99").status_code, 404)
        self.assertEqual(self.client.get("/read/not-a-book/1").status_code, 404)

    def test_prev_next_boundaries(self):
        html = self.client.get("/read/genesis/1", headers={"HX-Request": "true"}).get_data(as_text=True)
        self.assertIn("Start of the Bible", html)  # no previous chapter
        self.assertIn('rel="next"', html)

    # -- partials ---------------------------------------------------------
    def test_book_grid_partial(self):
        html = self.client.get("/partials/book-grid?book=john").get_data(as_text=True)
        self.assertIn("Old Testament", html)
        self.assertIn("Revelation", html)
        self.assertIn("is-current", html)

    def test_chapter_grid_partial(self):
        html = self.client.get("/partials/chapter-grid/psalms?chapter=23").get_data(as_text=True)
        self.assertIn("150 chapters", html)
        self.assertIn("is-current", html)

    def test_verse_drawer_partial_with_commentary(self):
        vid = verse_id_of("john", 3, 16)
        resp = self.client.get(f"/partials/verse/{vid}")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("God so loved the world", html)
        self.assertIn('hx-post', html)
        self.assertIn("Copy verse", html)

    def test_verse_drawer_missing_404(self):
        self.assertEqual(self.client.get("/partials/verse/99999999").status_code, 404)

    def test_inline_note_partial(self):
        vid = verse_id_of("psalms", 23, 1)
        html = self.client.get(f"/partials/note/{vid}").get_data(as_text=True)
        self.assertIn("The Lord is my shepherd", html)

    # -- search -----------------------------------------------------------
    def test_search_partial_highlights(self):
        resp = self.client.get("/search?q=shepherd", headers={"HX-Request": "true"})
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<mark>", html)
        self.assertIn("search-hits", html)
        self.assertIn("Psalms", html)

    def test_search_reference_jump(self):
        resp = self.client.get("/search?q=John+3%3A16", headers={"HX-Request": "true"})
        html = resp.get_data(as_text=True)
        self.assertIn("Jump to", html)
        self.assertIn("John 3:16", html)

    def test_search_too_short_returns_empty(self):
        resp = self.client.get("/search?q=a", headers={"HX-Request": "true"})
        self.assertEqual(resp.get_data(as_text=True), "")

    def test_search_no_results(self):
        resp = self.client.get("/search?q=xyzzyqopl", headers={"HX-Request": "true"})
        self.assertIn("No verses match", resp.get_data(as_text=True))

    def test_search_full_page(self):
        resp = self.client.get("/search?q=faith")
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("results", html)

    # -- notes ------------------------------------------------------------
    def test_note_lifecycle(self):
        vid = verse_id_of("john", 3, 16)
        post = self.client.post(
            f"/verses/{vid}/notes",
            data={"body": "A test note about grace."},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(post.status_code, 200)
        self.assertIn("A test note about grace.", post.get_data(as_text=True))

        drawer = self.client.get(f"/partials/verse/{vid}").get_data(as_text=True)
        self.assertIn("A test note about grace.", drawer)

        db = database.connect(database.DB_PATH)
        row = db.execute("SELECT id FROM notes WHERE body = ?", ("A test note about grace.",)).fetchone()
        db.close()
        self.assertIsNotNone(row)

        delete = self.client.delete(f"/notes/{row['id']}", headers={"HX-Request": "true"})
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.get_data(as_text=True), "")

        db = database.connect(database.DB_PATH)
        gone = db.execute("SELECT 1 FROM notes WHERE id = ?", (row["id"],)).fetchone()
        db.close()
        self.assertIsNone(gone)

    def test_empty_note_rejected(self):
        vid = verse_id_of("john", 3, 16)
        resp = self.client.post(f"/verses/{vid}/notes", data={"body": "   "})
        self.assertEqual(resp.status_code, 422)

    def test_note_for_missing_verse_404(self):
        resp = self.client.post("/verses/99999999/notes", data={"body": "hi"})
        self.assertEqual(resp.status_code, 404)

    # -- Arabic translation --------------------------------------------------
    def test_both_translations_are_seeded(self):
        db = database.connect(database.DB_PATH)
        try:
            counts = dict(db.execute("SELECT translation, COUNT(*) FROM verses GROUP BY translation"))
        finally:
            db.close()
        self.assertEqual(counts.get("kjv"), 31102)
        self.assertEqual(counts.get("jesuit"), 31102)

    def test_footer_counts_verse_references_not_rows(self):
        html = self.client.get("/read/john/3").get_data(as_text=True)
        self.assertIn("66 books · 31102 verses", html)

    def test_chapter_is_english_without_the_cookie(self):
        html = self.client.get("/read/john/3", headers={"HX-Request": "true"}).get_data(as_text=True)
        self.assertIn("For God so loved the world", html)
        self.assertNotIn('dir="rtl"', html)

    def test_cookie_switches_the_chapter_to_arabic(self):
        self.client.set_cookie("selah_translation", "jesuit")
        try:
            resp = self.client.get("/read/john/3", headers={"HX-Request": "true"})
        finally:
            self.client.delete_cookie("selah_translation")
        html = resp.get_data(as_text=True)
        self.assertIn('data-translation="jesuit"', html)
        self.assertIn('dir="rtl"', html)
        self.assertIn('lang="ar"', html)
        self.assertIn("لأَنَّهُ", html)  # John 3:16 in the Arabic text
        self.assertNotIn("For God so loved", html)
        self.assertIn(">John<", html)  # navigation chrome stays English/LTR

    def test_verse_drawer_uses_the_right_script(self):
        arabic = self.client.get(f"/partials/verse/{verse_id_of('john', 3, 16, 'jesuit')}")
        html = arabic.get_data(as_text=True)
        self.assertIn('dir="rtl"', html)
        self.assertIn("لأَنَّهُ", html)
        self.assertIn("(Jesuit)", html)
        self.assertIn("God so loved the world", html)  # study notes stay English

        english = self.client.get(f"/partials/verse/{verse_id_of('john', 3, 16)}")
        html = english.get_data(as_text=True)
        self.assertNotIn('dir="rtl"', html)
        self.assertIn("For God so loved the world", html)
        self.assertIn("(KJV)", html)

    def test_search_is_scoped_to_the_active_translation(self):
        english = self.client.get(
            "/search", query_string={"q": "shepherd"}, headers={"HX-Request": "true"}
        ).get_data(as_text=True)
        self.assertIn("<mark>", english)
        self.assertIn("Psalms", english)

        self.client.set_cookie("selah_translation", "jesuit")
        try:
            english_only = self.client.get(
                "/search", query_string={"q": "shepherd"}, headers={"HX-Request": "true"}
            ).get_data(as_text=True)
            # typed without vocalisation marks, matched against vocalised text
            folded = self.client.get(
                "/search", query_string={"q": "الارض"}, headers={"HX-Request": "true"}
            ).get_data(as_text=True)
        finally:
            self.client.delete_cookie("selah_translation")

        self.assertIn("No verses match", english_only)
        self.assertIn("<mark>", folded)

    def test_prayer_verse_follows_the_translation(self):
        self.client.set_cookie("selah_translation", "jesuit")
        try:
            html = self.client.get("/partials/random-verse").get_data(as_text=True)
        finally:
            self.client.delete_cookie("selah_translation")
        self.assertTrue(any("؀" <= ch <= "ۿ" for ch in html))

    # -- static assets ----------------------------------------------------
    def test_static_assets_served(self):
        for path in (
            "/static/js/htmx.min.js",
            "/static/js/tailwind.js",
            "/static/js/app.js",
            "/static/css/app.css",
            "/static/favicon.svg",
        ):
            resp = self.client.get(path)
            try:
                self.assertEqual(resp.status_code, 200, path)
            finally:
                resp.close()

    def test_404_page(self):
        resp = self.client.get("/read/genesis/999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("isn’t here", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
