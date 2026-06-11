#!/usr/bin/env python3
"""
Scrape World Cup 2026 odds data from multiple sources using existing scrapers
and custom Playwright scripts.

Uses:
  - OddsHarvester (pip install oddsharvester) for OddsPortal scraping
  - Custom Playwright for Polymarket, Covers, Nate Silver, BetExplorer
  - Direct HTTP for openfootball, GitHub repos

Output: _data/raw/<source>/
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

RAW = Path("_data/raw")
RAW.mkdir(parents=True, exist_ok=True)
MANIFEST = []


def log(msg):
    print(f"  {msg}")


def save_raw(subdir, filename, data_bytes, meta=None):
    d = RAW / subdir
    d.mkdir(parents=True, exist_ok=True)
    path = d / filename
    path.write_bytes(data_bytes)
    entry = {
        "source": subdir,
        "file": str(path),
        "size_bytes": len(data_bytes),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if meta:
        entry.update(meta)
    MANIFEST.append(entry)
    log(f"[OK] {path} ({len(data_bytes):,} bytes)")
    return path


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "worldcup-data/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except Exception as e:
        return 0, str(e).encode()


# ===================================================================
# 1. OddsHarvester — scrape OddsPortal for World Cup 2026
# ===================================================================
def run_oddsharvester():
    print("\n=== OddsHarvester — OddsPortal World Cup 2026 ===")
    out_dir = RAW / "oddsharvester"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Scrape upcoming World Cup 2026 matches (1X2 market)
    # OddsHarvester uses league slugs; world-championship-2026 is the slug
    cmd = [
        sys.executable, "-m", "oddsharvester", "upcoming",
        "-s", "football",
        "-l", "world-championship-2026",
        "-m", "1x2",
        "--headless",
        "-f", "json",
        "-o", str(out_dir / "worldcup-2026-odds"),
        "--no-append",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            log(f"OddsHarvester completed successfully")
            if result.stdout:
                log(result.stdout[:500])
        else:
            log(f"[WARN] OddsHarvester exit code {result.returncode}")
            if result.stderr:
                log(f"stderr: {result.stderr[:500]}")
            if result.stdout:
                log(f"stdout: {result.stdout[:500]}")
    except subprocess.TimeoutExpired:
        log("[FAIL] OddsHarvester timed out after 300s")
    except Exception as e:
        log(f"[FAIL] OddsHarvester error: {e}")


# ===================================================================
# 2. Playwright — scrape Polymarket, Covers, Nate Silver, BetExplorer
# ===================================================================
def run_playwright_scraper():
    print("\n=== Playwright — Polymarket / Covers / Nate Silver / BetExplorer ===")

    script = r'''
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
'''
    script_path = Path("_data/_playwright_scraper.py")
    script_path.write_text(script)

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=600
        )
        print(result.stdout)
        if result.returncode != 0:
            log(f"[WARN] Playwright scraper exit code {result.returncode}")
            if result.stderr:
                log(f"stderr: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        log("[FAIL] Playwright scraper timed out")
    except Exception as e:
        log(f"[FAIL] Playwright scraper error: {e}")


# ===================================================================
# 3. Direct HTTP — openfootball, GitHub repos, Polymarket API
# ===================================================================
def run_direct_downloads():
    print("\n=== Direct HTTP downloads ===")

    # openfootball/worldcup.json
    print("  Downloading openfootball/worldcup.json...")
    url = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
    status, data = fetch(url)
    if status == 200:
        save_raw("openfootball", "worldcup-2026.json", data, {"status": status})
    else:
        log(f"[FAIL] openfootball: HTTP {status}")

    # Polymarket Gamma API — World Cup events
    print("  Downloading Polymarket Gamma API...")
    pm_url = "https://gamma-api.polymarket.com/events?active=true&closed=false&limit=200&order=volume24hr&ascending=false"
    status, data = fetch(pm_url)
    if status == 200:
        save_raw("polymarket", "gamma-events.json", data, {"status": status})
    else:
        log(f"[FAIL] Polymarket API: HTTP {status}")

    # uanalyse predictions
    print("  Downloading uanalyse predictions...")
    for subdir, fname in [("latest", "match_predictions.csv"), ("latest", "tournament_probabilities.csv")]:
        url = f"https://raw.githubusercontent.com/uanalyse/world-cup-2026-predictions/main/data/{subdir}/{fname}"
        status, data = fetch(url)
        if status == 200:
            save_raw("uanalyse", f"{subdir}/{fname}", data, {"status": status})
        else:
            log(f"[FAIL] uanalyse {fname}: HTTP {status}")

    # worldcup-predictor
    print("  Downloading worldcup-predictor...")
    url = "https://raw.githubusercontent.com/hjjbh1314/worldcup-predictor/master/outputs/wc2026_predictions.csv"
    status, data = fetch(url)
    if status == 200:
        save_raw("worldcup-predictor", "wc2026_predictions.csv", data, {"status": status})
    else:
        log(f"[FAIL] worldcup-predictor: HTTP {status}")

    # Hicruben model
    print("  Downloading Hicruben model data...")
    for fname in ["results.json", "elo-calibrated.json", "model-backtest.json"]:
        url = f"https://raw.githubusercontent.com/Hicruben/world-cup-2026-prediction-model/main/data/{fname}"
        status, data = fetch(url)
        if status == 200:
            save_raw("hicruben", fname, data, {"status": status})
        else:
            log(f"[FAIL] Hicruben {fname}: HTTP {status}")

    # FiveThirtyEight 2014 final snapshot (methodology reference)
    print("  Downloading FiveThirtyEight 2014 snapshot...")
    url = "https://raw.githubusercontent.com/fivethirtyeight/data/master/world-cup-predictions/wc-20140713-113900.csv"
    status, data = fetch(url)
    if status == 200:
        save_raw("fivethirtyeight", "wc-2014-final-predictions.csv", data, {"status": status})
    else:
        log(f"[FAIL] FiveThirtyEight: HTTP {status}")


# ===================================================================
# Main
# ===================================================================
def main():
    print("=" * 60)
    print("World Cup 2026 — Multi-Source Data Scraper")
    print("=" * 60)

    run_direct_downloads()
    run_oddsharvester()
    run_playwright_scraper()

    # Write manifest
    manifest_path = RAW / "_manifest.json"
    manifest_path.write_text(json.dumps(MANIFEST, indent=2))
    print(f"\nManifest: {manifest_path}")
    print(f"Total files: {len(MANIFEST)}")
    total = sum(m.get("size_bytes", m.get("size", 0)) for m in MANIFEST)
    print(f"Total size: {total:,} bytes ({total / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
