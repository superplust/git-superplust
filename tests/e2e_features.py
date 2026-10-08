"""End-to-end verification of the new Selah features in headless Firefox.

Covers: the translation selector, the Selah logo nav/settings drawer
(typography, appearance + dark mode, highlights, notes management, Wikipedia
lexicon, prayer/reminder tool) and the verse drawer's Notes/Lexicon tabs.

Requirements (script exits 0 with a SKIP notice if unmet):
  * the app running, e.g. `python app.py` (override host with SELAH_BASE_URL)
  * firefox + geckodriver (env GECKODRIVER, PATH, or /tmp/geckodriver)
  * `pip install selenium`

Run: python3 tests/e2e_features.py
"""

import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:  # pragma: no cover - environment dependent
    print("SKIP: selenium is not installed (pip install selenium)")
    sys.exit(0)

BASE = os.environ.get("SELAH_BASE_URL", "http://127.0.0.1:5000")


def find_geckodriver():
    env = os.environ.get("GECKODRIVER")
    if env and Path(env).exists():
        return env
    found = shutil.which("geckodriver")
    if found:
        return found
    if Path("/tmp/geckodriver").exists():
        return "/tmp/geckodriver"
    return None


PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(f"{name} {detail}")
        print(f"  FAIL  {name}  {detail}")


def wait(driver, cond, timeout=10):
    return WebDriverWait(driver, timeout).until(cond)


def settings(driver):
    return json.loads(driver.execute_script(
        "return localStorage.getItem('selah.settings') || '{}'"))


