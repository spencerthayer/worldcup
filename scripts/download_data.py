#!/usr/bin/env python3
"""
Download raw World Cup 2026 odds data from all sources listed in README.md.

Usage:
    python3 download_data.py

Output:
    _data/raw/<source>/  — one subdirectory per source, raw files preserved
"""

import json
import csv
import io
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

RAW = Path("_data/raw")
RAW.mkdir(parents=True, exist_ok=True)

# Track download manifest
manifest = []


def fetch(url, headers=None, retries=2, delay=1):
    """HTTP GET with retry. Returns (status_code, body_bytes)."""
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "worldcup-data/1.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                return getattr(e, "code", 0), str(e).encode()


def save_raw(subdir, filename, data_bytes, meta=None):
    """Save raw bytes to _data/raw/<subdir>/<filename> and log to manifest."""
    d = RAW / subdir
    d.mkdir(parents=True, exist_ok=True)
    path = d / filename
    path.write_bytes(data_bytes)
    size = len(data_bytes)
    manifest.append({
        "source": subdir,
        "file": str(path),
        "size_bytes": size,
        "status": meta.get("status", "?") if meta else "?",
        "timestamp": datetime.utcnow().isoformat(),
    })
    print(f"  [OK] {path} ({size:,} bytes)")
    return path


def save_text(subdir, filename, text, meta=None):
    return save_raw(subdir, filename, text.encode("utf-8"), meta)


# ---------------------------------------------------------------------------
# 1. BetExplorer (via kubeia.io ICS — the existing source)
# ---------------------------------------------------------------------------
def download_betexplorer():
    print("\n=== BetExplorer (ICS calendar) ===")
    url = "https://calendar.kubeia.io/world-cup-with-alarm-with-score-tv-united-states-of-america-the.ics"
    status, data = fetch(url)
    if status == 200:
        save_raw("betexplorer", "world-cup-calendar.ics", data, {"status": status})
    else:
        print(f"  [FAIL] HTTP {status}: {data[:200]}")
        # Fall back to local copy if it exists
        local = Path("world-cup-calendar.ics")
        if local.exists():
            save_raw("betexplorer", "world-cup-calendar.ics", local.read_bytes(), {"status": "local-fallback"})
            print(f"  [FALLBACK] Using local copy")


# ---------------------------------------------------------------------------
# 2. BALLDONTLIE FIFA API
# ---------------------------------------------------------------------------
def download_balldontlie():
    print("\n=== BALLDONTLIE FIFA API ===")
    base = "https://api.balldontlie.io/v1/fifa"
    headers = {
        "User-Agent": "worldcup-data/1.0",
        # No API key needed for basic access; add "?api_key=..." if you have one
    }

    # Fetch matches with odds
    for endpoint in ["matches", "teams", "players"]:
        url = f"{base}/{endpoint}?per_page=100"
        status, data = fetch(url, headers=headers)
        if status == 200:
            save_raw("balldontlie", f"{endpoint}.json", data, {"status": status})
        else:
            print(f"  [FAIL] {endpoint}: HTTP {status}")
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# 3. Polymarket Gamma API
# ---------------------------------------------------------------------------
def download_polymarket():
    print("\n=== Polymarket Gamma API ===")
    # Search for World Cup 2026 events
    base = "https://gamma-api.polymarket.com"
    endpoints = [
        ("events?active=true&closed=false&limit=100&order=volume24hr&ascending=false", "events_worldcup.json"),
        ("markets?active=true&closed=false&limit=100&order=volume24hr&ascending=false", "markets_worldcup.json"),
    ]
    for ep, fname in endpoints:
        url = f"{base}/{ep}"
        status, data = fetch(url)
        if status == 200:
            save_raw("polymarket", fname, data, {"status": status})
        else:
            print(f"  [FAIL] {fname}: HTTP {status}")
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# 4. openfootball / worldcup.json
# ---------------------------------------------------------------------------
def download_openfootball():
    print("\n=== openfootball/worldcup.json ===")
    urls = [
        ("https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json", "worldcup-2026.json"),
        ("https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.csv", "worldcup-2026.csv"),
    ]
    for url, fname in urls:
        status, data = fetch(url)
        if status == 200:
            save_raw("openfootball", fname, data, {"status": status})
        else:
            print(f"  [FAIL] {fname}: HTTP {status}")


