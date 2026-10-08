"""Selah -- a quiet Bible reader.

Flask routes that answer either a full page or, when HTMX asks for a
fragment, a swap-in partial. All data comes straight from SQLite.
"""

from __future__ import annotations

import html
import re
import sqlite3
from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, url_for

import db as database

app = Flask(__name__)
database.init_app(app)


# ---------------------------------------------------------------------------
# startup: build the database on first run
# ---------------------------------------------------------------------------
def ensure_database() -> None:
    if database.DB_PATH.exists():
        return
    try:
        import seed

        print(f"Database not found at {database.DB_PATH} -- seeding (first run only) ...")
        seed.build()
    except Exception as exc:  # pragma: no cover - startup convenience
        print(f"WARNING: could not seed database: {exc}", file=__import__("sys").stderr)


ensure_database()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
# Translation keys as they appear in the UI and in the `verses` table.
TRANSLATIONS = ("kjv", "jesuit")
TRANSLATION_LABELS = {
    "kjv": "King James Version",
    "jesuit": "الترجمة اليسوعية الكاثوليكية",
}
# Short tag used inside "Copy verse" strings.
TRANSLATION_TAGS = {"kjv": "KJV", "jesuit": "Jesuit"}
# Cookie written by static/js/settings.js whenever the reader picks a text.
TRANSLATION_COOKIE = "selah_translation"


def current_translation() -> str:
    """The translation the reader chose (kept in a cookie so HTMX partials
    and full page loads agree without rewriting every URL)."""
    key = (request.cookies.get(TRANSLATION_COOKIE) or "").strip()
    return key if key in TRANSLATIONS else "kjv"


def wants_partial() -> bool:
    """True when HTMX asks for a fragment.

    History-restore requests carry HX-Request too, but must receive the full
    page so htmx can rebuild the document body.
    """
    if not request.headers.get("HX-Request"):
        return False
    return not request.headers.get("HX-History-Restore-Request")


def load_chapter(slug: str, chapter: int, focus: int | None = None) -> dict:
    conn = database.get_db()
    book = database.get_book(conn, slug)
    if book is None:
        abort(404)
    if not 1 <= chapter <= book["chapter_count"]:
        abort(404)
    translation = current_translation()
    verses = database.get_verses(conn, book["id"], chapter, translation)
    if focus is not None and not any(v["verse"] == focus for v in verses):
        focus = None
    return {
        "book": book,
        "chapter": chapter,
        "books": database.list_books(conn),
        "verses": verses,
        "focus": focus,
        "inline_notes": request.args.get("commentary") == "1",
        "prev_chapter": chapter - 1 if chapter > 1 else None,
        "next_chapter": chapter + 1 if chapter < book["chapter_count"] else None,
        "title": f"{book['name']} {chapter}",
        "translation": translation,
        "translation_label": TRANSLATION_LABELS[translation],
    }


# ---------------------------------------------------------------------------
# reference parsing + highlighting
# ---------------------------------------------------------------------------
REF_RE = re.compile(
    r"^(?P<book>[1-3]?\s*[A-Za-z][A-Za-z.' -]*?)\s+(?P<chapter>\d{1,3})(?::(?P<verse>\d{1,3}))?$"
)
TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def parse_reference(raw: str):
    """Turn 'john 3:16' / '1 cor 13' into {'book': row, 'chapter': n, 'verse': n}."""
    match = REF_RE.match(raw.strip())
    if not match:
        return None
    key = _norm(match.group("book"))
    if not key:
        return None
    conn = database.get_db()
    books = database.list_books(conn)

    def norm_book(b):
        return {_norm(b["slug"]), _norm(b["name"]), _norm(b["abbrev"])}

    found = next((b for b in books if key in norm_book(b)), None)
    if found is None and len(key) >= 3:
        partial = [b for b in books if _norm(b["name"]).startswith(key)]
        if len(partial) == 1:
            found = partial[0]
    if found is None:
        return None

    chapter = int(match.group("chapter"))
    if not 1 <= chapter <= found["chapter_count"]:
        return None

    verse = int(match.group("verse")) if match.group("verse") else None
    if verse is not None:
        exists = database.get_db().execute(
            "SELECT 1 FROM verses WHERE book_id = ? AND chapter = ? AND verse = ? AND translation = ?",
            (found["id"], chapter, verse, current_translation()),
        ).fetchone()
        if not exists:
            return None
    return {"book": found, "chapter": chapter, "verse": verse}


def highlight(text: str, terms: list[str]) -> str:
    """HTML-escape *text*, then wrap whole-word matches in <mark> tags.

    Each term is matched loosely around Arabic vocalisation marks, so a query
    typed as "مرحبا" still highlights "مَرْحَبًا" in the verse text.
    """
    escaped = html.escape(text)
    cleaned = sorted(
        {t.strip("'") for t in terms if len(t.strip("'")) >= 2},
        key=len,
        reverse=True,
    )
    if not cleaned:
        return escaped

    def term_pattern(term: str) -> str:
        # Each character of the term, plus any Arabic vocalisation marks that
        # sit on it ("م" matches "مَ"), with alef variants folded together.
        marks = f"(?:{database.AR_DIACRITICS_PATTERN})*"
        alef = "[" + re.escape(database.AR_ALEF) + "]"
        pieces = [
            (alef if ch in database.AR_ALEF else re.escape(ch)) + marks
            for ch in html.escape(term)
        ]
        return "".join(pieces) + marks

    # (?<![&\w]) keeps matches out of entities like &amp;; (?![\w]) keeps
    # whole-word semantics while still matching "lord" inside "lord's".
    pattern = re.compile(
        "(?<![&\\w])(?:" + "|".join(term_pattern(t) for t in cleaned) + r")(?![\w])",
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped)


