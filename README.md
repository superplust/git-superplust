# Selah — a quiet Bible reader

A modern, responsive, interactive Bible web application built with **Python (Flask)**,
**SQLite**, **HTMX**, **Tailwind CSS**, and a pinch of vanilla JavaScript.

Soft, parchment-toned palette · distraction-free long-form typography · instant
chapter switching, search, and study notes without full page reloads.

## Quick start

```bash
pip install -r requirements.txt   # just Flask
python seed.py                    # optional — the app auto-seeds on first run
python app.py                     # http://127.0.0.1:5000
```

The database is built at `data/bible.db` from the bundled public-domain King James
Version text (`data/kjv.json`, 66 books · 31,102 verses) plus a curated set of
study commentary notes.

Run the tests:

```bash
python -m unittest discover -s tests          # server-side suite (24 checks)
python tests/e2e_browser.py                  # full UI run in headless Firefox (49 checks;
                                             # needs firefox + geckodriver + selenium, app running)
python tests/e2e_features.py                 # settings drawer, translations, lexicon,
                                             # dark mode & reminders (59 checks)
```

## Features

- **Fast search** — debounced HTMX search across every verse (SQLite FTS5 with a
  `LIKE` fallback), matches highlighted in-line, plus reference jumps
  (`John 3:16`, `1 cor 13`, `psalm 23`). Press Enter for the full results page.
- **Chapter navigation** — sticky Previous/Next controls, book & chapter picker
  panels, end-of-chapter cards, and browser back/forward support
  (`hx-push-url`). Every chapter link still works without JavaScript.
- **Verse detail drawer** — tap any verse number (or the verse itself) for a
  bottom sheet / side drawer with commentary, copy-to-clipboard, and private
  notes stored in SQLite (add & delete over HTMX).
- **Inline commentary toggles** — the toolbar *Notes* flag re-renders the chapter
  with collapsible study notes under the verses that have them.
- **Translation selector** — the toolbar/eyebrow dropdown offers *King James
  Version (KJV)* and *الترجمة اليسوعية الكاثوليكية (Jesuit)*; the choice is kept
  in `localStorage` (bundled texts are still KJV only).
- **Settings drawer** — click the top-left *Selah* logo for typography (font
  size, word spacing, family), light/dark mode, scripture colour, a custom word
  highlighter (e.g. “God” in green), a daily-reminder toggle, a notes manager, a
  Wikipedia lexicon search, and a prayer/reminder tool whose random verse
  refreshes every minute.
- **Verse drawer tabs** — *Notes* and *Lexicon*; the Lexicon tab looks the
  selected word up on Wikipedia and shows a short summary with a link through.
- **Dark mode** — a complete dark palette driven by CSS variables, persisted in
  `localStorage` and applied before first paint.
- **Mobile-first & responsive** — viewport-aware layout from 320 px phones to
  desktop; drawers become bottom sheets on mobile and side panels on desktop.
- **Reading-first typography** — Georgia/serif scripture at a comfortable
  measure, verse-number affordances, focus flash when arriving from search,
  smooth scrolling, print styles, and reduced-motion support.

## Architecture

```
app.py           Flask routes: full pages vs HTMX fragments (HX-Request),
                 reference parsing, search + highlighting
db.py            sqlite3 connection-per-request + queries (no ORM)
seed.py          schema, KJV import, curated commentary
templates/
  base.html        shell: header, search, footer, drawer scaffolding
  index.html       reader page → #chapter-outlet
  _chapter.html    chapter partial (toolbar, verses, navigation)
  _book_grid.html  _chapter_grid.html   picker panels
  _search_results.html  _search_hit.html  search page/panel
  _verse_drawer.html    _note_item.html   _inline_note.html
static/
  css/app.css      palette (light + dark), reading typography, drawer/panel design
  js/settings.js   persisted preferences (theme, typography, translation, reminders)
  js/app.js        UI glue: panels, both drawers, tabs, lexicon, highlighting
  js/htmx.min.js   vendored HTMX 1.9
  js/tailwind.js   vendored Tailwind Play CDN (dev build — see note)
data/
  bible.db         generated SQLite database
  kjv.json         bundled KJV source (public domain)
```

### One URL, two responses

`GET /read/<book>/<chapter>` answers a **full page** to normal requests and an
**HTML fragment** when HTMX sends `HX-Request: true` — history-restore requests
(`HX-History-Restore-Request`) deliberately get the full page back so HTMX can
rebuild the document. This keeps every link canonical, shareable, and
back-button friendly.

### Routes

| Route | Purpose |
| --- | --- |
| `/` | redirect to the default chapter |
| `/read/<book>/<chapter>` | reader page *or* chapter fragment (`HX-Request`) |
| `/search?q=` | search results page *or* dropdown fragment |
| `/partials/book-grid`, `/partials/chapter-grid/<book>` | picker panels |
| `/partials/verse/<id>` | verse drawer (commentary + notes) |
| `/partials/note/<id>` | inline commentary card |
| `POST /verses/<id>/notes`, `DELETE /notes/<id>` | private notes (SQLite) |

## Notes & trade-offs

- **Translation**: King James Version (public domain), imported from
  [thiagobodruk/bible](https://github.com/thiagobodruk/bible). Swap the source
  in `seed.py` if you prefer another public-domain text.
- **Tailwind**: vendored Play-CDN build so the app runs fully offline and
  restyles HTMX-injected markup with no build step. It prints a
  “don’t use in production” console warning; for production run the Tailwind
  CLI over `templates/` + `static/js/app.js` and drop `tailwind.js`.
- **Notes are local**: private notes live in SQLite on the server running the
  app; there are no accounts. The app is intended for local/personal use and
  does not implement CSRF protection or authentication.
- **Database path** defaults to `data/bible.db`; override with the `SELAH_DB`
  environment variable.
