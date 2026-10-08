/* Selah — persisted UI settings.
 *
 * Loaded synchronously from <head> so the stored theme and typography are
 * applied to <html> before the first paint (no flash). Exposes window.Selah,
 * which static/js/app.js uses to wire the controls in the nav drawer. */
(function (w) {
  "use strict";

  var KEY = "selah.settings";
  // Mirrored into a cookie so server-rendered HTMX partials (chapter, search,
  // prayer verse) know which text the reader picked without a query string.
  var COOKIE = "selah_translation";

  var FONTS = {
    serif: 'Georgia, "Iowan Old Style", "Times New Roman", serif',
    times: '"Times New Roman", Times, serif',
    sans: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
  };

  var TRANSLATIONS = {
    kjv: {
      short: "King James Version",
      full: "King James Version (KJV)",
    },
    jesuit: {
      short: "الترجمة اليسوعية الكاثوليكية",
      full: "الترجمة اليسوعية الكاثوليكية (Jesuit)",
    },
  };

  var DEFAULTS = {
    theme: "light",        // "light" | "dark"
    fontSize: 1.1,         // rem, applied to scripture
    wordSpacing: 0,        // em
    fontFamily: "serif",   // key of FONTS
    verseColor: "",        // "" = follow the theme's ink colour
    hlWord: "God",         // custom word highlighter
    hlColor: "#16a34a",
    dailyReminder: false,  // notifications toggle
    translation: "kjv",    // "kjv" | "jesuit" — served from SQLite, mirrored to a cookie
    reminders: [],         // [{ text, cat, at }]
  };

  function readCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function writeCookie(name, value) {
    try {
      document.cookie = name + "=" + encodeURIComponent(value) + "; path=/; max-age=31536000; SameSite=Lax";
    } catch (e) { /* private mode */ }
  }

  function read() {
    var raw = null;
    try { raw = w.localStorage.getItem(KEY); } catch (e) { raw = null; }
    var saved = {};
    if (raw) {
      try { saved = JSON.parse(raw) || {}; } catch (e) { saved = {}; }
    }
    var out = {};
    for (var k in DEFAULTS) {
      out[k] = Object.prototype.hasOwnProperty.call(saved, k) ? saved[k] : DEFAULTS[k];
    }
    if (!Object.prototype.hasOwnProperty.call(saved, "translation")) {
      // No stored choice yet: trust the cookie the server sees.
      var fromCookie = readCookie(COOKIE);
      if (fromCookie === "kjv" || fromCookie === "jesuit") out.translation = fromCookie;
    }
    if (!Array.isArray(out.reminders)) out.reminders = [];
    return out;
  }

  function write(state) {
    try { w.localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode */ }
  }

  function apply(state) {
    var root = document.documentElement;
    var dark = state.theme === "dark";
    root.setAttribute("data-theme", dark ? "dark" : "light");
    root.style.colorScheme = dark ? "dark" : "light";
    root.style.setProperty("--reading-size", state.fontSize + "rem");
    root.style.setProperty("--reading-spacing", state.wordSpacing + "em");
    root.style.setProperty("--reading-font", FONTS[state.fontFamily] || FONTS.serif);
    if (state.verseColor) root.style.setProperty("--verse-color", state.verseColor);
    else root.style.removeProperty("--verse-color");
    root.style.setProperty("--hl-color", state.hlColor || DEFAULTS.hlColor);
    // Keep the server in step with the stored choice before any HTMX request.
    writeCookie(COOKIE, state.translation === "jesuit" ? "jesuit" : "kjv");
  }

  var state = read();
  apply(state);

  w.Selah = {
    DEFAULTS: DEFAULTS,
    FONTS: FONTS,
    TRANSLATIONS: TRANSLATIONS,
    state: state,
    save: function (patch) {
      for (var k in patch) {
        if (Object.prototype.hasOwnProperty.call(patch, k)) state[k] = patch[k];
      }
      write(state);
      apply(state);
      return state;
    },
    apply: apply,
  };
})(window);
