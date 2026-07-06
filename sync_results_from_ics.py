#!/usr/bin/env python3
"""
Sync match results from the kubeia ICS calendar into _data/results.json.

Usage:
    python3 sync_results_from_ics.py
    python3 sync_results_from_ics.py --generate
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from generate_bracket import nteam

ICS_URL = "https://calendar.kubeia.io/world-cup-with-alarm-with-score-tv-united-states-of-america-the.ics"
FIXTURES_PATH = Path("_data/raw/openfootball/worldcup-2026.json")
RESULTS_PATH = Path("_data/results.json")
ICS_OUT = Path("_data/raw/betexplorer/world-cup-calendar.ics")

SCORE_RE = re.compile(r"^(.+?) (\d+) - (\d+) (.+?) \(")
MATCH_NUM_RE = re.compile(r"\((\d+)\)\)?(?:\s*$|\s*\()")


def clean_summary_teams(text):
    text = re.sub(r"[^\x00-\x7F]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def unfold_ics(content):
    return re.sub(r"\r?\n ", "", content)


def load_fixtures():
    fixtures = json.loads(FIXTURES_PATH.read_text())["matches"]
    canon_to_fixture = {}
    for match in fixtures:
        for team in (match["team1"], match["team2"]):
            canon_to_fixture[nteam(team)] = team
    fixture_by_pair = {}
    for match in fixtures:
        if not match.get("group"):
            continue
        pair = tuple(sorted([nteam(match["team1"]), nteam(match["team2"])]))
        fixture_by_pair[pair] = match
    return fixtures, canon_to_fixture, fixture_by_pair


def fixture_name(raw, canon_to_fixture):
    canonical = nteam(clean_summary_teams(raw))
    return canon_to_fixture.get(canonical, canonical)


def parse_match_num(summary):
    nums = [int(n) for n in MATCH_NUM_RE.findall(summary)]
    return nums[-1] if nums else None


def knockout_round_for_match_num(match_num):
    if match_num is None:
        return None
    if 73 <= match_num <= 88:
        return "round_of_32"
    if 89 <= match_num <= 96:
        return "round_of_16"
    if 97 <= match_num <= 100:
        return "quarter_finals"
    if 101 <= match_num <= 102:
        return "semi_finals"
    if match_num == 104:
        return "final"
    return None


def extract_penalty_winner(event_text, canon_to_fixture):
    desc = event_text.replace("\\n", "\n").replace("\\r", "")
    pens = re.findall(r"Penalty scored - [^(]+\(([^)]+)\)", desc)
    if not pens:
        return None
    final = pens[-1].strip()
    pm = re.match(r"(.+?) (\d+) - (\d+) (.+)", final)
    if not pm:
        return None
    fs1, fs2 = int(pm.group(2)), int(pm.group(3))
    wt1 = fixture_name(pm.group(1), canon_to_fixture)
    wt2 = fixture_name(pm.group(4), canon_to_fixture)
    if fs1 > fs2:
        return wt1
    if fs2 > fs1:
        return wt2
    return None


def sync_results(ics_url=ICS_URL, results_path=RESULTS_PATH, ics_out=ICS_OUT):
    with urllib.request.urlopen(ics_url, timeout=60) as resp:
        ics = unfold_ics(resp.read().decode("utf-8"))
    ics_out.parent.mkdir(parents=True, exist_ok=True)
    ics_out.write_text(ics)

    _, canon_to_fixture, fixture_by_pair = load_fixtures()
    matches = {}
    knockout = {}
    skipped = []

    for event in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics, re.DOTALL):
        summary_match = re.search(r"SUMMARY:(.*?)\n", event)
        if not summary_match:
            continue
        summary = summary_match.group(1).strip().replace("\r", "")
        score_match = SCORE_RE.match(summary)
        if not score_match:
            continue

        raw_t1, s1, s2, raw_t2 = (
            score_match.group(1),
            int(score_match.group(2)),
            int(score_match.group(3)),
            score_match.group(4),
        )
        t1 = fixture_name(raw_t1, canon_to_fixture)
        t2 = fixture_name(raw_t2, canon_to_fixture)
        pair = tuple(sorted([nteam(t1), nteam(t2)]))
        match_num = parse_match_num(summary)
        ko_round = knockout_round_for_match_num(match_num)

        if s1 > s2:
            winner = t1
        elif s2 > s1:
            winner = t2
        else:
            winner = "draw"
            if ko_round:
                pen_winner = extract_penalty_winner(event, canon_to_fixture)
                if pen_winner:
                    winner = pen_winner

        entry = {
            "team1": t1,
            "team2": t2,
            "score1": s1,
            "score2": s2,
            "winner": winner,
            "played": True,
        }

        if pair in fixture_by_pair:
            fixture_match = fixture_by_pair[pair]
            key = (
                fixture_match["team1"].replace(" ", "_")
                + "_vs_"
                + fixture_match["team2"].replace(" ", "_")
            )
            entry["team1"] = fixture_match["team1"]
            entry["team2"] = fixture_match["team2"]
            entry["group"] = fixture_match["group"].replace("Group ", "")
            matches[key] = entry
        elif ko_round:
            if winner != "draw":
                entry["penalties"] = s1 == s2
            entry["match_num"] = match_num
            entry["round"] = ko_round
            key = entry["team1"].replace(" ", "_") + "_vs_" + entry["team2"].replace(" ", "_")
            knockout[key] = entry
        else:
            skipped.append(summary[:100])

    results = {
        "matches": matches,
        "knockout_matches": knockout,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "kubeia ICS calendar",
    }
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    return {
        "group_matches": len(matches),
        "knockout_matches": len(knockout),
        "skipped": len(skipped),
        "results_path": str(results_path),
        "ics_path": str(ics_out),
    }


def main():
    parser = argparse.ArgumentParser(description="Sync results.json from kubeia ICS calendar")
    parser.add_argument("--results", default=str(RESULTS_PATH))
    parser.add_argument("--ics-out", default=str(ICS_OUT))
    parser.add_argument("--generate", action="store_true", help="Run generate_results.py after sync")
    args = parser.parse_args()

    stats = sync_results(results_path=Path(args.results), ics_out=Path(args.ics_out))
    print(
        f"Synced {stats['group_matches']} group matches, "
        f"{stats['knockout_matches']} knockout matches "
        f"-> {stats['results_path']}"
    )
    if stats["skipped"]:
        print(f"Skipped {stats['skipped']} unmatched summaries")

    if args.generate:
        subprocess.run([sys.executable, "generate_results.py"], check=True)


if __name__ == "__main__":
    main()