def run_search(q: str, limit: int, translation: str = "kjv"):
    """Return (reference_or_None, highlighted rows, total_matches)."""
    conn = database.get_db()
    ref = parse_reference(q)
    # Fold Arabic vocalisation out of the query before matching: the full-text
    # index stores the same folded text.
    terms = TOKEN_RE.findall(database.normalize_search_text(q))

    rows: list = []
    total = 0
    if terms:
        match = " ".join(f'"{t}"*' for t in terms)
        try:
            total = database.fts_count(conn, match, translation)
            if total:
                rows = database.fts_search(conn, match, limit, translation)
        except sqlite3.OperationalError:
            rows, total = [], 0

    if not rows:
        needle = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{needle}%"
        total = database.like_count(conn, like, translation)
        rows = database.like_search(conn, like, limit, translation) if total else []

    out = [dict(row, html=highlight(row["text"], terms)) for row in rows]
    return ref, out, total


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("read_chapter", book="john", chapter=1))


@app.route("/read/<book>/<int:chapter>")
def read_chapter(book: str, chapter: int):
    focus = request.args.get("focus", type=int)
    payload = load_chapter(book, chapter, focus)
    if wants_partial():
        return render_template("_chapter.html", **payload)
    return render_template("index.html", **payload, page_title=f"{payload['title']} · Selah")


@app.route("/search")
def search_route():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        if wants_partial():
            return ""
        return render_template("search.html", q="", ref=None, rows=[], total=0)

    limit = 12 if wants_partial() else 100
    ref, rows, total = run_search(q, limit, current_translation())
    if wants_partial():
        return render_template("_search_results.html", q=q, ref=ref, rows=rows, total=total)
    return render_template("search.html", q=q, ref=ref, rows=rows, total=total)


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------
@app.route("/partials/book-grid")
def book_grid():
    current = request.args.get("book", "")
    return render_template("_book_grid.html", books=database.list_books(database.get_db()), current=current)


@app.route("/partials/chapter-grid/<book>")
def chapter_grid(book: str):
    row = database.get_book(database.get_db(), book)
    if row is None:
        abort(404)
    current = request.args.get("chapter", type=int) or 1
    return render_template("_chapter_grid.html", book=row, chapter=current)


@app.route("/partials/verse/<int:verse_id>")
def verse_partial(verse_id: int):
    conn = database.get_db()
    verse = database.get_verse(conn, verse_id)
    if verse is None:
        abort(404)
    return render_template(
        "_verse_drawer.html",
        verse=verse,
        commentary=database.get_commentary(conn, verse_id),
        notes=database.get_notes(conn, verse_id),
        translation_label=TRANSLATION_LABELS.get(verse["translation"], TRANSLATION_LABELS["kjv"]),
        translation_tag=TRANSLATION_TAGS.get(verse["translation"], TRANSLATION_TAGS["kjv"]),
    )


@app.route("/partials/note/<int:verse_id>")
def inline_note(verse_id: int):
    return render_template("_inline_note.html", commentary=database.get_commentary(database.get_db(), verse_id))


@app.route("/partials/random-verse")
def random_verse_partial():
    """A single random verse — the prayer tool refreshes this every minute."""
    return render_template(
        "_random_verse.html",
        prayer_verse=database.random_verse(database.get_db(), current_translation()),
    )


@app.route("/partials/all-notes")
def all_notes_partial():
    """Every saved note with its reference — the notes manager in the nav drawer."""
    return render_template("_all_notes.html", notes=database.list_all_notes(database.get_db()))


# ---------------------------------------------------------------------------
# notes (user-written, stored in SQLite)
# ---------------------------------------------------------------------------
@app.post("/verses/<int:verse_id>/notes")
def add_note(verse_id: int):
    conn = database.get_db()
    verse = database.get_verse(conn, verse_id)
    if verse is None:
        abort(404)
    body = request.form.get("body", "").strip()
    if not body:
        return ("", 422)
    note_id = database.insert_note(conn, verse_id, body)
    if not wants_partial():
        # No-JS fallback: save, then return to the chapter.
        url = url_for("read_chapter", book=verse["slug"], chapter=verse["chapter"])
        return redirect(f"{url}?focus={verse['verse']}")
    note = database.get_note(conn, note_id)
    return render_template("_note_item.html", note=note)


@app.delete("/notes/<int:note_id>")
def delete_note(note_id: int):
    if not database.delete_note(database.get_db(), note_id):
        abort(404)
    return ""


# ---------------------------------------------------------------------------
# errors / shared context
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


@app.context_processor
def inject_stats():
    conn = database.get_db()
    return {
        "stats": database.get_stats(conn),
        # server-rendered so the prayer tool has a verse before HTMX ticks
        "prayer_verse": database.random_verse(conn, current_translation()),
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
