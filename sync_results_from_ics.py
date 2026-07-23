#!/usr/bin/env python3
"""
Sync match results into _data/results.json.

Primary source: FIFA's official API (api.fifa.com) — authoritative final
scores with correct extra-time and penalty outcomes. The kubeia ICS
calendar is kept as a fallback only: it records 90-minute scorelines for
matches decided in extra time (e.g. it had the 2026 final as 0-0 when
Spain actually won 1-0 AET), so never trust it when FIFA is reachable.

Usage:
    python3 sync_results_from_ics.py
    python3 sync_results_from_ics.py --generate
    python3 sync_results_from_ics.py --source ics   # force a source
"""

import argparse
import json
import re
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from generate_bracket import nteam

ICS_URL = "https://calendar.kubeia.io/world-cup-with-alarm-with-score-tv-united-states-of-america-the.ics"
FIFA_API_URL = (
    "https://api.fifa.com/api/v3/calendar/matches"
    "?idCompetition=17&idSeason=285023&count=200&language=en"
)
FIXTURES_PATH = Path("_data/raw/openfootball/worldcup-2026.json")
RESULTS_PATH = Path("_data/results.json")
ICS_OUT = Path("_data/raw/betexplorer/world-cup-calendar.ics")
FIFA_OUT = Path("_data/raw/fifa/matches.json")

# FIFA ResultType values: 1 = regulation, 2 = decided on penalties,
# 3 = decided in extra time (score already includes ET goals).
FIFA_RT_PENALTIES = 2
FIFA_RT_EXTRA_TIME = 3

# FIFA display names that nteam() cannot canonicalize on its own.
FIFA_NAME_OVERRIDES = {"IR Iran": "Iran"}

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


