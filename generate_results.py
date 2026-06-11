#!/usr/bin/env python3
"""
Generate a visual results.md from bracket.json, comparing predictions against
actual match results stored in _data/results.json.

Scoring (203 points total):
- Group Stage Placement: +1pt per correct placement (48 picks, 48 max)
  Only scored when ALL 6 matches in a group have been played.
- Advance to Knockout: +1pt per correct team (32 picks, 32 max)
  Only scored when the group is fully determined (all matches played).
- Advance to Round of 16: +2pts per correct team (16 picks, 32 max)
  Only scored when R16 matches have been played.
- Advance to Quarter-Finals: +4pts per correct team (8 picks, 32 max)
- Advance to Semi-Finals: +6pts per correct team (4 picks, 24 max)
- Finalist: +10pts per correct team (2 picks, 20 max)
- Winner: +15pts (1 pick, 15 max)

Usage:
    python3 generate_results.py
    python3 generate_results.py --input _data/bracket.json --output results.md
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Country flag emojis ────────────────────────────────────────────────
FLAGS = {
    "Algeria": "🇩🇿", "Argentina": "🇦🇷", "Australia": "🇦🇺", "Austria": "🇦🇹",
    "Belgium": "🇧🇪", "Bosnia and Herzegovina": "🇧🇦", "Brazil": "🇧🇷",
    "Canada": "🇨🇦", "Cape Verde": "🇨🇻", "Colombia": "🇨🇴", "Croatia": "🇭🇷",
    "Curaçao": "🇨🇼", "Czech Republic": "🇨🇿", "DR Congo": "🇨🇩",
    "Ecuador": "🇪🇨", "Egypt": "🇪🇬", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "France": "🇫🇷",
    "Germany": "🇩🇪", "Ghana": "🇬🇭", "Haiti": "🇭🇹", "Iran": "🇮🇷",
    "Iraq": "🇮🇶", "Ivory Coast": "🇨🇮", "Japan": "🇯🇵", "Jordan": "🇯🇴",
    "Mexico": "🇲🇽", "Morocco": "🇲🇦", "Netherlands": "🇳🇱", "New Zealand": "🇳🇿",
    "Norway": "🇳🇴", "Panama": "🇵🇦", "Paraguay": "🇵🇾", "Portugal": "🇵🇹",
    "Qatar": "🇶🇦", "Saudi Arabia": "🇸🇦", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Senegal": "🇸🇳", "South Africa": "🇿🇦", "South Korea": "🇰🇷", "Spain": "🇪🇸",
    "Sweden": "🇸🇪", "Switzerland": "🇨🇭", "Tunisia": "🇹🇳", "Turkey": "🇹🇷",
    "USA": "🇺🇸", "Uruguay": "🇺🇾", "Uzbekistan": "🇺🇿",
}

STAGE_POINTS = {
    "group_placement": 1, "round_of_32": 1, "round_of_16": 2,
    "quarter_finals": 4, "semi_finals": 6, "finalists": 10, "winner": 15,
}

STAGE_KEY = {
    "round_of_32": "r32", "round_of_16": "r16",
    "quarter_finals": "qf", "semi_finals": "sf",
    "finalists": "final", "winner": "champion",
}

EMOJI_CHECK = "✅"
EMOJI_WRONG = "❌"
EMOJI_TIE = "🟰"
EMOJI_PENDING = "⏳"


def flag(name):
    return FLAGS.get(name, "🏳️")


def pct(p):
    return f"{p * 100:.1f}%"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_results(results_path):
    if Path(results_path).exists():
        return load_json(results_path)
    return {"matches": {}, "knockout_matches": {}, "last_updated": None}


def parse_fixture_results(results):
    matches = results.get("matches", {})
    parsed = {}
    for key, m in matches.items():
        norm_key = key.replace(" ", "_")
        parsed[norm_key] = {
            "team1": m.get("team1", "").replace(" ", "_"),
            "team2": m.get("team2", "").replace(" ", "_"),
            "score1": m.get("score1"), "score2": m.get("score2"),
            "winner": m.get("winner"),
            "played": m.get("winner") is not None,
        }
    return parsed


def compute_group_standings(fixtures, results_parsed, group_letter):
    group_matches = [m for m in fixtures if m.get("group") == group_letter]
    teams = set()
    for m in group_matches:
        teams.add(m["team1"])
        teams.add(m["team2"])
    standings = {t: {"pts": 0, "gf": 0, "ga": 0, "gd": 0} for t in teams}
    for m in group_matches:
        t1n = m["team1"].replace(" ", "_")
        t2n = m["team2"].replace(" ", "_")
        key = f"{t1n}_vs_{t2n}"
        rk = f"{t2n}_vs_{t1n}"
        r = results_parsed.get(key) or results_parsed.get(rk)
        if not r or not r["played"]:
            continue
        t1, t2 = m["team1"], m["team2"]
        s1, s2 = r["score1"], r["score2"]
        standings[t1]["gf"] += s1
        standings[t1]["ga"] += s2
        standings[t2]["gf"] += s2
        standings[t2]["ga"] += s1
        if s1 > s2:
            standings[t1]["pts"] += 3
        elif s2 > s1:
            standings[t2]["pts"] += 3
        else:
            standings[t1]["pts"] += 1
            standings[t2]["pts"] += 1
    for t in standings:
        standings[t]["gd"] = standings[t]["gf"] - standings[t]["ga"]
    ranked = sorted(teams, key=lambda t: (-standings[t]["pts"], -standings[t]["gd"], -standings[t]["gf"]))
    return ranked, standings


def is_group_complete(group_matches, results_parsed):
    """Check if ALL matches in a group have been played."""
    for m in group_matches:
        t1n = m["team1"].replace(" ", "_")
        t2n = m["team2"].replace(" ", "_")
        key = f"{t1n}_vs_{t2n}"
        rk = f"{t2n}_vs_{t1n}"
        r = results_parsed.get(key) or results_parsed.get(rk)
        if not r or not r.get("played"):
            return False
    return True


def compute_scores(bracket, fixtures, results_parsed):
    scores = {
        "group_placement": {"correct": 0, "total": 0, "points": 0, "max": 48},
        "round_of_32": {"correct": 0, "total": 0, "points": 0, "max": 32},
        "round_of_16": {"correct": 0, "total": 0, "points": 0, "max": 32, "pending": 0},
        "quarter_finals": {"correct": 0, "total": 0, "points": 0, "max": 32, "pending": 0},
        "semi_finals": {"correct": 0, "total": 0, "points": 0, "max": 24, "pending": 0},
        "finalists": {"correct": 0, "total": 0, "points": 0, "max": 20, "pending": 0},
        "winner": {"correct": 0, "total": 0, "points": 0, "max": 15, "pending": 0},
    }
    total_played = 0
    total_correct = 0

    # ── Group placements (only when all 6 matches played) ──
    for g in sorted(bracket["group_placements"].keys()):
        predicted = bracket["group_placements"][g]
        fixture_group = f"Group {g}" if not g.startswith("Group ") else g
        group_matches = [m for m in fixtures if m.get("group") == fixture_group]
        if not is_group_complete(group_matches, results_parsed):
            continue
        ranked, standings = compute_group_standings(fixtures, results_parsed, fixture_group)
        for pos in range(4):
            pred_team = predicted[pos] if pos < len(predicted) else None
            actual_team = ranked[pos] if pos < len(ranked) else None
            if pred_team and actual_team:
                is_correct = pred_team == actual_team
                if is_correct:
                    scores["group_placement"]["correct"] += 1
                    scores["group_placement"]["points"] += 1
                    total_correct += 1
                total_played += 1
        scores["group_placement"]["total"] = total_played

    # ── R32 qualifiers (only when all groups are complete) ──
    groups_list = sorted(set(m["group"] for m in fixtures if m.get("group")))
    all_groups_complete = all(
        is_group_complete(
            [m for m in fixtures if m.get("group") == g],
            results_parsed
        )
        for g in groups_list
    )

    if all_groups_complete:
        predicted_r32 = set(bracket.get("round_of_32", []))
        actual_r32 = set()
        all_thirds = []
        for g in groups_list:
            ranked, standings = compute_group_standings(fixtures, results_parsed, g)
            if len(ranked) >= 2:
                actual_r32.add(ranked[0])
                actual_r32.add(ranked[1])
            if len(ranked) >= 3:
                all_thirds.append((ranked[2], standings[ranked[2]]["pts"],
                                  standings[ranked[2]]["gd"], standings[ranked[2]]["gf"]))
        all_thirds.sort(key=lambda x: (-x[1], -x[2], -x[3]))
        for t, _, _, _ in all_thirds[:8]:
            actual_r32.add(t)

        for team in sorted(predicted_r32):
            if team in actual_r32:
                scores["round_of_32"]["correct"] += 1
                scores["round_of_32"]["points"] += 1
                total_correct += 1
            total_played += 1
        for team in sorted(actual_r32):
            if team not in predicted_r32:
                total_played += 1
        scores["round_of_32"]["total"] = max(len(predicted_r32), len(actual_r32))
    else:
        scores["round_of_32"]["pending"] = len(bracket.get("round_of_32", []))

    # ── Knockout stages (require match results) ──
    ko_rounds = [
        ("round_of_16", "round_of_16", "Round of 16"),
        ("quarter_finals", "quarter_finals", "Quarter-final"),
        ("semi_finals", "semi_finals", "Semi-final"),
        ("finalists", "final", "Final"),
        ("winner", "champion", "Winner"),
    ]
    for score_key, _, _ in ko_rounds:
        predicted = bracket.get(score_key, [])
        if not predicted:
            continue
        scores[score_key]["pending"] = len(predicted)

    total_points = sum(s["points"] for s in scores.values())
    return scores, total_points, total_played, total_correct


def compute_expected_score_from_probs(bracket, per_team_probs):
    """Compute expected score by summing probability * points for all picks."""
    score = 0.0
    for g, teams in bracket["group_placements"].items():
        for pos, team in enumerate(teams):
            placement_probs = per_team_probs.get(team, {}).get("placement", {})
            p = placement_probs.get(str(pos + 1), 0)
            score += p * 1
    for stage, key in STAGE_KEY.items():
        if stage == "winner":
            w = bracket.get("winner", "")
            picks = [w] if w else []
        else:
            picks = bracket.get(stage, [])
        points = STAGE_POINTS[stage]
        for t in picks:
            p = per_team_probs.get(t, {}).get(key, 0)
            score += p * points
    return score


def render_scoring_summary(scores, total_points, total_played, total_correct):
    lines = []
    lines.append("## 📈 Scoring Summary\n")
    max_total = 203
    pct_val = (total_points / max_total * 100) if max_total > 0 else 0
    lines.append(f"**Current Score: {total_points:.0f} / {max_total} ({pct_val:.1f}%)**\n")
    if total_played > 0:
        lines.append(f"**Accuracy: {total_correct}/{total_played} correct ({total_correct/total_played*100:.1f}%)**\n")
    else:
        lines.append("**Accuracy: No matches played yet**\n")

    lines.append("| Stage | Correct | Pts/Pick | Max | Pts Earned |")
    lines.append("|:---|:---:|:---:|:---:|:---:|")
    stage_names = {
        "group_placement": "Group Placement",
        "round_of_32": "Advance to Knockout",
        "round_of_16": "Advance to R16",
        "quarter_finals": "Advance to QF",
        "semi_finals": "Advance to SF",
        "finalists": "Finalist",
        "winner": "Winner",
    }
    for key, name in stage_names.items():
        s = scores[key]
        correct = s["correct"]
        total = s["total"]
        pts = s["points"]
        max_pts = s["max"]
        pending = s.get("pending", 0)
        if pending:
            status = f"{correct}/{total} (+{pending} pending)"
        else:
            status = f"{correct}/{total}"
        lines.append(f"| {name} | {status} | {STAGE_POINTS[key]} | {max_pts} | **{pts}** |")
    lines.append(f"| **Total** | | | **{max_total}** | **{total_points:.0f}** |")
    lines.append("")
    return lines


def render_group_placements(bracket, per_team_probs, fixtures, results_parsed):
    lines = []
    lines.append("## 📊 Group Placements\n")
    for g in sorted(bracket["group_placements"].keys()):
        predicted = bracket["group_placements"][g]
        fixture_group = f"Group {g}" if not g.startswith("Group ") else g
        group_matches = [m for m in fixtures if m.get("group") == fixture_group]
        complete = is_group_complete(group_matches, results_parsed)
        ranked, standings = compute_group_standings(fixtures, results_parsed, fixture_group)

        lines.append(f"### Group {g}\n")
        lines.append("| Pos | Predicted | Actual | Pts | GD | Result |")
        lines.append("|:---:|:---|:---|:---:|:---:|:---:|")
        for pos in range(4):
            pred_team = predicted[pos] if pos < len(predicted) else "—"
            if complete and pos < len(ranked):
                actual_team = ranked[pos]
                s = standings.get(actual_team, {})
                pts = s.get("pts", 0)
                gd = s.get("gd", 0)
                gd_str = f"+{gd}" if gd > 0 else str(gd)
            else:
                actual_team = "—"
                pts, gd_str = "—", "—"
            if pred_team != "—" and actual_team != "—":
                if pred_team == actual_team:
                    result = EMOJI_CHECK
                else:
                    result = EMOJI_WRONG
            elif actual_team == "—":
                result = EMOJI_PENDING
            else:
                result = ""
            pred_str = f"{flag(pred_team)} {pred_team}" if pred_team != "—" else "—"
            actual_str = f"{flag(actual_team)} {actual_team}" if actual_team != "—" else "—"
            pos_label = ["1st", "2nd", "3rd", "4th"][pos]
            lines.append(f"| {pos_label} | {pred_str} | {actual_str} | {pts} | {gd_str} | {result} |")
        lines.append("")
    return lines


def render_knockout_bracket(bracket, per_team_probs):
    lines = []
    lines.append("## 🏆 Knockout Bracket\n")
    r32_teams = bracket.get("round_of_32", [])
    r16_set = set(bracket.get("round_of_16", []))
    qf_set = set(bracket.get("quarter_finals", []))
    sf_set = set(bracket.get("semi_finals", []))
    final_set = set(bracket.get("finalists", []))
    winner = bracket.get("winner", "")

    def team_line(team, stage_emoji=""):
        p_r32 = per_team_probs.get(team, {}).get("r32", 0)
        marker = ""
        if team == winner:
            marker = " 👑"
        elif team in final_set:
            marker = " 🌟"
        elif team in sf_set:
            marker = " 🏅"
        elif team in qf_set:
            marker = " 💎"
        elif team in r16_set:
            marker = " 🔥"
        return f"{stage_emoji}{flag(team)} {team} ({pct(p_r32)}){marker}"

    lines.append("### Round of 32\n")
    for team in sorted(r32_teams):
        lines.append(f"- {team_line(team)}")
    lines.append("")

    lines.append("### Round of 16\n")
    for team in sorted(r16_set):
        lines.append(f"- {team_line(team, '🔥 ')}")
    lines.append("")

    lines.append("### Quarter-Finals\n")
    for team in sorted(qf_set):
        lines.append(f"- {team_line(team, '💥 ')}")
    lines.append("")

    lines.append("### Semi-Finals\n")
    for team in sorted(sf_set):
        lines.append(f"- {team_line(team, '🏆 ')}")
    lines.append("")

    lines.append("### Final\n")
    for team in sorted(final_set):
        lines.append(f"- {team_line(team, '🌟 ')}")
    lines.append("")

    if winner:
        lines.append(f"### 👑 Champion: {flag(winner)} {winner}\n")
    return lines


def render_champion_probabilities(per_team_probs, top_n=15):
    lines = []
    lines.append("## 🏅 Champion Probabilities\n")
    lines.append("| Rank | Team | Probability |")
    lines.append("|:---:|:---:|:---:|")
    champs = sorted(per_team_probs.items(), key=lambda x: -x[1].get("champion", 0))
    for i, (team, probs) in enumerate(champs[:top_n], 1):
        p = probs.get("champion", 0)
        if p > 0:
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            lines.append(f"| {medal} | {flag(team)} {team} | {pct(p)} |")
    lines.append("")
    return lines


def render_validation(bracket, config):
    lines = []
    lines.append("## ⚙️ Simulation Config\n")
    lines.append(f"- **Model:** {config['model']}")
    lines.append(f"- **Simulations:** {config['sims']:,}")
    lines.append(f"- **Seed:** {config['seed']}")
    sims = config['sims']
    se = math.sqrt(0.25 / sims)
    lines.append(f"- **Simulation accuracy:** ±{se*100:.2f}% (SE bound at p=0.5)")
    strategy = config.get('strategy', 'ev-bracket')
    probs = config.get('probabilities', 'sim')
    lines.append(f"- **Strategy:** {strategy}")
    lines.append(f"- **Probabilities:** {probs}")
    lines.append(f"- **Generated:** {bracket.get('generated_at', 'N/A')}")
    lines.append("")

    validation = bracket.get("validation", {})
    errors = validation.get("errors", [])
    mad = validation.get("mad_vs_uanalyse", {})
    if errors:
        lines.append("### ❌ Validation Errors\n")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")
    else:
        lines.append("### ✅ All Invariants Passed\n")
    if mad:
        lines.append("### Validation vs UAnalyse Priors (MAD)\n")
        lines.append("| Stage | MAD |")
        lines.append("|:---|:---:|")
        for stage in ["r32", "qf", "sf", "final", "champion"]:
            if stage in mad:
                lines.append(f"| {stage.upper()} | {mad[stage]:.4f} |")
        lines.append("")
    return lines


def render_per_team_table(per_team_probs):
    lines = []
    lines.append("## 📋 Full Team Probabilities\n")
    lines.append("| Team | Flag | R32 | R16 | QF | SF | Final | Champion |")
    lines.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")
    sorted_teams = sorted(per_team_probs.items(), key=lambda x: -x[1].get("champion", 0))
    for team, probs in sorted_teams:
        if probs.get("r32", 0) > 0.001:
            stages = ["r32", "r16", "qf", "sf", "final", "champion"]
            vals = [pct(probs.get(s, 0)) for s in stages]
            lines.append(f"| {team} | {flag(team)} | {' | '.join(vals)} |")
    lines.append("")
    return lines


def generate_results(bracket_path, fixtures_path, results_path, output_path):
    bracket = load_json(bracket_path)
    fixtures = load_json(fixtures_path)["matches"]
    config = bracket["config"]
    per_team_probs = bracket.get("per_team_probs", {})
    actual_results = load_results(results_path)
    results_parsed = parse_fixture_results(actual_results)

    actual_scores, actual_points, total_played, total_correct = compute_scores(bracket, fixtures, results_parsed)
    expected_score = compute_expected_score_from_probs(bracket, per_team_probs)

    L = []
    L.append("# 🏆 2026 World Cup Bracket Results\n")
    L.append(f"**Last updated:** {datetime.now(timezone.utc).isoformat()}\n")

    winner = bracket.get("winner", "TBD")
    finalists = bracket.get("finalists", [])
    L.append("## 🎯 Summary\n")
    L.append(f"- 👑 **Predicted Champion:** {flag(winner)} {winner} ({pct(per_team_probs.get(winner, {}).get('champion', 0))})")
    if len(finalists) == 2:
        f1, f2 = sorted(finalists)
        L.append(f"- 🌟 **Predicted Final:** {flag(f1)} {f1} vs {flag(f2)} {f2}")
    L.append(f"- 📊 **Expected Score:** {expected_score:.2f} / 203\n")

    L.extend(render_scoring_summary(actual_scores, actual_points, total_played, total_correct))
    L.extend(render_group_placements(bracket, per_team_probs, fixtures, results_parsed))
    L.extend(render_knockout_bracket(bracket, per_team_probs))
    L.extend(render_champion_probabilities(per_team_probs))
    L.extend(render_validation(bracket, config))
    L.extend(render_per_team_table(per_team_probs))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"Written {output_path}")
    print(f"Expected Score: {expected_score:.2f} / 203")
    print(f"Actual Score: {actual_points:.0f} / 203")
    print(f"Champion: {flag(winner)} {winner}")
    if total_played > 0:
        print(f"Accuracy: {total_correct}/{total_played} ({total_correct/total_played*100:.1f}%)")
    else:
        print("No matches played yet")


def main():
    parser = argparse.ArgumentParser(description="Generate visual results.md from bracket.json")
    parser.add_argument("--input", default="_data/bracket.json")
    parser.add_argument("--fixtures", default="_data/raw/openfootball/worldcup-2026.json")
    parser.add_argument("--results", default="_data/results.json")
    parser.add_argument("--output", default="results.md")
    args = parser.parse_args()
    generate_results(args.input, args.fixtures, args.results, args.output)


if __name__ == "__main__":
    main()
