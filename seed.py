"""Create and seed data/bible.db.

    python seed.py            # build (refuses to overwrite an existing db)
    python seed.py --force    # rebuild from scratch

Source text: King James Version (public domain), bundled as data/kjv.json,
plus an Arabic text (Ketab El Hayat, Smith & Van Dyck translation) bundled as
data/arabic.json. If a bundle is missing it is downloaded once from
https://github.com/thiagobodruk/bible (en_kjv.json / ar_kehm.json).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import db as database

BASE_DIR = Path(__file__).resolve().parent
SOURCE_JSON = BASE_DIR / "data" / "kjv.json"
SOURCE_URL = "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/en_kjv.json"

# Arabic source: same project, same canonical book order. Stored under the
# UI's "jesuit" translation key (see app.TRANSLATIONS).
ARABIC_JSON = BASE_DIR / "data" / "arabic.json"
ARABIC_URL = "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/ar_kehm.json"
ARABIC_TRANSLATION = "jesuit"
ARABIC_NAME = "Ketab El Hayat (Smith & Van Dyck)"

# Canonical 66 books, in the same order as the source JSON.
BOOKS = [
    ("genesis", "Genesis", "Gen", "OT"),
    ("exodus", "Exodus", "Ex", "OT"),
    ("leviticus", "Leviticus", "Lev", "OT"),
    ("numbers", "Numbers", "Num", "OT"),
    ("deuteronomy", "Deuteronomy", "Deut", "OT"),
    ("joshua", "Joshua", "Josh", "OT"),
    ("judges", "Judges", "Judg", "OT"),
    ("ruth", "Ruth", "Ruth", "OT"),
    ("1-samuel", "1 Samuel", "1 Sam", "OT"),
    ("2-samuel", "2 Samuel", "2 Sam", "OT"),
    ("1-kings", "1 Kings", "1 Kgs", "OT"),
    ("2-kings", "2 Kings", "2 Kgs", "OT"),
    ("1-chronicles", "1 Chronicles", "1 Chr", "OT"),
    ("2-chronicles", "2 Chronicles", "2 Chr", "OT"),
    ("ezra", "Ezra", "Ezra", "OT"),
    ("nehemiah", "Nehemiah", "Neh", "OT"),
    ("esther", "Esther", "Esth", "OT"),
    ("job", "Job", "Job", "OT"),
    ("psalms", "Psalms", "Ps", "OT"),
    ("proverbs", "Proverbs", "Prov", "OT"),
    ("ecclesiastes", "Ecclesiastes", "Eccl", "OT"),
    ("song-of-solomon", "Song of Solomon", "Song", "OT"),
    ("isaiah", "Isaiah", "Isa", "OT"),
    ("jeremiah", "Jeremiah", "Jer", "OT"),
    ("lamentations", "Lamentations", "Lam", "OT"),
    ("ezekiel", "Ezekiel", "Ezek", "OT"),
    ("daniel", "Daniel", "Dan", "OT"),
    ("hosea", "Hosea", "Hos", "OT"),
    ("joel", "Joel", "Joel", "OT"),
    ("amos", "Amos", "Amos", "OT"),
    ("obadiah", "Obadiah", "Obad", "OT"),
    ("jonah", "Jonah", "Jonah", "OT"),
    ("micah", "Micah", "Mic", "OT"),
    ("nahum", "Nahum", "Nah", "OT"),
    ("habakkuk", "Habakkuk", "Hab", "OT"),
    ("zephaniah", "Zephaniah", "Zeph", "OT"),
    ("haggai", "Haggai", "Hag", "OT"),
    ("zechariah", "Zechariah", "Zech", "OT"),
    ("malachi", "Malachi", "Mal", "OT"),
    ("matthew", "Matthew", "Matt", "NT"),
    ("mark", "Mark", "Mark", "NT"),
    ("luke", "Luke", "Luke", "NT"),
    ("john", "John", "John", "NT"),
    ("acts", "Acts", "Acts", "NT"),
    ("romans", "Romans", "Rom", "NT"),
    ("1-corinthians", "1 Corinthians", "1 Cor", "NT"),
    ("2-corinthians", "2 Corinthians", "2 Cor", "NT"),
    ("galatians", "Galatians", "Gal", "NT"),
    ("ephesians", "Ephesians", "Eph", "NT"),
    ("philippians", "Philippians", "Phil", "NT"),
    ("colossians", "Colossians", "Col", "NT"),
    ("1-thessalonians", "1 Thessalonians", "1 Thess", "NT"),
    ("2-thessalonians", "2 Thessalonians", "2 Thess", "NT"),
    ("1-timothy", "1 Timothy", "1 Tim", "NT"),
    ("2-timothy", "2 Timothy", "2 Tim", "NT"),
    ("titus", "Titus", "Titus", "NT"),
    ("philemon", "Philemon", "Phlm", "NT"),
    ("hebrews", "Hebrews", "Heb", "NT"),
    ("james", "James", "Jas", "NT"),
    ("1-peter", "1 Peter", "1 Pet", "NT"),
    ("2-peter", "2 Peter", "2 Pet", "NT"),
    ("1-john", "1 John", "1 John", "NT"),
    ("2-john", "2 John", "2 John", "NT"),
    ("3-john", "3 John", "3 John", "NT"),
    ("jude", "Jude", "Jude", "NT"),
    ("revelation", "Revelation", "Rev", "NT"),
]

SCHEMA = """
CREATE TABLE books (
    id           INTEGER PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    abbrev       TEXT NOT NULL,
    testament    TEXT NOT NULL CHECK (testament IN ('OT', 'NT')),
    sort_order   INTEGER NOT NULL UNIQUE,
    chapter_count INTEGER NOT NULL
);

