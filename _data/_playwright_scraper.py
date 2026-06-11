
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

RAW = Path("_data/raw")
MANIFEST = []

def save(subdir, fname, text):
    p = RAW / subdir / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    MANIFEST.append({"source": subdir, "file": str(p), "size": len(text)})
    print(f"  [OK] {p} ({len(text):,} chars)")

def scrape_page(page, url, wait_selector=None, wait_ms=5000):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=wait_ms)
        except:
            pass
    time.sleep(2)  # extra render time
    return page.content()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )

    # --- Polymarket World Cup ---
    print("  Scraping Polymarket World Cup...")
    try:
        page = context.new_page()
        html = scrape_page(page, "https://polymarket.com/sports/world-cup/props", wait_ms=8000)
        save("polymarket", "world-cup-props.html", html)
        browser.close()
    except Exception as e:
        print(f"  [FAIL] Polymarket: {e}")
        try: browser.close()
        except: pass

    # --- Covers World Cup Odds ---
    print("  Scraping Covers World Cup odds...")
    try:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        html = scrape_page(page, "https://www.covers.com/world-cup/odds", wait_ms=8000)
        save("covers", "odds-live.html", html)
        browser.close()
    except Exception as e:
        print(f"  [FAIL] Covers: {e}")
        try: browser.close()
        except: pass

    # --- Nate Silver PELE ---
    print("  Scraping Nate Silver PELE predictions...")
    try:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        html = scrape_page(page, "https://www.natesilver.net/p/world-cup-2026-odds-predictions", wait_ms=10000)
        save("natesilver", "pele-predictions-live.html", html)
        browser.close()
    except Exception as e:
        print(f"  [FAIL] Nate Silver: {e}")
        try: browser.close()
        except: pass

    # --- BetExplorer World Cup 2026 ---
    print("  Scraping BetExplorer World Cup 2026...")
    try:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        html = scrape_page(page, "https://www.betexplorer.com/football/world/world-cup-2026/", wait_ms=8000)
        save("betexplorer", "world-cup-2026.html", html)
        browser.close()
    except Exception as e:
        print(f"  [FAIL] BetExplorer: {e}")
        try: browser.close()
        except: pass

    # --- OddsPortal World Cup 2026 (full page) ---
    print("  Scraping OddsPortal World Cup 2026...")
    try:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        html = scrape_page(page, "https://www.oddsportal.com/football/world/world-championship-2026/", wait_ms=8000)
        save("oddsportal", "world-championship-2026-live.html", html)
        browser.close()
    except Exception as e:
        print(f"  [FAIL] OddsPortal: {e}")
        try: browser.close()
        except: pass

print("  Playwright scraping complete.")