def fetch_fifa_matches(fifa_url=FIFA_API_URL, fifa_out=FIFA_OUT):
    req = urllib.request.Request(fifa_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    fifa_out.parent.mkdir(parents=True, exist_ok=True)
    fifa_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload.get("Results", [])


def fifa_team_name(raw, canon_to_fixture):
    raw = FIFA_NAME_OVERRIDES.get(raw, raw)
    ascii_name = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    canonical = nteam(re.sub(r"\s+", " ", ascii_name).strip())
    return canon_to_fixture.get(canonical, canonical)


def results_from_fifa(fifa_matches, canon_to_fixture, fixture_by_pair):
    """Build (group, knockout) result dicts from FIFA API match objects."""
    matches = {}
    knockout = {}
    for fm in fifa_matches:
        if fm.get("MatchStatus") != 0:  # 0 = played/official
            continue
        s1, s2 = fm.get("HomeTeamScore"), fm.get("AwayTeamScore")
        if s1 is None or s2 is None:
            continue
        t1 = fifa_team_name(fm.get("Home", {}).get("ShortClubName", ""), canon_to_fixture)
        t2 = fifa_team_name(fm.get("Away", {}).get("ShortClubName", ""), canon_to_fixture)

        winner_id = str(fm.get("Winner") or "")
        if winner_id and winner_id == str(fm.get("Home", {}).get("IdTeam")):
            winner = t1
        elif winner_id and winner_id == str(fm.get("Away", {}).get("IdTeam")):
            winner = t2
        elif s1 > s2:
            winner = t1
        elif s2 > s1:
            winner = t2
        else:
            winner = "draw"

        entry = {
            "team1": t1,
            "team2": t2,
            "score1": s1,
            "score2": s2,
            "winner": winner,
            "played": True,
        }

        match_num = fm.get("MatchNumber")
        ko_round = knockout_round_for_match_num(match_num)
        pair = tuple(sorted([nteam(t1), nteam(t2)]))
        if ko_round:
            if fm.get("ResultType") in (FIFA_RT_EXTRA_TIME, FIFA_RT_PENALTIES):
                entry["extra_time"] = True
            if fm.get("ResultType") == FIFA_RT_PENALTIES:
                entry["penalties"] = True
            entry["match_num"] = match_num
            entry["round"] = ko_round
            key = t1.replace(" ", "_") + "_vs_" + t2.replace(" ", "_")
            knockout[key] = entry
        elif match_num is not None and match_num >= 73:
            continue  # third-place playoff (103) — not tracked in this bracket
        elif pair in fixture_by_pair:
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
    return matches, knockout


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


def extract_penalty_winner_from_description(event_text, canon_to_fixture):
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


def resolve_knockout_winner(summary, t1, t2, s1, s2, event_text, canon_to_fixture):
    """
    Resolve knockout winner from regulation score, then ET, then penalties.

    ICS summaries encode extras as:
      (ET 1 - 0)                    — extra-time goals for team1 / team2
      (ET 0 - 0, Penalties 4 - 3)  — pens for team1 / team2
    """
    if s1 > s2:
        return t1, False, False
    if s2 > s1:
        return t2, False, False

    # Normalize escaped commas from ICS unfolding
    summary_norm = summary.replace("\\,", ",")

    et = re.search(r"\(ET\s+(\d+)\s*-\s*(\d+)", summary_norm)
    if et:
        et1, et2 = int(et.group(1)), int(et.group(2))
        if et1 > et2:
            return t1, True, False
        if et2 > et1:
            return t2, True, False

    pens = re.search(r"Penalties\s+(\d+)\s*-\s*(\d+)", summary_norm)
    if pens:
        p1, p2 = int(pens.group(1)), int(pens.group(2))
        if p1 > p2:
            return t1, True, True
        if p2 > p1:
            return t2, True, True

    pen_winner = extract_penalty_winner_from_description(event_text, canon_to_fixture)
    if pen_winner:
        return pen_winner, True, True

    return "draw", False, False


def parse_ics_results(ics_url, ics_out, canon_to_fixture, fixture_by_pair):
    """Legacy fallback: parse results from the kubeia ICS calendar.

    WARNING: this feed stores 90-minute scorelines for matches decided in
    extra time, so AET scorelines synced this way are wrong (winners and
    penalty outcomes are still resolved correctly).
    """
    with urllib.request.urlopen(ics_url, timeout=60) as resp:
        ics = unfold_ics(resp.read().decode("utf-8"))
    ics_out.parent.mkdir(parents=True, exist_ok=True)
    ics_out.write_text(ics)

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

        went_et = False
        went_pens = False
        if ko_round:
            winner, went_et, went_pens = resolve_knockout_winner(
                summary, t1, t2, s1, s2, event, canon_to_fixture,
            )
        elif s1 > s2:
            winner = t1
        elif s2 > s1:
            winner = t2
        else:
            winner = "draw"

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
            if went_et or went_pens or (s1 == s2 and winner != "draw"):
                entry["extra_time"] = True
            if went_pens or (winner != "draw" and "Penalties" in summary.replace("\\,", ",")):
                entry["penalties"] = True
            entry["match_num"] = match_num
            entry["round"] = ko_round
            key = entry["team1"].replace(" ", "_") + "_vs_" + entry["team2"].replace(" ", "_")
            knockout[key] = entry
        else:
            skipped.append(summary[:100])

    return matches, knockout, skipped


def sync_results(
    results_path=RESULTS_PATH,
    ics_url=ICS_URL,
    ics_out=ICS_OUT,
    fifa_url=FIFA_API_URL,
    fifa_out=FIFA_OUT,
    source="auto",
):
    _, canon_to_fixture, fixture_by_pair = load_fixtures()

    matches = knockout = None
    skipped = []
    if source in ("auto", "fifa"):
        try:
            fifa_matches = fetch_fifa_matches(fifa_url, fifa_out)
            matches, knockout = results_from_fifa(
                fifa_matches, canon_to_fixture, fixture_by_pair
            )
            if not matches and not knockout:
                raise ValueError("FIFA API returned no played matches")
            used_source = "FIFA API (api.fifa.com)"
        except Exception as exc:
            if source == "fifa":
                raise
            print(
                f"WARNING: FIFA API sync failed ({exc}); "
                "falling back to kubeia ICS calendar",
                file=sys.stderr,
            )
            matches = knockout = None
    if matches is None:
        matches, knockout, skipped = parse_ics_results(
            ics_url, ics_out, canon_to_fixture, fixture_by_pair
        )
        used_source = "kubeia ICS calendar (fallback; AET scorelines unreliable)"

    results = {
        "matches": matches,
        "knockout_matches": knockout,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": used_source,
    }
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    return {
        "group_matches": len(matches),
        "knockout_matches": len(knockout),
        "skipped": len(skipped),
        "results_path": str(results_path),
        "source": used_source,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sync results.json from the FIFA API (kubeia ICS calendar as fallback)"
    )
    parser.add_argument("--results", default=str(RESULTS_PATH))
    parser.add_argument("--ics-out", default=str(ICS_OUT))
    parser.add_argument("--fifa-out", default=str(FIFA_OUT))
    parser.add_argument(
        "--source",
        choices=["auto", "fifa", "ics"],
        default="auto",
        help="Data source: 'auto' tries FIFA first and falls back to ICS",
    )
    parser.add_argument("--generate", action="store_true", help="Run generate_results.py after sync")
    args = parser.parse_args()

    stats = sync_results(
        results_path=Path(args.results),
        ics_out=Path(args.ics_out),
        fifa_out=Path(args.fifa_out),
        source=args.source,
    )
    print(
        f"Synced {stats['group_matches']} group matches, "
        f"{stats['knockout_matches']} knockout matches "
        f"-> {stats['results_path']} [{stats['source']}]"
    )
    if stats["skipped"]:
        print(f"Skipped {stats['skipped']} unmatched summaries")

    if args.generate:
        subprocess.run([sys.executable, "generate_results.py"], check=True)


if __name__ == "__main__":
    main()
