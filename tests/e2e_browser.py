"""End-to-end verification of the Selah app in headless Firefox.

Drives the real UI: HTMX chapter swaps, history, panels, search, drawer,
inline notes, and notes CRUD — 49 checks in total.

Requirements (script exits 0 with a SKIP notice if unmet):
  * the app running, e.g. `python app.py` (override host with SELAH_BASE_URL)
  * firefox + geckodriver (env GECKODRIVER, PATH, or /tmp/geckodriver)
  * `pip install selenium`

Run: python3 tests/e2e_browser.py
"""

import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoAlertPresentException, TimeoutException
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


def accept_alert(driver, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        try:
            driver.switch_to.alert.accept()
            return True
        except NoAlertPresentException:
            time.sleep(0.15)
    return False


def outlet(driver):
    return driver.find_element(By.CSS_SELECTOR, "#chapter-outlet > [data-book]")


def main():
    try:
        urllib.request.urlopen(BASE + "/read/john/1", timeout=3)
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
    wait_ = WebDriverWait(driver, 10)
    js_errors = []

    try:
        # ------------------------------------------------------------------
        print("\n[1] Reader page load + Tailwind applied")
        driver.get(f"{BASE}/read/john/3")
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#chapter-outlet .verse")))
        driver.execute_script(
            "window.__errs=[]; window.addEventListener('error', e => window.__errs.push(String(e.message)));"
        )
        check("title", driver.title == "John 3 · Selah", repr(driver.title))
        check("36 verses", len(driver.find_elements(By.CSS_SELECTOR, "#chapter-outlet .verse")) == 36)
        sticky = driver.execute_script(
            "return getComputedStyle(document.querySelector('.site-header')).position"
        )
        check("tailwind processed (header sticky)", sticky == "sticky", sticky)
        border = driver.execute_script(
            "return getComputedStyle(document.querySelector('#search-input')).borderTopWidth"
        )
        check("tailwind utilities applied (search border)", border == "1px", border)
        serif = driver.execute_script(
            "return getComputedStyle(document.querySelector('.verse-line')).fontFamily"
        )
        check("scripture serif font", "Georgia" in serif, serif)

        # ------------------------------------------------------------------
        print("\n[2] HTMX next-chapter swap + URL push + title update")
        driver.find_element(By.CSS_SELECTOR, 'a.nav-arrow[rel="next"]').click()
        wait_.until(lambda d: outlet(d).get_attribute("data-chapter") == "4")
        check("outlet swapped to John 4", True)
        check("URL pushed", driver.current_url.endswith("/read/john/4"), driver.current_url)
        time.sleep(0.3)
        check("document.title updated", driver.title == "John 4 · Selah", repr(driver.title))

        # ------------------------------------------------------------------
        print("\n[3] Browser back restores chapter")
        driver.back()
        wait_.until(lambda d: outlet(d).get_attribute("data-chapter") == "3")
        check("back → John 3", True)
        check("URL restored", driver.current_url.endswith("/read/john/3"), driver.current_url)

        # ------------------------------------------------------------------
        print("\n[4] Book panel navigation")
        driver.find_element(By.CSS_SELECTOR, '[data-toggle-panel="book-panel"]').click()
        wait_.until(EC.visibility_of_element_located((By.ID, "book-panel")))
        check("book panel visible", True)
        driver.find_element(By.CSS_SELECTOR, "#book-panel a[href='/read/genesis/1']").click()
        wait_.until(lambda d: outlet(d).get_attribute("data-book") == "genesis")
        check("navigated to Genesis", True)
        check("book panel closed", not driver.find_element(By.ID, "book-panel").is_displayed())
        check("URL /read/genesis/1", driver.current_url.endswith("/read/genesis/1"), driver.current_url)

        # ------------------------------------------------------------------
        print("\n[5] Chapter panel: pills + refresh after navigation")
        driver.find_element(By.CSS_SELECTOR, '[data-toggle-panel="chapter-panel"]').click()
        wait_.until(EC.visibility_of_element_located((By.ID, "chapter-panel")))
        pills = driver.find_elements(By.CSS_SELECTOR, "#chapter-panel .grid-chapter")
        check("50 chapter pills for Genesis", len(pills) == 50, str(len(pills)))
        driver.find_element(By.CSS_SELECTOR, "#chapter-panel a[href='/read/genesis/10']").click()
        wait_.until(lambda d: outlet(d).get_attribute("data-chapter") == "10")
        check("navigated to Genesis 10", True)
        driver.find_element(By.CSS_SELECTOR, '[data-toggle-panel="chapter-panel"]').click()
        wait_.until(EC.visibility_of_element_located((By.ID, "chapter-panel")))
        wait_.until(lambda d: d.find_element(By.CSS_SELECTOR, "#chapter-panel .grid-chapter.is-current").text == "10")
        check("chapter panel refreshed (pill 10 highlighted)", True)

        # ------------------------------------------------------------------
        print("\n[6] Instant search + result jump")
        box = driver.find_element(By.ID, "search-input")
        box.click()
        box.send_keys("shepherd")
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#search-results .hit")))
        hits = driver.find_elements(By.CSS_SELECTOR, "#search-results .hit")
        check("search results rendered", len(hits) > 0, str(len(hits)))
        check("matches highlighted", len(driver.find_elements(By.CSS_SELECTOR, "#search-results mark")) > 0)
        hits[0].click()
        wait_.until(lambda d: d.find_element(By.CSS_SELECTOR, "#chapter-outlet > [data-book]").get_attribute("data-book") == "john")
        wait_.until(lambda d: "focus=" in d.current_url)
        time.sleep(1.0)
        check("jumped to first hit", "focus=" in driver.current_url, driver.current_url)
        focus_exists = driver.find_elements(By.CSS_SELECTOR, "#chapter-outlet .verse-focus")
        check("focus flash rendered", len(focus_exists) > 0)
        check("scrolled to verse", driver.execute_script("return window.scrollY") > 0)

        # ------------------------------------------------------------------
        print("\n[7] Reference search → John 3:16")
        box = driver.find_element(By.ID, "search-input")
        box.send_keys(Keys.CONTROL, "a")
        box.send_keys("John 3:16")
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#search-results .search-goto")))
        check("jump-to card shown", True)
        driver.find_element(By.CSS_SELECTOR, "#search-results .search-goto").click()
        wait_.until(lambda d: d.find_element(By.CSS_SELECTOR, "#chapter-outlet > [data-book]").get_attribute("data-chapter") == "3")
        time.sleep(0.8)
        check("arrived at John 3", True)
        check("v16 exists", len(driver.find_elements(By.ID, "v16")) == 1)

        # ------------------------------------------------------------------
        print("\n[8] Verse drawer: open via verse number, commentary shown")
        driver.find_element(By.CSS_SELECTOR, "#v16 .verse-num").click()
        wait_.until(lambda d: "drawer-open" in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#drawer .drawer-verse")))
        check("drawer opened", True)
        check(
            "commentary shown",
            "God so loved the world" in driver.find_element(By.ID, "drawer").text,
        )
        overflow = driver.execute_script("return getComputedStyle(document.body).overflow")
        check("background scroll locked", overflow == "hidden", overflow)

        # note CRUD inside the drawer
        area = wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#drawer .note-form textarea")))
        area.send_keys("End-to-end browser note")
        driver.find_element(By.CSS_SELECTOR, "#drawer .note-form button[type=submit]").click()
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#notes-list .note-item")))
        check("note saved via HTMX", "End-to-end browser note" in driver.find_element(By.ID, "notes-list").text)
        check("placeholder removed", len(driver.find_elements(By.ID, "notes-empty")) == 0)
        driver.find_element(By.CSS_SELECTOR, "#notes-list .link-btn").click()
        check("confirm dialog accepted", accept_alert(driver))
        wait_.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#notes-list .note-item")) == 0)
        check("note deleted via HTMX", True)

        print("\n[9] Drawer closes via Escape (repeatable)")
        # step 8 left the drawer open — close it first, then redo the open/close cycle
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        wait_.until(lambda d: "drawer-open" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        check("escape closed drawer", True)
        driver.find_element(By.CSS_SELECTOR, "#v16 .verse-num").click()
        wait_.until(lambda d: "drawer-open" in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        wait_.until(lambda d: "drawer-open" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        check("drawer reopens and closes", True)
        check("aria-hidden reset", driver.find_element(By.ID, "drawer").get_attribute("aria-hidden") == "true")

        # ------------------------------------------------------------------
        print("\n[10] Whole-verse click opens drawer (mouse convenience)")
        driver.get(f"{BASE}/read/psalms/23")
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#v1 .verse-text")))
        driver.find_element(By.CSS_SELECTOR, "#v1 .verse-text").click()
        wait_.until(lambda d: "drawer-open" in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#drawer .drawer-verse")))
        check("drawer opened from verse text", True)
        # NOTE: geckodriver's getElementText occasionally returns partial rendered
        # text for freshly swapped nodes — the DOM itself is complete (verified by
        # sampling innerText/computed styles), so assert via JS innerText.
        commentary_ok = wait_.until(
            lambda d: "The Lord is my shepherd"
            in d.execute_script("return document.getElementById('drawer').innerText"))
        check("psalm 23:1 commentary", commentary_ok)
        driver.find_element(By.ID, "drawer-backdrop").click()
        wait_.until(lambda d: "drawer-open" not in d.find_element(By.TAG_NAME, "body").get_attribute("class"))
        check("backdrop click closed drawer", True)

        # ------------------------------------------------------------------
        print("\n[11] Inline commentary toggle (toolbar Notes flag)")
        driver.find_element(By.CSS_SELECTOR, 'a[title="Toggle inline study notes"]').click()
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#chapter-outlet .note-toggle")))
        check("commentary flag in URL", "commentary=1" in driver.current_url, driver.current_url)
        toggle = driver.find_element(By.CSS_SELECTOR, "#chapter-outlet .note-toggle")
        toggle.click()
        wait_.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".inline-note:not([hidden])")))
        note_box = driver.find_element(By.CSS_SELECTOR, ".inline-note:not([hidden])")
        check("inline note expanded", note_box.is_displayed())
        check(
            "inline note content",
            "The Lord is my shepherd" in note_box.text,
            note_box.text[:60],
        )
        toggle.click()  # collapse again (content stays loaded, hidden)
        time.sleep(0.3)
        check(
            "inline note collapsed",
            driver.find_element(By.CSS_SELECTOR, "#chapter-outlet .inline-note").get_attribute("hidden") is not None,
        )

        # ------------------------------------------------------------------
        print("\n[12] Mobile layout: real viewport checks, bottom sheet")
        driver.set_window_size(375, 740)
        time.sleep(0.6)
        vw, vh = driver.execute_script("return [window.innerWidth, window.innerHeight];")
        print(f"    actual viewport: {vw}x{vh} (Firefox headless may clamp window size)")
        mobile = driver.execute_script("return !window.matchMedia('(min-width: 768px)').matches")
        check("mobile media query active", mobile, f"vw={vw}")
        sw = driver.execute_script("return document.documentElement.scrollWidth")
        check("no horizontal overflow", sw <= vw + 1, f"scrollWidth={sw} vw={vw}")
        driver.find_element(By.CSS_SELECTOR, "#v1 .verse-num").click()
        wait_.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#drawer .drawer-verse")))
        time.sleep(0.6)
        rect = driver.execute_script(
            "var r = document.getElementById('drawer').getBoundingClientRect();"
            "return {x: r.x, y: r.y, w: r.width, h: r.height};"
        )
        check("bottom sheet spans width", rect["w"] >= vw - 2, str(rect))
        # sheet may grow to 86vh (max-height) — docked means flush with the
        # viewport bottom and not full-screen
        check("bottom sheet docked to bottom",
              rect["y"] + rect["h"] >= vh - 2 and 0 < rect["h"] < vh, str(rect))
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        check("escape closed mobile sheet",
              "drawer-open" not in driver.find_element(By.TAG_NAME, "body").get_attribute("class"))

        # tablet sanity
        driver.set_window_size(820, 1000)
        time.sleep(0.5)
        vw2 = driver.execute_script("return window.innerWidth")
        sw = driver.execute_script("return document.documentElement.scrollWidth")
        check("no horizontal overflow at tablet width", sw <= vw2 + 1, f"scrollWidth={sw} vw={vw2}")

        # ------------------------------------------------------------------
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
