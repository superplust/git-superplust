/* Selah — minimal vanilla JS glue.
 *
 * All content loading is done by HTMX (chapter swaps, search, drawer,
 * commentary, notes). This file manages UI state: panels, both drawers,
 * the translation selector, settings, the Wikipedia lexicon, reminders,
 * focus scrolling, clipboard copy, custom word highlighting and the
 * request progress bar. Persisted preferences live in static/js/settings.js. */
(function () {
  "use strict";

  var OUTLET = "#chapter-outlet";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function store() {
    return window.Selah || { state: {}, save: function (p) { return p; } };
  }

  function currentChapter() {
    var el = $(OUTLET + " > [data-book]");
    return el ? el.dataset : null;
  }

  /* ------------------------------------------------------------------ *
   * Toolbar panels (book picker / chapter picker / translation)
   * ------------------------------------------------------------------ */
  function closePanels() {
    $$(".panel").forEach(function (p) { p.classList.add("hidden"); });
    $$("[data-toggle-panel]").forEach(function (b) {
      b.setAttribute("aria-expanded", "false");
    });
  }

  function refreshPanel(panel) {
    if (panel.id !== "book-panel" && panel.id !== "chapter-panel") return;
    var cur = currentChapter();
    if (!cur) return;
    var stale =
      panel.dataset.book !== cur.book ||
      (panel.id === "chapter-panel" && panel.dataset.chapter !== cur.chapter);
    if (!stale) return;

    var body = $("[data-panel-body]", panel);
    if (!body || typeof htmx === "undefined") return;
    var url =
      panel.id === "book-panel"
        ? "/partials/book-grid?book=" + encodeURIComponent(cur.book)
        : "/partials/chapter-grid/" + encodeURIComponent(cur.book) +
          "?chapter=" + encodeURIComponent(cur.chapter);
    htmx.ajax("GET", url, { target: body, swap: "innerHTML" });
    panel.dataset.book = cur.book;
    panel.dataset.chapter = cur.chapter;
  }

  function openPanel(id) {
    var panel = document.getElementById(id);
    if (!panel) return;
    var wasOpen = !panel.classList.contains("hidden");
    closePanels();
    if (wasOpen) return;
    panel.classList.remove("hidden");
    var toggle = $('[data-toggle-panel="' + id + '"]');
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    refreshPanel(panel);
  }

  /* ------------------------------------------------------------------ *
   * Translation selector (texts are served from SQLite by cookie)
   * ------------------------------------------------------------------ */
  function applyTranslation() {
    var S = store();
    var key = (S.state && S.state.translation) || "kjv";
    var meta = (S.TRANSLATIONS && S.TRANSLATIONS[key]) || { short: "King James Version" };
    $$("[data-translation-label]").forEach(function (el) { el.textContent = meta.short; });
    $$(".translation-option").forEach(function (btn) {
      var on = btn.dataset.translation === key;
      btn.classList.toggle("is-current", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
  }

  function reloadChapter() {
    var cur = currentChapter();
    if (!cur || typeof htmx === "undefined") return;
    var url =
      "/read/" + encodeURIComponent(cur.book) + "/" + encodeURIComponent(cur.chapter) +
      (window.location.search || "");
    htmx.ajax("GET", url, { target: "#chapter-outlet", swap: "innerHTML" });
  }

  function refreshPrayerVerse() {
    var box = document.getElementById("prayer-verse");
    if (!box || typeof htmx === "undefined") return;
    var get = box.getAttribute("hx-get");
    if (get) htmx.ajax("GET", get, { target: box, swap: "innerHTML" });
  }

  function selectTranslation(key) {
    if (!window.Selah || !window.Selah.TRANSLATIONS[key]) return;
    var same = store().state && store().state.translation === key;
    store().save({ translation: key }); // save() writes the cookie before we refetch
    applyTranslation();
    closePanels();
    if (same) return;
    reloadChapter();
    refreshPrayerVerse();
  }

  /* ------------------------------------------------------------------ *
   * Verse drawer (bottom sheet on mobile, side panel on desktop)
   * ------------------------------------------------------------------ */
  var lastFocused = null;

  function openDrawer() {
    var drawer = document.getElementById("drawer");
    if (!drawer) return;
    if (!document.body.classList.contains("drawer-open")) {
      lastFocused = document.activeElement;
      document.body.classList.add("drawer-open");
      closeNav(true);
    }
    drawer.setAttribute("aria-hidden", "false");
    var closeBtn = $("[data-close-drawer]", drawer);
    if (closeBtn) closeBtn.focus({ preventScroll: true });
  }

  function closeDrawer() {
    if (!document.body.classList.contains("drawer-open")) return;
    document.body.classList.remove("drawer-open");
    var drawer = document.getElementById("drawer");
    if (drawer) drawer.setAttribute("aria-hidden", "true");
    if (lastFocused && document.contains(lastFocused)) {
      try { lastFocused.focus({ preventScroll: true }); } catch (e) { /* noop */ }
    }
    lastFocused = null;
  }

  function openVerse(verseId) {
    if (typeof htmx === "undefined") return;
    htmx.ajax("GET", "/partials/verse/" + verseId, {
      target: "#drawer",
      swap: "innerHTML",
    });
  }

  /* ------------------------------------------------------------------ *
   * Navigation / settings drawer (top-left Selah logo)
   * ------------------------------------------------------------------ */
  var navLastFocused = null;

  function openNav() {
    var nav = document.getElementById("nav-drawer");
    if (!nav) return;
    if (!document.body.classList.contains("nav-open")) {
      navLastFocused = document.activeElement;
      document.body.classList.add("nav-open");
      closeDrawer();
    }
    nav.setAttribute("aria-hidden", "false");
    var logo = document.getElementById("selah-logo");
    if (logo) logo.setAttribute("aria-expanded", "true");
    var closeBtn = $("[data-close-nav]", nav);
    if (closeBtn) closeBtn.focus({ preventScroll: true });
  }

  function closeNav(keepFocus) {
    if (!document.body.classList.contains("nav-open")) return;
    document.body.classList.remove("nav-open");
    var nav = document.getElementById("nav-drawer");
    if (nav) nav.setAttribute("aria-hidden", "true");
    var logo = document.getElementById("selah-logo");
    if (logo) logo.setAttribute("aria-expanded", "false");
    if (!keepFocus && logo && document.contains(logo)) {
      try { logo.focus({ preventScroll: true }); } catch (e) { /* noop */ }
    }
    navLastFocused = null;
  }

  /* ------------------------------------------------------------------ *
   * Verse drawer tabs (Notes | Lexicon)
   * ------------------------------------------------------------------ */
  function switchDrawerTab(name) {
    var drawer = document.getElementById("drawer");
    if (!drawer) return;
    $$(".drawer-tab", drawer).forEach(function (btn) {
      var on = btn.dataset.drawerTab === name;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    $$(".drawer-tabpanel", drawer).forEach(function (panel) {
      if (panel.dataset.tabPanel === name) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    });
    if (name === "lexicon") drawerLexiconLookup();
  }

  /* ------------------------------------------------------------------ *
   * Wikipedia lexicon (nav drawer + verse drawer tab)
   * ------------------------------------------------------------------ */
  var STOPWORDS = {
    the: 1, and: 1, for: 1, that: 1, with: 1, this: 1, from: 1, was: 1, are: 1,
    but: 1, not: 1, you: 1, your: 1, his: 1, her: 1, their: 1, they: 1, them: 1,
    hath: 1, shall: 1, will: 1, unto: 1, upon: 1, said: 1, thee: 1, thou: 1,
    thy: 1, ye: 1, have: 1, has: 1, had: 1, who: 1, whom: 1, which: 1, what: 1,
    when: 1, where: 1, how: 1, all: 1, any: 1, can: 1, may: 1, before: 1,
    after: 1, into: 1, out: 1, off: 1, over: 1, under: 1, our: 1, us: 1,
    we: 1, he: 1, she: 1, its: 1, were: 1, been: 1, both: 1, every: 1,
    through: 1, among: 1, there: 1, these: 1, those: 1, here: 1, king: 1,
  };

  function keywordFrom(text) {
    var words = String(text || "").match(/[A-Za-z][A-Za-z']{2,}/g) || [];
    for (var i = 0; i < words.length; i++) {
      if (!STOPWORDS[words[i].toLowerCase().replace(/^'+|'+$/g, "")]) return words[i];
    }
    return words[0] || "";
  }

  function clip(text, max) {
    var s = String(text || "").replace(/\s+/g, " ").trim();
    if (s.length <= max) return s;
    var cut = s.slice(0, max);
    var sp = cut.lastIndexOf(" ");
    return (sp > max * 0.6 ? cut.slice(0, sp) : cut).replace(/[,;:.]$/, "") + "…";
  }

  function wikiLookup(term) {
    var url =
      "https://en.wikipedia.org/w/api.php?action=query&format=json&origin=*" +
      "&redirects=1&generator=search&gsrlimit=1&prop=extracts&exintro=1" +
      "&explaintext=1&exsentences=4&exlimit=1&gsrsearch=" + encodeURIComponent(term);
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        var pages = data && data.query && data.query.pages;
        var ids = pages ? Object.keys(pages) : [];
        if (!ids.length) return null;
        var page = pages[ids[0]];
        if (!page || !page.title || page.missing !== undefined) return null;
        return {
          title: page.title,
          extract: String(page.extract || "").trim(),
          url: "https://en.wikipedia.org/wiki/" +
            encodeURIComponent(String(page.title).replace(/ /g, "_")),
        };
      });
  }

  function lexiconStatus(outEl, message) {
    outEl.textContent = "";
    var p = document.createElement("p");
    p.className = "lexicon-status";
    p.textContent = message;
    outEl.appendChild(p);
  }

  function runLexicon(raw, outEl) {
    if (!outEl) return;
    var term = String(raw || "").trim();
    if (term.length < 2) {
      lexiconStatus(outEl, "Type a word to look it up on Wikipedia.");
      return;
    }
    var req = String(Date.now()) + Math.random();
    outEl.dataset.req = req;
    lexiconStatus(outEl, "Searching Wikipedia…");
    wikiLookup(term)
      .then(function (result) {
        if (outEl.dataset.req !== req) return;
        outEl.textContent = "";
        if (!result) {
          lexiconStatus(outEl, "No Wikipedia entry found for “" + term + "”.");
          return;
        }
        var card = document.createElement("div");
        card.className = "lexicon-card";
        var title = document.createElement("h4");
        title.textContent = result.title;
        var snippet = document.createElement("p");
        snippet.className = "snippet";
        snippet.textContent = clip(result.extract, 260) || "No summary available.";
        var more = document.createElement("a");
        more.className = "more";
        more.href = result.url;
        more.target = "_blank";
        more.rel = "noopener";
        more.textContent = "More on Wikipedia →";
        card.appendChild(title);
        card.appendChild(snippet);
        card.appendChild(more);
        outEl.appendChild(card);
        if (outEl.id === "drawer-lexicon-out") {
          var owner = $("#drawer-lexicon-input");
          if (owner) owner.dataset.term = term;
        }
      })
      .catch(function () {
        if (outEl.dataset.req !== req) return;
        lexiconStatus(outEl, "Wikipedia could not be reached — check your connection.");
      });
  }

  function drawerLexiconLookup() {
    var panel = $("#drawer-panel-lexicon");
    var input = $("#drawer-lexicon-input");
    var out = $("#drawer-lexicon-out");
    if (!panel || !input || !out) return;
    if (!input.value.trim()) {
      var selection = String(window.getSelection ? window.getSelection() : "").trim();
      var term = selection && selection.length <= 40 ? selection : "";
      if (!term) term = keywordFrom(panel.dataset.lexiconVerse || panel.dataset.lexiconRef || "");
      if (!term) term = panel.dataset.lexiconRef || "";
      input.value = term;
    }
    // re-opening the tab for the same word keeps the result we already have
    if (input.dataset.term === input.value.trim() && $(".lexicon-card", out)) return;
    runLexicon(input.value, out);
  }

  /* ------------------------------------------------------------------ *
   * Custom word highlighting (Settings → Appearance)
   * ------------------------------------------------------------------ */
  function unwrapHighlights(root) {
    $$(".word-hl", root).forEach(function (span) {
      var parent = span.parentNode;
      if (!parent) return;
      parent.replaceChild(document.createTextNode(span.textContent), span);
      parent.normalize();
    });
  }

  function highlightRoot(root, term) {
    unwrapHighlights(root);
    if (!term) return;
    var esc = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    var re;
    try {
      re = new RegExp("(^|[^\\p{L}\\p{N}])(" + esc + ")(?![\\p{L}\\p{N}])", "giu");
    } catch (e) {
      re = new RegExp("(^|[^A-Za-z0-9])(" + esc + ")(?![A-Za-z0-9])", "gi");
    }
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach(function (node) {
      var text = node.nodeValue;
      if (!text) return;
      var frag = document.createDocumentFragment();
      var last = 0;
      var match;
      var found = false;
      re.lastIndex = 0;
      while ((match = re.exec(text)) !== null) {
        found = true;
        var start = match.index + match[1].length;
        frag.appendChild(document.createTextNode(text.slice(last, start)));
        var span = document.createElement("span");
        span.className = "word-hl";
        span.textContent = match[2];
        frag.appendChild(span);
        last = start + match[2].length;
        if (match[0].length === 0) re.lastIndex += 1;
      }
      if (!found || !node.parentNode) return;
      frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    });
  }

  function applyHighlights() {
    var S = store();
    var term = String((S.state && S.state.hlWord) || "").trim();
    $$(OUTLET + " .verse-text, #drawer .drawer-verse, #prayer-verse blockquote")
      .forEach(function (root) { highlightRoot(root, term); });
  }

  /* ------------------------------------------------------------------ *
   * Settings controls (nav drawer)
   * ------------------------------------------------------------------ */
  function syncThemeUI() {
    var S = store();
    var dark = S.state.theme === "dark";
    $$("[data-theme-set]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.dataset.themeSet === (dark ? "dark" : "light"));
    });
  }

  function syncInlineNotesToggle() {
    var box = document.getElementById("set-inline-notes");
    if (box) box.checked = /[?&]commentary=1(&|$)/.test(location.search);
  }

  function syncSettingsUI() {
    var S = store();
    var s = S.state;
    var size = document.getElementById("set-font-size");
    if (size) {
      size.value = s.fontSize;
      document.getElementById("out-font-size").textContent =
        Math.round((Number(s.fontSize) / 1.1) * 100) + "%";
    }
    var spacing = document.getElementById("set-word-spacing");
    if (spacing) {
      spacing.value = s.wordSpacing;
      document.getElementById("out-word-spacing").textContent =
        Number(s.wordSpacing).toFixed(2) + "em";
    }
    var family = document.getElementById("set-font-family");
    if (family) family.value = s.fontFamily;
    var color = document.getElementById("set-verse-color");
    if (color && s.verseColor) color.value = s.verseColor;
    var hlWord = document.getElementById("set-hl-word");
    if (hlWord) hlWord.value = s.hlWord;
    var hlColor = document.getElementById("set-hl-color");
    if (hlColor) hlColor.value = s.hlColor;
    var daily = document.getElementById("set-daily");
    if (daily) daily.checked = !!s.dailyReminder;
    syncThemeUI();
    syncInlineNotesToggle();
  }

  function setInlineNotes(on) {
    var cur = currentChapter();
    var box = document.getElementById("set-inline-notes");
    if (!cur) { if (box) box.checked = false; return; }
    var url =
      "/read/" + encodeURIComponent(cur.book) + "/" + encodeURIComponent(cur.chapter) +
      (on ? "?commentary=1" : "");
    if (typeof htmx !== "undefined") {
      htmx.ajax("GET", url, { target: "#chapter-outlet", swap: "innerHTML" });
      try { history.pushState(null, "", url); } catch (e) { /* noop */ }
      window.setTimeout(function () { closeNav(); }, 300);
    } else {
      location.href = url;
    }
  }

  function wireSettings() {
    var size = document.getElementById("set-font-size");
    if (size) {
      size.addEventListener("input", function () {
        store().save({ fontSize: Number(size.value) });
        document.getElementById("out-font-size").textContent =
          Math.round((Number(size.value) / 1.1) * 100) + "%";
      });
    }
    var spacing = document.getElementById("set-word-spacing");
    if (spacing) {
      spacing.addEventListener("input", function () {
        store().save({ wordSpacing: Number(spacing.value) });
        document.getElementById("out-word-spacing").textContent =
          Number(spacing.value).toFixed(2) + "em";
      });
    }
    var family = document.getElementById("set-font-family");
    if (family) {
      family.addEventListener("change", function () {
        store().save({ fontFamily: family.value });
      });
    }
    var color = document.getElementById("set-verse-color");
    if (color) {
      color.addEventListener("input", function () {
        store().save({ verseColor: color.value });
      });
    }
    var hlWord = document.getElementById("set-hl-word");
    if (hlWord) {
      hlWord.addEventListener("input", function () {
        store().save({ hlWord: hlWord.value });
        applyHighlights();
      });
    }
    var hlColor = document.getElementById("set-hl-color");
    if (hlColor) {
      hlColor.addEventListener("input", function () {
        store().save({ hlColor: hlColor.value });
      });
    }
    var daily = document.getElementById("set-daily");
    if (daily) {
      daily.addEventListener("change", function () {
        store().save({ dailyReminder: daily.checked });
        if (daily.checked && typeof Notification !== "undefined" && Notification.requestPermission) {
          try {
            var req = Notification.requestPermission();
            if (req && req.catch) req.catch(function () { /* noop */ });
          } catch (e) { /* noop */ }
        }
      });
    }
    var inline = document.getElementById("set-inline-notes");
    if (inline) {
      inline.addEventListener("change", function () { setInlineNotes(inline.checked); });
    }
  }

  /* ------------------------------------------------------------------ *
   * Reminders (Prayer & reminder tool)
   * ------------------------------------------------------------------ */
  function renderReminders() {
    var list = document.getElementById("reminder-list");
    if (!list) return;
    var items = (store().state && store().state.reminders) || [];
    list.textContent = "";
    items.forEach(function (item, index) {
      var li = document.createElement("li");
      li.className = "reminder-item";
      var cat = document.createElement("span");
      cat.className = "cat";
      cat.textContent = item.cat || "Prayer";
      var txt = document.createElement("span");
      txt.className = "txt";
      txt.textContent = item.text || "";
      var del = document.createElement("button");
      del.type = "button";
      del.className = "del";
      del.setAttribute("data-del-reminder", String(index));
      del.setAttribute("aria-label", "Delete reminder");
      del.textContent = "✕";
      li.appendChild(cat);
      li.appendChild(txt);
      li.appendChild(del);
      list.appendChild(li);
    });
  }

  function addReminder(text, cat) {
    var S = store();
    var items = (S.state.reminders || []).slice();
    items.push({ text: text, cat: cat, at: Date.now() });
    S.save({ reminders: items });
    renderReminders();
  }

  function removeReminder(index) {
    var S = store();
    var items = (S.state.reminders || []).slice();
    if (index < 0 || index >= items.length) return;
    items.splice(index, 1);
    S.save({ reminders: items });
    renderReminders();
  }

  function wireReminders() {
    var form = document.getElementById("reminder-form");
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var input = document.getElementById("reminder-text");
      var text = input ? input.value.trim() : "";
      if (!text) return;
      var checked = form.querySelector('input[name="reminder-cat"]:checked');
      addReminder(text, checked ? checked.value : "Prayer");
      if (input) input.value = "";
    });
  }

  /* ------------------------------------------------------------------ *
   * Search results
   * ------------------------------------------------------------------ */
  function closeSearchResults() {
    var box = document.getElementById("search-results");
    if (box) box.innerHTML = "";
  }

  /* ------------------------------------------------------------------ *
   * Clipboard
   * ------------------------------------------------------------------ */
  function copyText(btn) {
    var text = btn.dataset.copy || "";
    var original = btn.textContent;
    function done() {
      btn.textContent = "Copied ✓";
      window.setTimeout(function () { btn.textContent = original; }, 1400);
    }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      btn.textContent = ok ? "Copied ✓" : "Copy failed";
      if (ok) window.setTimeout(function () { btn.textContent = original; }, 1400);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
  }

  /* ------------------------------------------------------------------ *
   * Delegated clicks
   * ------------------------------------------------------------------ */
  document.addEventListener("click", function (event) {
    var t = event.target;
    if (!t || !t.closest) return;

    // panel toggle buttons
    var toggle = t.closest("[data-toggle-panel]");
    if (toggle) {
      openPanel(toggle.dataset.togglePanel);
      return;
    }

    // nav / settings drawer
    if (t.closest("[data-open-nav]")) {
      if (document.body.classList.contains("nav-open")) closeNav();
      else openNav();
      return;
    }
    if (t.closest("[data-close-nav]")) {
      closeNav();
      return;
    }

    // theme buttons inside the settings drawer
    var themeBtn = t.closest("[data-theme-set]");
    if (themeBtn) {
      store().save({ theme: themeBtn.dataset.themeSet === "dark" ? "dark" : "light" });
      syncThemeUI();
      return;
    }

    // translation option buttons — the chapter <article> also carries a
    // data-translation attribute, so scope this to the buttons themselves
    var option = t.closest(".translation-option[data-translation]");
    if (option) {
      selectTranslation(option.dataset.translation);
      return;
    }

    // verse drawer tabs
    var tab = t.closest("[data-drawer-tab]");
    if (tab) {
      switchDrawerTab(tab.dataset.drawerTab);
      return;
    }

    // reminder delete
    var del = t.closest("[data-del-reminder]");
    if (del) {
      removeReminder(parseInt(del.dataset.delReminder, 10));
      return;
    }

    // drawer close button / backdrop
    if (t.closest("[data-close-drawer]")) {
      closeDrawer();
      return;
    }

    // copy-verse pills
    var copyBtn = t.closest("[data-copy]");
    if (copyBtn) {
      copyText(copyBtn);
      return;
    }

    // inline study-note toggles (content lazy-loads via hx-trigger="click once")
    var noteBtn = t.closest(".note-toggle");
    if (noteBtn) {
      var box = document.getElementById(noteBtn.dataset.noteTarget);
      if (box) {
        var willOpen = box.hasAttribute("hidden");
        if (willOpen) box.removeAttribute("hidden");
        else box.setAttribute("hidden", "");
        noteBtn.setAttribute("aria-expanded", willOpen ? "true" : "false");
      }
      return;
    }

    // close popovers unless the click landed inside them
    if (t.closest(".panel a")) closePanels();
    else if (!t.closest(".panel-wrap")) closePanels();

    if (t.closest("#search-results a")) closeSearchResults();
    else if (!t.closest("#search-wrap")) closeSearchResults();

    // clicking a verse row (not a button/link) opens the drawer,
    // unless the user is selecting text
    var verse = t.closest(".verse");
    if (!verse || !verse.dataset.verseId) return;
    if (t.closest("button, a, .inline-note")) return;
    var selection = window.getSelection ? String(window.getSelection()) : "";
    if (selection) return;
    openVerse(verse.dataset.verseId);
  });

  /* ------------------------------------------------------------------ *
   * Forms that are wired by hand (no HTMX endpoint)
   * ------------------------------------------------------------------ */
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || !form.id) return;
    if (form.id === "nav-lexicon-form") {
      event.preventDefault();
      runLexicon($("#nav-lexicon-input") && $("#nav-lexicon-input").value, $("#nav-lexicon-out"));
    } else if (form.id === "drawer-lexicon-form") {
      event.preventDefault();
      runLexicon($("#drawer-lexicon-input") && $("#drawer-lexicon-input").value, $("#drawer-lexicon-out"));
    }
  });

  /* ------------------------------------------------------------------ *
   * Keyboard: Escape closes drawers / results / panels
   * ------------------------------------------------------------------ */
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    if (document.body.classList.contains("nav-open")) {
      closeNav();
      return;
    }
    if (document.body.classList.contains("drawer-open")) {
      closeDrawer();
      return;
    }
    var results = document.getElementById("search-results");
    if (results && results.innerHTML.trim()) {
      closeSearchResults();
      var input = document.getElementById("search-input");
      if (input) input.blur();
      return;
    }
    closePanels();
  });

  /* ------------------------------------------------------------------ *
   * HTMX lifecycle
   * ------------------------------------------------------------------ */
  // NOTE: htmx temporarily copies the old element's attributes (class included)
  // onto id-matched nodes during a swap and restores the new ones during the
  // *settle* phase — which runs after htmx:afterSwap. Hooking afterSettle
  // guarantees .verse-focus and friends are back before we look for them.
  document.addEventListener("htmx:afterSettle", function (event) {
    var target = event.detail.target;
    if (!target || !target.id) return;
    if (target.id === "chapter-outlet") onChapterSwap(target);
    else if (target.id === "drawer") openDrawer();
  });

  // Fresh content (chapter, drawer, prayer verse, notes manager) needs the
  // translation label and the custom word highlighter re-applied.
  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (!target || !target.id) return;
    if (
      target.id === "chapter-outlet" ||
      target.id === "drawer" ||
      target.id === "prayer-verse" ||
      target.id === "notes-manage-out"
    ) {
      applyTranslation();
      applyHighlights();
      if (target.id === "chapter-outlet") syncInlineNotesToggle();
    }
  });

  function onChapterSwap(target) {
    var chapter = target.querySelector("[data-title]");
    if (chapter && chapter.dataset.title) document.title = chapter.dataset.title;
    closePanels();
    closeDrawer();

    var focus = target.querySelector(".verse-focus");
    if (focus) {
      focus.scrollIntoView({ behavior: "smooth", block: "center" });
      window.setTimeout(function () {
        focus.classList.remove("verse-focus");
      }, 2600);
    } else if (window.scrollY > 0) {
      window.scrollTo({ top: 0, behavior: window.scrollY > 700 ? "auto" : "smooth" });
    }
  }

  // Note form: clear the textarea only after a successful save.
  document.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail.elt;
    if (!elt || !elt.matches || !elt.matches("form[data-notes-form]")) return;
    var xhr = event.detail.xhr;
    if (xhr && xhr.status >= 200 && xhr.status < 300) {
      elt.reset();
      var empty = document.getElementById("notes-empty");
      if (empty) empty.remove();
    }
  });

  /* ------------------------------------------------------------------ *
   * Progress bar while requests are in flight
   * ------------------------------------------------------------------ */
  var pending = 0;
  document.addEventListener("htmx:beforeRequest", function () {
    pending += 1;
    document.body.classList.add("htmx-busy");
  });
  document.addEventListener("htmx:afterRequest", function () {
    pending = Math.max(0, pending - 1);
    if (pending === 0) document.body.classList.remove("htmx-busy");
  });

  /* ------------------------------------------------------------------ *
   * Initial page load: honour ?focus= (server renders .verse-focus),
   * restore persisted settings into the controls, apply highlighting
   * ------------------------------------------------------------------ */
  document.addEventListener("DOMContentLoaded", function () {
    var focus = document.querySelector("#chapter-outlet .verse-focus");
    if (focus) {
      focus.scrollIntoView({ block: "center" });
      window.setTimeout(function () {
        focus.classList.remove("verse-focus");
      }, 2600);
    }

    syncSettingsUI();
    wireSettings();
    wireReminders();
    applyTranslation();
    renderReminders();
    applyHighlights();

    // The page was rendered from the cookie; if the stored choice disagrees
    // (cookie cleared, localStorage restored elsewhere), refetch the chapter.
    var cur = currentChapter();
    var want = (store().state && store().state.translation) || "kjv";
    if (cur && cur.translation && cur.translation !== want) reloadChapter();
  });
})();
