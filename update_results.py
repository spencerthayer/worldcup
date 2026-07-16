#!/usr/bin/env python3
"""
Update match results in _data/results.json.

Usage:
    python3 update_results.py                          # List unscored matches
    python3 update_results.py --group A                # List Group A matches
    python3 update_results.py --match KEY SCORE1 SCORE2  # Update by match key

Match keys are: Team1_vs_Team2 (from fixture data)
Example: Mexico_vs_South_Africa

After updating, run: python3 generate_results.py
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# FIFA 2026 bracket topology: child match_num -> (parent_a, parent_b).
BRACKET_CHILDREN = {
    89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
    93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87),
    97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96),
    101: (97, 98), 102: (99, 100), 104: (101, 102),
}

ROUND_BY_NUM = {}
for mn in range(73, 89):
    ROUND_BY_NUM[mn] = "round_of_32"
for mn in range(89, 97):
    ROUND_BY_NUM[mn] = "round_of_16"
for mn in range(97, 101):
    ROUND_BY_NUM[mn] = "quarter_finals"
for mn in (101, 102):
    ROUND_BY_NUM[mn] = "semi_finals"
ROUND_BY_NUM[104] = "final"


def _nteam(team):
    return team.replace(" ", "_").replace("&", "and")


def resolve_knockout_match_num(ko_matches, team1, team2):
    """Determine the match_num for a knockout match from the bracket topology.

    Walks the bracket tree: R32 matches are keyed by team names already in
    ko_matches.  Higher rounds are resolved by checking which two parent
    matches' winners would face each other.
    """
    t1n = _nteam(team1)
    t2n = _nteam(team2)

    # Build team -> match_num from already-recorded R32 results.
    team_to_r32 = {}
    for key, m in ko_matches.items():
        if m.get("round") == "round_of_32" and m.get("match_num"):
            mn = m["match_num"]
            w = m.get("winner")
            if w:
                team_to_r32[_nteam(w)] = mn

    # For each unmatched bracket child, check if both parent winners are known
    # and match the team pair we're looking for.
    for child_mn, (pa, pb) in BRACKET_CHILDREN.items():
        w_a = None
        w_b = None
        for key, m in ko_matches.items():
            if m.get("match_num") == pa:
                w_a = _nteam(m.get("winner", ""))
            if m.get("match_num") == pb:
                w_b = _nteam(m.get("winner", ""))
        if w_a and w_b:
            if (t1n == w_a and t2n == w_b) or (t1n == w_b and t2n == w_a):
                return child_mn

    return None


def load_results(path):
    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return {"matches": {}, "knockout_matches": {}, "last_updated": None}


def save_results(results, path):
    results["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Updated {path}")


def load_fixtures(path):
    with open(path) as f:
        return json.load(f)["matches"]


def main():
    parser = argparse.ArgumentParser(description="Update match results")
    parser.add_argument("--match", "-m", help="Match key (e.g., Mexico_vs_South_Africa)")
    parser.add_argument("--score", "-s", nargs=2, type=int, metavar=("S1", "S2"), help="Score (e.g., 2 1)")
    parser.add_argument("--group", "-g", help="List matches in a group (A-L)")
    parser.add_argument("--results", default="_data/results.json")
    parser.add_argument("--fixtures", default="_data/raw/openfootball/worldcup-2026.json")
    parser.add_argument("--generate", action="store_true", help="Auto-run generate_results.py after")
    args = parser.parse_args()

    results = load_results(args.results)
    fixtures = load_fixtures(args.fixtures)

    if args.match and args.score:
        s1, s2 = args.score
        if s1 > s2:
            winner = args.match.split("_vs_")[0]
        elif s2 > s1:
            winner = args.match.split("_vs_")[1]
        else:
            winner = "draw"

        # Determine if group or knockout
        is_group = any(
            (m.get("group") and (
                (m["team1"].replace(" ", "_") + "_vs_" + m["team2"].replace(" ", "_") == args.match) or
                (m["team2"].replace(" ", "_") + "_vs_" + m["team1"].replace(" ", "_") == args.match)
            ))
            for m in fixtures
        )

        t1 = args.match.split("_vs_")[0].replace("_", " ")
        t2 = args.match.split("_vs_")[1].replace("_", " ")

        entry = {
            "team1": t1, "team2": t2,
            "score1": s1, "score2": s2,
            "winner": winner, "played": True
        }

        if is_group:
            if "matches" not in results:
                results["matches"] = {}
            results["matches"][args.match] = entry
            print(f"✅ {t1} {s1}-{s2} {t2} → {winner}")
        else:
            if "knockout_matches" not in results:
                results["knockout_matches"] = {}
            match_num = resolve_knockout_match_num(
                results.get("knockout_matches", {}), t1, t2
            )
            if match_num is not None:
                entry["match_num"] = match_num
                entry["round"] = ROUND_BY_NUM.get(match_num, "")
            results["knockout_matches"][args.match] = entry
            if match_num is not None:
                print(f"✅ {t1} {s1}-{s2} {t2} → {winner}  (match #{match_num})")
            else:
                print(f"✅ {t1} {s1}-{s2} {t2} → {winner}")

        save_results(results, args.results)

        if args.generate:
            print("\nRegenerating results.md...")
            import subprocess
            subprocess.run([sys.executable, "generate_results.py"], check=True)
        return

    # List matches
    if args.group:
        g = args.group.upper()
        group_matches = [m for m in fixtures if m.get("group") == f"Group {g}"]
        if not group_matches:
            print(f"No matches found for Group {g}")
            return

        print(f"\n{'='*65}")
        print(f"  Group {g} — {len(group_matches)} matches")
        print(f"{'='*65}\n")

        for m in group_matches:
            key = m["team1"].replace(" ", "_") + "_vs_" + m["team2"].replace(" ", "_")
            r = results.get("matches", {}).get(key)
            if r and r.get("played"):
                w = r.get("winner", "draw")
                icon = "🟰" if w == "draw" else "🏆"
                print(f"  ✅ {m['team1']:20s} {r['score1']}-{r['score2']:2d} {m['team2']:20s}  {icon} {w}")
            else:
                print(f"  ⏳ {m['team1']:20s}  vs  {m['team2']:20s}  [{key}]")
        print()
        return

    # Default: show all unscored
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  🏆 World Cup 2026 — Match Results Updater                 ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║                                                              ║")
    print("║  Usage:                                                      ║")
    print("║    python3 update_results.py --group A                       ║")
    print("║    python3 update_results.py -m Mexico_vs_South_Africa -s 2 1║")
    print("║    python3 update_results.py --group A --generate            ║")
    print("║                                                              ║")
    print("║  Then regenerate:                                            ║")
    print("║    python3 generate_results.py                               ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    played = {k for k, v in results.get("matches", {}).items() if v.get("played")}
    ko_played = {k for k, v in results.get("knockout_matches", {}).items() if v.get("played")}

    unscored = []
    for m in fixtures:
        if m.get("group"):
            key = m["team1"].replace(" ", "_") + "_vs_" + m["team2"].replace(" ", "_")
            if key not in played:
                unscored.append((m, key))

    if unscored:
        print(f"⏳ {len(unscored)} matches awaiting results:\n")
        current_group = None
        for m, key in unscored[:24]:
            g = m["group"]
            if g != current_group:
                current_group = g
                print(f"  {g}:")
            print(f"    {m['date']:12s}  {m['team1']:20s}  vs  {m['team2']:20s}")
        if len(unscored) > 24:
            print(f"    ... and {len(unscored) - 24} more")
    else:
        print("✅ All group matches have been scored!")


if __name__ == "__main__":
    main()
