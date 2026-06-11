#!/usr/bin/env python3
"""Download remaining data from GitHub repos."""
import urllib.request, json, time
from pathlib import Path

RAW = Path("_data/raw")

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "worldcup-data/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except Exception as e:
        return 0, str(e).encode()

def save(subdir, fname, data):
    p = RAW / subdir / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    print(f"  [OK] {p} ({len(data):,} bytes)")
    return p

# 1. uanalyse
print("=== uanalyse ===")
for subdir in ["latest", "history"]:
    url = f"https://api.github.com/repos/uanalyse/world-cup-2026-predictions/contents/data/{subdir}"
    status, data = fetch(url)
    if status == 200:
        files = json.loads(data)
        for f in files:
            if f["type"] == "file":
                s2, d2 = fetch(f["download_url"])
                if s2 == 200:
                    save("uanalyse", f"{subdir}/{f['name']}", d2)
                else:
                    print(f"  [FAIL] {f['name']}: {s2}")
                time.sleep(0.3)

# 2. worldcup-predictor
print("\n=== worldcup-predictor ===")
for fname in ["outputs/wc2026_predictions.csv", "PREDICTIONS.md"]:
    url = f"https://raw.githubusercontent.com/hjjbh1314/worldcup-predictor/master/{fname}"
    status, data = fetch(url)
    if status == 200:
        save("worldcup-predictor", Path(fname).name, data)
    else:
        print(f"  [FAIL] {fname}: {status}")
    time.sleep(0.3)

# 3. Hicruben
print("\n=== Hicruben ===")
for fname in ["data/results.json", "data/elo-calibrated.json", "data/model-backtest.json"]:
    url = f"https://raw.githubusercontent.com/Hicruben/world-cup-2026-prediction-model/main/{fname}"
    status, data = fetch(url)
    if status == 200:
        save("hicruben", Path(fname).name, data)
    else:
        print(f"  [FAIL] {fname}: {status}")
    time.sleep(0.3)

# 4. FiveThirtyEight final snapshot
print("\n=== FiveThirtyEight ===")
url = "https://raw.githubusercontent.com/fivethirtyeight/data/master/world-cup-predictions/wc-20140713-113900.csv"
status, data = fetch(url)
if status == 200:
    save("fivethirtyeight", "wc-2014-final-predictions.csv", data)
else:
    print(f"  [FAIL] {status}")

print("\nDone.")