CREATE TABLE verses (
    id      INTEGER PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    chapter INTEGER NOT NULL,
    verse   INTEGER NOT NULL,
    text    TEXT NOT NULL,
    translation TEXT NOT NULL DEFAULT 'kjv',
    UNIQUE (book_id, chapter, verse, translation)
);
CREATE INDEX idx_verses_ref ON verses (book_id, chapter, verse, translation);

CREATE TABLE commentaries (
    id       INTEGER PRIMARY KEY,
    verse_id INTEGER NOT NULL REFERENCES verses(id) ON DELETE CASCADE,
    title    TEXT NOT NULL,
    body     TEXT NOT NULL
);
CREATE INDEX idx_commentaries_verse ON commentaries (verse_id);

CREATE TABLE notes (
    id         INTEGER PRIMARY KEY,
    verse_id   INTEGER NOT NULL REFERENCES verses(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_notes_verse ON notes (verse_id);

-- Full-text index over every translation. It stores a diacritics-folded copy
-- of each verse (db.normalize_search_text) so Arabic matches a query typed without
-- vocalisation marks. `verses` rows are never edited at runtime, so the index
-- is written once after seeding instead of being kept in sync by triggers;
-- rowids match verses.id.
CREATE VIRTUAL TABLE verses_fts USING fts5(
    text,
    tokenize = "unicode61 remove_diacritics 2"
);
"""

# Curated study notes, keyed by (slug, chapter, verse).
COMMENTARY = [
    ("genesis", 1, 1, "A beginning without a beginning",
     "The Bible opens by simply asserting God's existence rather than arguing for it. Time, space and matter "
     "are spoken into being by a personal Creator -- a claim the rest of Scripture assumes and the gospel "
     "depends on."),
    ("genesis", 1, 3, "Light before the sun",
     "Light exists on day one; the sun is made on day four. The text quietly insists that the source of all "
     "light and life is God himself, which John picks up when he calls Christ the light of men."),
    ("exodus", 20, 3, "No other gods before me",
     "The first commandment orders loyalty before it orders behaviour. \"Before me\" means in God's presence: "
     "all of life is lived openly before his face, and nothing may take the place of his claim on us."),
    ("deuteronomy", 6, 4, "The Shema",
     "Israel's creed: one Lord, one whole-hearted love. Jesus calls this the greatest commandment "
     "(Mark 12:29-30), and it frames every later discussion of what it means to love God."),
    ("psalms", 23, 1, "\"The Lord is my shepherd\"",
     "The possessive \"my\" is the heart of the psalm -- not a distant deity but a shepherd who knows his "
     "sheep. Because he tends David, he can honestly say, \"I shall not want.\""),
    ("psalms", 23, 4, "Through the valley",
     "Note the shift in address: David walks into darkness speaking of God in the third person, then to God "
     "in the second -- \"thou art with me.\" The path goes through the valley, not around it."),
    ("psalms", 46, 1, "A very present help",
     "Literally, help found very much in distress. God is not most distant when trouble is nearest; the "
     "psalmist answers fear with the settled fact of God's near presence."),
    ("psalms", 119, 105, "A lamp to my feet",
     "A lamp in the ancient world lit the next step, not the whole road. Scripture guides conduct -- the "
     "feet -- one faithful step at a time rather than handing us a map of everything."),
    ("isaiah", 40, 31, "Wings like eagles",
     "Waiting here is leaning, not idling. An eagle does not flap against the wind; it mounts the thermal. "
     "Strength is renewed for those who stop striving in their own power and trust God's timing."),
    ("isaiah", 53, 5, "Wounded for our transgressions",
     "The suffering servant absorbs a debt he did not incur: \"the chastisement of our peace was upon him.\" "
     "Peter quotes this verse to explain Christ's atoning death (1 Peter 2:24)."),
    ("jeremiah", 29, 11, "Thoughts of peace",
     "Written to exiles in Babylon, told to build houses and pray for their city. The promise of a future "
     "and a hope comes with a seventy-year clock -- God's plans include patience."),
    ("matthew", 5, 9, "Blessed are the peacemakers",
     "Not merely peacekeepers who avoid conflict, but peacemakers who reconcile -- enemies to God and to one "
     "another. Such people are called sons of God because they resemble their Father."),
    ("matthew", 6, 33, "Seek ye first",
     "Anxiety is answered with ordering, not just reassurance. The kingdom is not one concern among many "
     "but the organising centre; everything else falls into place behind it."),
    ("matthew", 28, 19, "All power is given unto me",
     "The Great Commission rests on Christ's authority, not our competence. Going, baptising and teaching "
     "are the church's marching orders -- until he is seen again."),
    ("john", 1, 1, "The Word was God",
     "Three escalating claims: the Word was with God, was God, and made all things. Verse 14 then pins "
     "that eternity to a manger -- the Word became flesh and dwelt among us."),
    ("john", 3, 16, "God so loved the world",
     "\"World\" means the whole fallen order of humanity, not an abstraction. The one-of-a-kind Son is "
     "given, belief receives, and everlasting life stands directly beside perishing."),
    ("john", 14, 6, "The way, the truth, the life",
     "An exclusive claim made gently by someone about to die for his hearers. Way gives direction, truth "
     "gives content, life gives power -- and no one comes to the Father apart from him."),
    ("romans", 8, 28, "All things work together",
     "Not that all things are good, but that God weaves all things together for good -- and the promise "
     "names its audience: those who love him and are called according to his purpose."),
    ("romans", 12, 2, "Transformed by renewing the mind",
     "Transformation begins in thinking, not mere behaviour. A mind renewed by Scripture stops agreeing "
     "with the age's assumptions and discovers God's good, acceptable and perfect will."),
    ("1-corinthians", 13, 4, "Charity suffereth long",
     "The KJV's \"charity\" is agape -- love defined by verbs of patience and humility rather than "
     "feeling. Verse 7 adds that it bears, believes, hopes and endures through everything."),
    ("philippians", 4, 6, "Be careful for nothing",
     "\"Careful\" here means consumed with care. The remedy is prayer with thanksgiving, and the result "
     "is specific: God's peace will guard heart and mind like a sentinel."),
    ("philippians", 4, 13, "I can do all things",
     "In context Paul is talking about plenty and want alike (vv. 12-13). Christ's strength is given for "
     "every situation he calls us into -- sufficiency, not necessarily success."),
    ("hebrews", 11, 1, "Faith is the substance",
     "Substance is the ground on which hoped-for things are built; evidence is the title-deed of things "
     "not yet seen. Faith does not guess -- it receives the unseen as real."),
    ("james", 1, 2, "Count it all joy",
     "Temptation here is testing, and joy is an act of arithmetic: trials are counted as gain because "
     "they produce steadfastness -- and steadfastness matures (vv. 3-4)."),
    ("1-peter", 5, 7, "Casting all your care",
     "The verb is a once-for-all throw, not a daily trickle. The reason follows: \"he careth for you\" -- "
     "God is not indifferent to the smallest anxieties of his people."),
    ("1-john", 1, 9, "Faithful and just to forgive",
     "Forgiveness here is a promise rather than a favour, because it rests on justice already satisfied "
     "at the cross. Confession simply agrees with God about what he has already dealt with."),
    ("revelation", 21, 4, "God shall wipe away all tears",
     "The Bible's story ends with God close to his people: no more death, sorrow, crying or pain. The "
     "same hand that formed the world in Genesis 1 gently wipes every tear."),
]

_PUNCT = re.compile(r"\s+([,.;:!?])")
_SPACES = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Fix spacing artifacts in the source JSON (e.g. 'the LORD , and')."""
    t = text.replace("\u00a0", " ")
    t = _PUNCT.sub(r"\1", t)
    t = t.replace("( ", "(").replace(" )", ")")
    return _SPACES.sub(" ", t).strip()


def fetch_source(path: Path, url: str = SOURCE_URL, label: str = "KJV") -> Path:
    if path.exists():
        return path
    print(f"Downloading {label} source to {path} ...")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(path, "wb") as fh:
            fh.write(resp.read())
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise SystemExit(f"Could not download {label} source from {url}: {exc}") from exc
    return path


def load_json(path: Path, url: str, label: str) -> list:
    with open(fetch_source(path, url, label), encoding="utf-8") as fh:
        raw = json.load(fh)
    if len(raw) != len(BOOKS):
        raise SystemExit(f"Expected {len(BOOKS)} books in {label} source, found {len(raw)}")
    return raw


def build(
    db_path: Path | None = None,
    source: Path | None = None,
    arabic: Path | None = None,
    force: bool = False,
) -> Path:
    db_path = Path(db_path or database.DB_PATH)
    if db_path.exists():
        if not force:
            print(f"{db_path} already exists (use --force to rebuild).")
            return db_path
        db_path.unlink()

    raw = load_json(Path(source or SOURCE_JSON), SOURCE_URL, "KJV")
    arabic_raw = load_json(
        Path(arabic or ARABIC_JSON), ARABIC_URL, f"Arabic ({ARABIC_NAME})"
    )

    conn = database.connect(db_path)
    try:
        conn.executescript(SCHEMA)

        books = []
        for order, ((slug, name, abbrev, testament), src) in enumerate(zip(BOOKS, raw), start=1):
            chapters = src["chapters"]
            books.append((slug, name, abbrev, testament, order, len(chapters)))

        conn.executemany(
            "INSERT INTO books (slug, name, abbrev, testament, sort_order, chapter_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            books,
        )

        book_ids = {
            row["slug"]: row["id"]
            for row in conn.execute("SELECT id, slug FROM books")
        }

        # English (KJV) verses.
        verse_rows = []
        for (slug, _name, _abbrev, _testament), src in zip(BOOKS, raw):
            book_id = book_ids[slug]
            for chapter_no, chapter in enumerate(src["chapters"], start=1):
                for verse_no, verse_text in enumerate(chapter, start=1):
                    verse_rows.append(
                        (book_id, chapter_no, verse_no, clean_text(verse_text), "kjv")
                    )
        conn.executemany(
            "INSERT INTO verses (book_id, chapter, verse, text, translation) VALUES (?, ?, ?, ?, ?)",
            verse_rows,
        )

        # Arabic verses: same canonical book order, same chapter layout. A few
        # chapters number their verses slightly differently from the KJV -- that
        # is recorded, not fatal.
        chapter_totals = {slug: [len(c) for c in src["chapters"]] for (slug, *_), src in zip(BOOKS, raw)}
        arabic_rows = []
        renumbered = []
        for (slug, _name, _abbrev, _testament), src in zip(BOOKS, arabic_raw):
            book_id = book_ids[slug]
            chapters = src["chapters"]
            expected = chapter_totals[slug]
            if len(chapters) != len(expected):
                raise SystemExit(
                    f"Arabic source: {slug} has {len(chapters)} chapters, expected {len(expected)}"
                )
            for chapter_no, chapter in enumerate(chapters, start=1):
                if len(chapter) != expected[chapter_no - 1]:
                    renumbered.append(
                        f"{slug} {chapter_no} ({expected[chapter_no - 1]} KJV / {len(chapter)} Arabic)"
                    )
                for verse_no, verse_text in enumerate(chapter, start=1):
                    arabic_rows.append(
                        (book_id, chapter_no, verse_no, clean_text(verse_text), ARABIC_TRANSLATION)
                    )
        conn.executemany(
            "INSERT INTO verses (book_id, chapter, verse, text, translation) VALUES (?, ?, ?, ?, ?)",
            arabic_rows,
        )
        if renumbered:
            print(f"  note: verse numbering differs in {len(renumbered)} chapter(s): {', '.join(renumbered)}")

        # Curated commentary, attached to every translation's copy of a verse
        # (only references that exist are inserted).
        inserted = 0
        for slug, chapter, verse, title, body in COMMENTARY:
            rows = conn.execute(
                "SELECT v.id FROM verses v JOIN books b ON b.id = v.book_id "
                "WHERE b.slug = ? AND v.chapter = ? AND v.verse = ?",
                (slug, chapter, verse),
            ).fetchall()
            if not rows:
                print(f"  ! commentary target missing: {slug} {chapter}:{verse}")
                continue
            for row in rows:
                conn.execute(
                    "INSERT INTO commentaries (verse_id, title, body) VALUES (?, ?, ?)",
                    (row["id"], title, body),
                )
                inserted += 1

        # Full-text index: one row per verse, diacritics folded out so Arabic
        # can be searched as it is typed (see db.normalize_search_text).
        conn.executemany(
            "INSERT INTO verses_fts (rowid, text) VALUES (?, ?)",
            [
                (row["id"], database.normalize_search_text(row["text"]))
                for row in conn.execute("SELECT id, text FROM verses ORDER BY id")
            ],
        )

        conn.commit()

        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"Integrity check failed: {integrity}")

        by_translation = dict(
            conn.execute("SELECT translation, COUNT(*) FROM verses GROUP BY translation")
        )
        counts = {
            "books": conn.execute("SELECT COUNT(*) FROM books").fetchone()[0],
            "verses": conn.execute(
                "SELECT COUNT(*) FROM verses WHERE translation = 'kjv'"
            ).fetchone()[0],
            "indexed": conn.execute("SELECT COUNT(*) FROM verses_fts").fetchone()[0],
            "commentaries": conn.execute("SELECT COUNT(*) FROM commentaries").fetchone()[0],
        }
        print(
            f"Seeded {db_path} -- {counts['books']} books, {counts['verses']} verse references "
            f"({by_translation.get('kjv', 0)} KJV + {by_translation.get(ARABIC_TRANSLATION, 0)} "
            f"Arabic rows), {counts['indexed']} indexed, {counts['commentaries']} commentary notes."
        )
    finally:
        conn.close()
    return db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Selah SQLite database.")
    parser.add_argument("--force", action="store_true", help="rebuild even if the database exists")
    parser.add_argument("--db", default=None, help="database path (default: data/bible.db)")
    parser.add_argument("--source", default=None, help="path to KJV JSON source")
    parser.add_argument("--arabic", default=None, help="path to Arabic JSON source")
    args = parser.parse_args()
    build(
        db_path=Path(args.db) if args.db else None,
        source=Path(args.source) if args.source else None,
        arabic=Path(args.arabic) if args.arabic else None,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())