def main():
    try:
        urllib.request.urlopen(BASE + "/read/john/3", timeout=3)
    except Exception:
        print(f"SKIP: server not reachable at {BASE} — start it with `python app.py`")
        return 0

    opts = Options()
    opts.add_argument("-headless")
    driver_path = find_geckodriver()
    service = Service(executable_path=driver_path) if driver_path else Service()
    driver = webdriver.Firefox(options=opts, service=service)
    driver.set_window_size(1280, 900)
    driver.set_page_load_timeout(30)
    wait_ = WebDriverWait(driver, 15)

    try:
        # ------------------------------------------------------------------
        print("\n[1] Translation selector opens with both options")
        driver.get(f"{BASE}/read/john/3")
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#chapter-outlet .verse")))
        driver.execute_script(
            "localStorage.clear();"
            "document.cookie='selah_translation=; path=/; max-age=0';"
        )
        driver.refresh()
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#chapter-outlet .verse")))
        driver.execute_script(
            "window.__errs=[]; window.addEventListener('error', e => window.__errs.push(String(e.message)));"
        )

        check("toolbar label shows KJV",
              "King James Version" in driver.find_element(By.CSS_SELECTOR,
                                                          '[data-translation-label]').text)
        driver.find_element(By.CSS_SELECTOR, ".translation-eyebrow").click()
        wait_.until(EC.visibility_of_element_located((By.ID, "translation-panel")))
        options = driver.find_elements(By.CSS_SELECTOR, "#translation-panel .translation-option")
        check("dropdown panel visible", True)
        check("two options offered", len(options) == 2, str(len(options)))
        check("KJV option listed", "King James Version (KJV)" in options[0].text, options[0].text)
        check("Jesuit option listed", "Jesuit" in options[1].text, options[1].text)

        # ------------------------------------------------------------------
        print("\n[2] Selecting a translation updates the UI state")
        options[1].click()
        wait_.until(lambda d: "hidden" in d.find_element(By.ID, "translation-panel")
                    .get_attribute("class"))
        check("panel closes after selection", True)
        labels = [el.text for el in driver.find_elements(By.CSS_SELECTOR, "[data-translation-label]")]
        check("labels switched to Arabic name",
              all("الترجمة" in t for t in labels) and len(labels) >= 2, str(labels))
        check("stored in localStorage",
              settings(driver).get("translation") == "jesuit",
              str(settings(driver).get("translation")))

        # the chapter is refetched over HTMX with the Arabic text
        wait_.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#chapter-outlet .verses[dir='rtl']")))
        verses = driver.find_elements(By.CSS_SELECTOR, "#chapter-outlet .verse-text")
        sample = verses[0].text if verses else ""
        check("chapter swapped to Arabic text",
              any("؀" <= ch <= "ۿ" for ch in sample), sample[:40])
        check("verse block reads right-to-left",
              driver.find_element(By.CSS_SELECTOR, "#chapter-outlet .verses")
                    .get_attribute("dir") == "rtl")
        line_font = driver.find_element(By.CSS_SELECTOR, "#chapter-outlet .verse-line") \
            .value_of_css_property("font-family")
        check("Arabic font stack applied", "Amiri" in line_font, line_font)
        check("toolbar stays left-to-right",
              driver.find_element(By.CSS_SELECTOR, ".reading-toolbar").get_attribute("dir") is None)

        driver.refresh()
        wait_.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[data-translation-label]")))
        check("selection survives reload",
              "الترجمة" in driver.find_element(By.CSS_SELECTOR, "[data-translation-label]").text)
        wait_.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#chapter-outlet .verses[dir='rtl']")))
        check("reloaded chapter is still Arabic",
              any("؀" <= ch <= "ۿ" for ch in
                  driver.find_element(By.CSS_SELECTOR, "#chapter-outlet .verse-text").text))

        # back to KJV for the checks below
        driver.find_element(By.CSS_SELECTOR, ".translation-eyebrow").click()
        wait_.until(EC.visibility_of_element_located((By.ID, "translation-panel")))
        driver.find_element(By.CSS_SELECTOR, '#translation-panel [data-translation="kjv"]').click()
        wait_.until(lambda d: d.find_element(By.CSS_SELECTOR, "#chapter-outlet .verses")
                    .get_attribute("dir") is None)
        check("switching back restores English text",
              "For God so loved" in
              driver.find_element(By.CSS_SELECTOR, "#chapter-outlet .verse-text").text)

        # ------------------------------------------------------------------
        print("\n[3] Selah logo opens the navigation / settings drawer")
        driver.find_element(By.ID, "selah-logo").click()
        wait_.until(lambda d: "nav-open" in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        wait_.until(EC.visibility_of_element_located((By.ID, "nav-drawer")))
        check("nav drawer opened", True)
        check("aria-hidden reset", driver.find_element(By.ID, "nav-drawer").get_attribute("aria-hidden") == "false")
        for sel, name in [
            ("#set-font-size", "font size slider"),
            ("#set-word-spacing", "word spacing slider"),
            ("#set-font-family", "font family select"),
            ("[data-theme-set='dark']", "dark mode button"),
            ("[data-theme-set='light']", "light mode button"),
            ("#set-verse-color", "font colour picker"),
            ("#set-hl-word", "highlight word input"),
            ("#set-hl-color", "highlight colour picker"),
            ("#set-daily", "daily reminder toggle"),
            ("#set-inline-notes", "inline notes toggle"),
            ("#nav-lexicon-form input", "lexicon search input"),
            ("#prayer-verse blockquote", "random verse card"),
            ("#reminder-form input[type=text]", "reminder input"),
            ("#reminder-form input[value='Prayer']", "Prayer category"),
            ("#reminder-form input[value='Church Meeting']", "Church Meeting category"),
            ("#reminder-form input[value='rose']", "rose category"),
        ]:
            check(f"settings: {name}", len(driver.find_elements(By.CSS_SELECTOR, sel)) > 0, sel)

        # ------------------------------------------------------------------
        print("\n[4] Dark mode applies and persists")
        before = driver.execute_script("return getComputedStyle(document.body).backgroundColor")
        driver.find_element(By.CSS_SELECTOR, "[data-theme-set='dark']").click()
        wait_.until(lambda d: d.find_element(By.TAG_NAME, "html").get_attribute("data-theme") == "dark")
        after = driver.execute_script("return getComputedStyle(document.body).backgroundColor")
        check("data-theme=dark set", True)
        check("background darkened", before != after and after == "rgb(26, 24, 21)",
              f"{before} → {after}")
        check("theme stored", settings(driver).get("theme") == "dark")
        driver.refresh()
        wait_.until(lambda d: d.find_element(By.TAG_NAME, "html").get_attribute("data-theme") == "dark")
        check("dark mode survives reload",
              driver.execute_script("return getComputedStyle(document.body).backgroundColor")
              == "rgb(26, 24, 21)")
        driver.find_element(By.ID, "selah-logo").click()
        wait_.until(EC.visibility_of_element_located((By.ID, "nav-drawer")))

        # ------------------------------------------------------------------
        print("\n[5] Typography controls change the reading text")
        base_size = driver.execute_script(
            "return getComputedStyle(document.querySelector('.verse-line')).fontSize")
        driver.execute_script(
            "var s=document.getElementById('set-font-size'); s.value=1.5;"
            "s.dispatchEvent(new Event('input',{bubbles:true}));")
        new_size = driver.execute_script(
            "return getComputedStyle(document.querySelector('.verse-line')).fontSize")
        check("font size slider applied", base_size != new_size, f"{base_size} → {new_size}")

        driver.execute_script(
            "var s=document.getElementById('set-word-spacing'); s.value=0.3;"
            "s.dispatchEvent(new Event('input',{bubbles:true}));")
        spacing = driver.execute_script(
            "return getComputedStyle(document.querySelector('.verse-line')).wordSpacing")
        check("word spacing applied", spacing not in ("normal", "0px"), spacing)

        driver.execute_script(
            "var f=document.getElementById('set-font-family'); f.value='mono';"
            "f.dispatchEvent(new Event('change',{bubbles:true}));")
        time.sleep(0.3)
        font = driver.execute_script(
            "return getComputedStyle(document.querySelector('.verse-line')).fontFamily")
        check("font family applied", "mono" in font.lower(), font)

        driver.execute_script(
            "var s=document.getElementById('set-font-size'); s.value=1.1;"
            "s.dispatchEvent(new Event('input',{bubbles:true}));"
            "var w=document.getElementById('set-word-spacing'); w.value=0;"
            "w.dispatchEvent(new Event('input',{bubbles:true}));"
            "var f=document.getElementById('set-font-family'); f.value='serif';"
            "f.dispatchEvent(new Event('change',{bubbles:true}));")

        # ------------------------------------------------------------------
        print("\n[6] Custom word highlighting")
        highlight_count = len(driver.find_elements(By.CSS_SELECTOR, "#chapter-outlet .word-hl"))
        check("default word 'God' highlighted", highlight_count > 0, str(highlight_count))
        check("highlight colour stored",
              settings(driver).get("hlWord") == "God", str(settings(driver).get("hlWord")))
        driver.execute_script(
            "var i=document.getElementById('set-hl-word'); i.value='world';"
            "i.dispatchEvent(new Event('input',{bubbles:true}));")
        time.sleep(0.3)
        # geckodriver's .text is unreliable for fresh inline spans — read the DOM
        words = driver.execute_script(
            "return Array.from(document.querySelectorAll('#chapter-outlet .word-hl'))"
            ".map(e => e.textContent);")
        check("re-highlighted with new word", words and all(w == "world" for w in words),
              str(words[:5]))
        driver.execute_script(
            "var i=document.getElementById('set-hl-word'); i.value='God';"
            "i.dispatchEvent(new Event('input',{bubbles:true}));")
        time.sleep(0.3)

        # ------------------------------------------------------------------
        print("\n[7] Wikipedia lexicon inside the nav drawer")
        box = driver.find_element(By.ID, "nav-lexicon-input")
        box.send_keys("Gospel of John")
        driver.find_element(By.CSS_SELECTOR, "#nav-lexicon-form button[type=submit]").click()
        try:
            wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#nav-lexicon-out .lexicon-card")))
            card = driver.find_element(By.CSS_SELECTOR, "#nav-lexicon-out .lexicon-card")
            check("definition card rendered", True)
            check("summary present", len(card.find_element(By.CLASS_NAME, "snippet").text) > 10)
            check("more-on-wikipedia link",
                  "wikipedia.org" in card.find_element(By.CSS_SELECTOR, "a.more").get_attribute("href"))
        except TimeoutException:
            status = driver.find_element(By.ID, "nav-lexicon-out").text
            check("definition card rendered", False, status[:80])

        # ------------------------------------------------------------------
        print("\n[8] Prayer verse + reminder tool")
        prayer = driver.find_element(By.ID, "prayer-verse")
        trigger = prayer.get_attribute("hx-trigger") or ""
        check("minute refresh wired", "every 60s" in trigger, trigger)
        check("random verse rendered server-side",
              len(prayer.find_elements(By.CSS_SELECTOR, ".verse-card blockquote")) == 1)
        driver.execute_script(
            "var el=document.getElementById('prayer-verse');"
            "htmx.ajax('GET', el.getAttribute('hx-get'), {target: el, swap: 'innerHTML'});")
        wait_.until(lambda d: len(d.find_elements(
            By.CSS_SELECTOR, "#prayer-verse .verse-card blockquote")) == 1)
        check("HTMX refresh swaps a fresh verse", True)

        driver.execute_script(
            "var i=document.getElementById('reminder-text'); i.value='Read Psalm 23 tonight';"
            "document.querySelector('#reminder-form input[value=\"rose\"]').checked=true;")
        driver.find_element(By.CSS_SELECTOR, "#reminder-form button[type=submit]").click()
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#reminder-list .reminder-item")))
        item = driver.find_element(By.CSS_SELECTOR, "#reminder-list .reminder-item")
        check("reminder added", "Read Psalm 23 tonight" in item.text, item.text)
        check("category kept", "rose" in item.text.lower(), item.text)
        stored = settings(driver).get("reminders") or []
        check("reminder persisted", any(r.get("cat") == "rose" for r in stored), str(stored))

        # ------------------------------------------------------------------
        print("\n[9] Nav drawer: notes manager + close behaviour")
        driver.find_element(By.CSS_SELECTOR, "a.nav-sub-link").click()
        wait_.until(EC.presence_of_element_located((By.ID, "notes-manage-out")))
        time.sleep(0.5)
        manage = driver.find_element(By.ID, "notes-manage-out")
        loaded = ("allnotes-empty" in manage.get_attribute("innerHTML")
                  or len(manage.find_elements(By.CSS_SELECTOR, ".allnotes-item")) > 0)
        check("notes manager loaded", loaded, manage.text[:60])
        driver.find_element(By.CSS_SELECTOR, "#nav-drawer [data-close-nav]").click()
        wait_.until(lambda d: "nav-open" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        check("close button closes drawer", True)

        # ------------------------------------------------------------------
        print("\n[10] Verse drawer tabs: Notes | Lexicon")
        driver.get(f"{BASE}/read/psalms/23")
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#v1 .verse-num")))
        driver.find_element(By.CSS_SELECTOR, "#v1 .verse-num").click()
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#drawer .drawer-verse")))
        tabs = driver.find_elements(By.CSS_SELECTOR, "#drawer .drawer-tab")
        check("two tabs", len(tabs) == 2, str([t.text for t in tabs]))
        check("tab labels", [t.text for t in tabs] == ["Notes", "Lexicon"], str([t.text for t in tabs]))
        check("Notes active by default", tabs[0].get_attribute("aria-selected") == "true")
        check("notes content visible",
              driver.find_element(By.ID, "drawer-panel-notes").is_displayed())

        tabs[1].click()
        wait_.until(lambda d: d.find_element(By.ID, "drawer-panel-lexicon").is_displayed())
        check("Lexicon panel shows", True)
        check("Notes panel hides", not driver.find_element(By.ID, "drawer-panel-notes").is_displayed())
        prefill = driver.find_element(By.ID, "drawer-lexicon-input").get_attribute("value")
        check("verse keyword prefilled", bool(prefill.strip()), repr(prefill))
        try:
            wait_.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#drawer-lexicon-out .lexicon-card")))
            more = driver.find_element(By.CSS_SELECTOR, "#drawer-lexicon-out a.more")
            check("lexicon summary + wikipedia link",
                  "More on Wikipedia" in more.text and "wikipedia.org" in more.get_attribute("href"))
        except TimeoutException:
            status = driver.find_element(By.ID, "drawer-lexicon-out").text
            check("lexicon summary + wikipedia link", False, status[:80])

        driver.find_element(By.CSS_SELECTOR, "#drawer .drawer-tab").click()
        time.sleep(0.3)
        check("switch back to Notes",
              driver.find_element(By.ID, "drawer-panel-notes").is_displayed())

        # close the verse drawer before clicking the logo again
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        wait_.until(lambda d: "drawer-open" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))

        # ------------------------------------------------------------------
        print("\n[11] Light mode restored + no JS errors")
        driver.find_element(By.ID, "selah-logo").click()
        wait_.until(EC.visibility_of_element_located((By.ID, "nav-drawer")))
        driver.find_element(By.CSS_SELECTOR, "[data-theme-set='light']").click()
        time.sleep(0.3)
        check("light mode restored",
              driver.find_element(By.TAG_NAME, "html").get_attribute("data-theme") == "light")
        driver.find_element(By.CSS_SELECTOR, "#nav-drawer [data-close-nav]").click()

        errs = driver.execute_script("return window.__errs || []")
        check("no uncaught JS errors", len(errs) == 0, str(errs))

    finally:
        driver.quit()

    print("\n" + "=" * 60)
    print(f"PASSED: {len(PASS)}   FAILED: {len(FAIL)}")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
