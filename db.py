"""SQLite data access for Selah.

A single connection per Flask request, queried directly with the stdlib
``sqlite3`` module -- no ORM, no background services.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from flask import g

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SELAH_DB") or (BASE_DIR / "data" / "bible.db"))

# Arabic vocalisation / annotation marks (harakat, tanween, shadda, ...).
AR_DIACRITICS_PATTERN = "[\\u0610-\\u061A\\u064B-\\u065F\\u0670\\u06D6-\\u06ED]"
AR_DIACRITICS = re.compile(AR_DIACRITICS_PATTERN)
# Alef variants (plain, hamza, madda, wasla) all fold to a plain alef so
# "الأرض" and "الارض" find each other.
AR_ALEF = "\u0627\u0623\u0625\u0622\u0671"  # ا أ إ آ ٱ
_AR_ALEF_MAP = str.maketrans({codepoint: "\u0627" for codepoint in AR_ALEF})


def normalize_search_text(text: str) -> str:
    """Fold *text* to its search form: Arabic vocalisation marks removed and
    alef variants collapsed, so a query typed without harakat still matches
    fully vocalised scripture ("مرحبا" finds "مَرْحَبًا", "الارض" finds
    "الأَرْضِ"). Latin text passes through untouched.
    """
    if not text:
        return text
    return AR_DIACRITICS.sub("", text).translate(_AR_ALEF_MAP)


# ---------------------------------------------------------------------------
# connection handling
# ---------------------------------------------------------------------------
def connect(path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    """Return the connection for the current request (created on demand)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)


# ---------------------------------------------------------------------------
# books / chapters / verses
# ---------------------------------------------------------------------------
def list_books(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM books ORDER BY sort_order").fetchall()


def get_book(conn: sqlite3.Connection, slug: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM books WHERE slug = ?", (slug,)).fetchone()


def get_verses(
    conn: sqlite3.Connection, book_id: int, chapter: int, translation: str = "kjv"
) -> list[sqlite3.Row]:
    """Verses of one chapter in *translation*, flagged when commentary exists."""
    return conn.execute(
        """
        SELECT v.id, v.verse, v.text,
               EXISTS(SELECT 1 FROM commentaries c WHERE c.verse_id = v.id) AS has_note
        FROM verses v
        WHERE v.book_id = ? AND v.chapter = ? AND v.translation = ?
        ORDER BY v.verse
        """,
        (book_id, chapter, translation),
    ).fetchall()


def get_verse(conn: sqlite3.Connection, verse_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT v.id, v.chapter, v.verse, v.text, v.translation, b.slug, b.name AS book_name
        FROM verses v JOIN books b ON b.id = v.book_id
        WHERE v.id = ?
        """,
        (verse_id,),
    ).fetchone()


# ---------------------------------------------------------------------------
# commentary / notes
# ---------------------------------------------------------------------------
def get_commentary(conn: sqlite3.Connection, verse_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, body FROM commentaries WHERE verse_id = ? ORDER BY id",
        (verse_id,),
    ).fetchall()


def get_notes(conn: sqlite3.Connection, verse_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, body, created_at FROM notes WHERE verse_id = ? ORDER BY created_at DESC, id DESC",
        (verse_id,),
    ).fetchall()


def insert_note(conn: sqlite3.Connection, verse_id: int, body: str) -> int:
    cur = conn.execute("INSERT INTO notes (verse_id, body) VALUES (?, ?)", (verse_id, body))
    conn.commit()
    return int(cur.lastrowid)


def get_note(conn: sqlite3.Connection, note_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT id, body, created_at FROM notes WHERE id = ?", (note_id,)).fetchone()


def delete_note(conn: sqlite3.Connection, note_id: int) -> bool:
    cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()
    return cur.rowcount > 0


def random_verse(conn: sqlite3.Connection, translation: str = "kjv") -> sqlite3.Row | None:
    """One verse picked at random (with its reference) — feeds the prayer tool."""
    return conn.execute(
        """
        SELECT v.text, v.chapter, v.verse, v.translation, b.name AS book_name, b.slug
        FROM verses v JOIN books b ON b.id = v.book_id
        WHERE v.translation = ?
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (translation,),
    ).fetchone()


def list_all_notes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every saved note, newest first, joined to its verse reference."""
    return conn.execute(
        """
        SELECT n.id, n.body, n.created_at,
               b.slug, b.name AS book_name, v.chapter, v.verse
        FROM notes n
        JOIN verses v ON v.id = n.verse_id
        JOIN books b ON b.id = v.book_id
        ORDER BY n.created_at DESC, n.id DESC
        """
    ).fetchall()


# ---------------------------------------------------------------------------
# search (FTS5 with a LIKE fallback)
# ---------------------------------------------------------------------------
def fts_count(conn: sqlite3.Connection, match: str, translation: str = "kjv") -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM verses_fts JOIN verses v ON v.id = verses_fts.rowid
            WHERE verses_fts MATCH ? AND v.translation = ?
            """,
            (match, translation),
        ).fetchone()[0]
    )


def fts_search(conn: sqlite3.Connection, match: str, limit: int, translation: str = "kjv") -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT v.id, b.slug, b.name AS book_name, v.chapter, v.verse, v.text
        FROM verses_fts
        JOIN verses v ON v.id = verses_fts.rowid
        JOIN books b ON b.id = v.book_id
        WHERE verses_fts MATCH ? AND v.translation = ?
        ORDER BY rank
        LIMIT ?
        """,
        (match, translation, limit),
    ).fetchall()


def like_count(conn: sqlite3.Connection, like: str, translation: str = "kjv") -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM verses WHERE text LIKE ? ESCAPE '\\' AND translation = ?",
            (like, translation),
        ).fetchone()[0]
    )


def like_search(conn: sqlite3.Connection, like: str, limit: int, translation: str = "kjv") -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT v.id, b.slug, b.name AS book_name, v.chapter, v.verse, v.text
        FROM verses v JOIN books b ON b.id = v.book_id
        WHERE v.text LIKE ? ESCAPE '\\' AND v.translation = ?
        ORDER BY b.sort_order, v.chapter, v.verse
        LIMIT ?
        """,
        (like, translation, limit),
    ).fetchall()


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
def get_stats(conn: sqlite3.Connection) -> dict:
    cached = getattr(g, "stats", None)
    if cached is not None:
        return cached
    stats = {
        "books": int(conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]),
        # verse *references*, not rows: each translation repeats them (the
        # KJV set is the canonical count shown in the footer)
        "verses": int(conn.execute("SELECT COUNT(*) FROM verses WHERE translation = 'kjv'").fetchone()[0]),
        "commentaries": int(conn.execute("SELECT COUNT(*) FROM commentaries").fetchone()[0]),
    }
    g.stats = stats
    return stats