# ---------------------------------------------------------------------------
# 5. FiveThirtyEight world-cup-predictions
# ---------------------------------------------------------------------------
def download_fivethirtyeight():
    print("\n=== FiveThirtyEight World Cup Predictions ===")
    # The repo has historical data; check for 2026 if available
    urls = [
        ("https://raw.githubusercontent.com/fivethirtyeight/data/master/world-cup-predictions/wc-2018-predictions.csv", "wc-2018-predictions.csv"),
        ("https://raw.githubusercontent.com/fivethirtyeight/data/master/world-cup-predictions/wc-2022-predictions.csv", "wc-2022-predictions.csv"),
        ("https://raw.githubusercontent.com/fivethirtyeight/data/master/world-cup-predictions/README.md", "README.md"),
    ]
    for url, fname in urls:
        status, data = fetch(url)
        if status == 200:
            save_raw("fivethirtyeight", fname, data, {"status": status})
        else:
            print(f"  [FAIL] {fname}: HTTP {status}")

    # Also try the SPI ratings
    spi_url = "https://raw.githubusercontent.com/fivethirtyeight/data/master/fifa/international-matches/international-matches.csv"
    status, data = fetch(spi_url)
    if status == 200:
        save_raw("fivethirtyeight", "international-matches.csv", data, {"status": status})
    else:
        print(f"  [FAIL] international-matches.csv: HTTP {status}")


# ---------------------------------------------------------------------------
# 6. Nate Silver PELE model
# ---------------------------------------------------------------------------
def download_natesilver():
    print("\n=== Nate Silver PELE model ===")
    # The PELE predictions page — we'll save the HTML for parsing
    url = "https://www.natesilver.net/p/world-cup-2026-odds-predictions"
    status, data = fetch(url, headers={"User-Agent": "worldcup-data/1.0 (educational)"})
    if status == 200:
        save_raw("natesilver", "world-cup-2026-predictions.html", data, {"status": status})
    else:
        print(f"  [FAIL] HTTP {status}")


# ---------------------------------------------------------------------------
# 7. Covers Sports odds
# ---------------------------------------------------------------------------
def download_covers():
    print("\n=== Covers Sports odds ===")
    urls = [
        ("https://www.covers.com/world-cup/odds", "odds.html"),
        ("https://www.covers.com/world-cup/futures", "futures.html"),
    ]
    for url, fname in urls:
        status, data = fetch(url, headers={"User-Agent": "worldcup-data/1.0 (educational)"})
        if status == 200:
            save_raw("covers", fname, data, {"status": status})
        else:
            print(f"  [FAIL] {fname}: HTTP {status}")
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# 8. OddsPortal (World Cup 2026 page)
# ---------------------------------------------------------------------------
def download_oddsportal():
    print("\n=== OddsPortal World Cup 2026 ===")
    url = "https://www.oddsportal.com/football/world/world-championship-2026/"
    status, data = fetch(url, headers={"User-Agent": "worldcup-data/1.0 (educational)"})
    if status == 200:
        save_raw("oddsportal", "world-championship-2026.html", data, {"status": status})
    else:
        print(f"  [FAIL] HTTP {status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("World Cup 2026 — Raw Data Downloader")
    print("=" * 60)

    download_betexplorer()
    download_balldontlie()
    download_polymarket()
    download_openfootball()
    download_fivethirtyeight()
    download_natesilver()
    download_covers()
    download_oddsportal()

    # Write manifest
    manifest_path = RAW / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written to {manifest_path}")
    print(f"Total files: {len(manifest)}")
    total = sum(m["size_bytes"] for m in manifest)
    print(f"Total size: {total:,} bytes ({total / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
