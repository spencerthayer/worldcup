#!/usr/bin/env python3
"""
Generate a visual results.md from bracket.json.

Reads _data/bracket.json and produces results.md in the root directory
showing the full bracket with country flags, probabilities, and scoring.

Usage:
    python3 generate_results.py
    python3 generate_results.py --input _data/bracket.json --output results.md
"""

import argparse
import json
import math
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


def flag(name):
    return FLAGS.get(name, "🏳️")


def pct(p):
    return f"{p * 100:.1f}%"


def load_bracket(path):
    with open(path) as f:
        return json.load(f)


def compute_expected_score(bracket, per_team_probs):
    score = 0.0
    for g, teams in bracket["group_placements"].items():
        for pos, team in enumerate(teams):
            placement_probs = per_team_probs.get(team, {}).get("placement", {})
            key = str(pos + 1)
            p = placement_probs.get(key, 0)
            score += p * 1
    stage_key = {
        "round_of_32": "r32", "round_of_16": "r16",
        "quarter_finals": "qf", "semi_finals": "sf",
        "finalists": "final", "winner": "champion",
    }
    for stage, key in stage_key.items():
        points = STAGE_POINTS[stage]
        for team in bracket.get(stage, []):
            p = per_team_probs.get(team, {}).get(key, 0)
            score += p * points
    return score


def render_group_placements(bracket, per_team_probs):
    lines = []
    lines.append("## 📊 Group Placements\n")
    lines.append("| Group | 1st | 2nd | 3rd | 4th |")
    lines.append("|:---:|:---:|:---:|:---:|:---:|")
    for g in sorted(bracket["group_placements"].keys()):
        teams = bracket["group_placements"][g]
        cells = []
        for i, t in enumerate(teams):
            placement_probs = per_team_probs.get(t, {}).get("placement", {})
            p = placement_probs.get(str(i + 1), 0)
            cells.append(f"{flag(t)} {t} ({pct(p)})")
        lines.append(f"| **{g}** | {' | '.join(cells)} |")
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
    for stage, key in stage_key.items():
        if stage == "winner":
            w = bracket.get("winner", "")
            picks = [w] if w else []
        else:
            picks = bracket.get(stage, [])
        points = STAGE_POINTS[stage]
        stage_score = sum(per_team_probs.get(t, {}).get(key, 0) * points for t in picks)
        total += stage_score
        max_pts = len(picks) * points
        rows.append((stage.replace("_", " ").title(), len(picks), points, max_pts, stage_score))
        p = probs.get("champion", 0)
        if p > 0:
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            lines.append(f"| {medal} | {flag(team)} {team} | {pct(p)} |")
    lines.append("")
    return lines


def render_stage_breakdown(bracket, per_team_probs):
    lines = []
    lines.append("## 📈 Expected Points Breakdown\n")

    total = 0.0
    rows = []

    gp_score = 0.0
    for g, teams in bracket["group_placements"].items():
        for pos, team in enumerate(teams):
            placement_probs = per_team_probs.get(team, {}).get("placement", {})
            p = placement_probs.get(str(pos + 1), 0)
            gp_score += p * 1
    total += gp_score
    rows.append(("Group Placement", 48, 1, 48, gp_score))

    stage_key = {
        "round_of_32": "r32", "round_of_16": "r16",
        "quarter_finals": "qf", "semi_finals": "sf",
        "finalists": "final", "winner": "champion",
    }
    for stage, key in stage_key.items():
        if stage == "winner":
            w = bracket.get("winner", "")
            picks = [w] if w else []
        else:
            picks = bracket.get(stage, [])
        points = STAGE_POINTS[stage]
        stage_score = sum(per_team_probs.get(t, {}).get(key, 0) * points for t in picks)
        total += stage_score
        max_pts = len(picks) * points
        rows.append((stage.replace("_", " ").title(), len(picks), points, max_pts, stage_score))

    lines.append("| Stage | Picks | Pts/Pick | Max | Expected | % of Max |")
    lines.append("|:---|:---:|:---:|:---:|:---:|:---:|")
    for name, picks, pts, max_pts, expected in rows:
        pct_max = (expected / max_pts * 100) if max_pts > 0 else 0
        lines.append(f"| {name} | {picks} | {pts} | {max_pts} | **{expected:.2f}** | {pct_max:.1f}% |")
    lines.append(f"| **Total** | | | **203** | **{total:.2f}** | {total/203*100:.1f}% |")
    lines.append("")
    return lines


def render_validation(bracket, config):
    lines = []
    lines.append("## ⚙️ Simulation Config\n")
    lines.append(f"- **Model:** {config['model']}")
    lines.append(f"- **Simulations:** {config['sims']:,}")
    lines.append(f"- **Seed:** {config['seed']}")
    lines.append(f"- **Strategy:** {config['strategy']}")
    lines.append(f"- **Probabilities:** {config['probabilities']}")

    sims = config['sims']
    se = math.sqrt(0.25 / sims)
    lines.append(f"- **Simulation accuracy:** ±{se*100:.3f}% (SE bound at p=0.5)")
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


def generate_results(bracket_path, output_path):
    bracket = load_bracket(bracket_path)
    config = bracket["config"]
    per_team_probs = bracket.get("per_team_probs", {})

    expected_score = compute_expected_score(bracket, per_team_probs)

    L = []
    L.append("# 🏆 2026 World Cup Bracket Results\n")
    L.append(f"**Expected Score: {expected_score:.2f} / 203** ({expected_score/203*100:.1f}% of max)\n")

    winner = bracket.get("winner", "TBD")
    finalists = bracket.get("finalists", [])
    L.append("## 🎯 Summary\n")
    L.append(f"- 👑 **Champion:** {flag(winner)} {winner} ({pct(per_team_probs.get(winner, {}).get('champion', 0))})")
    if len(finalists) == 2:
        f1, f2 = sorted(finalists)
        L.append(f"- 🌟 **Final:** {flag(f1)} {f1} vs {flag(f2)} {f2}")
    L.append(f"- 📊 **Expected Points:** {expected_score:.2f} / 203")
    L.append(f"- 🎲 **Simulations:** {config['sims']:,} | **Seed:** {config['seed']}")
    L.append("")

    L.extend(render_group_placements(bracket, per_team_probs))
    L.extend(render_knockout_bracket(bracket, per_team_probs))
    L.extend(render_champion_probabilities(per_team_probs))
    L.extend(render_stage_breakdown(bracket, per_team_probs))
    L.extend(render_validation(bracket, config))
    L.extend(render_per_team_table(per_team_probs))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"Written {output_path} ({len(L)} lines)")
    print(f"Expected Score: {expected_score:.2f} / 203")
    print(f"Champion: {flag(winner)} {winner}")


def main():
    parser = argparse.ArgumentParser(description="Generate visual results.md from bracket.json")
    parser.add_argument("--input", default="_data/bracket.json")
    parser.add_argument("--output", default="results.md")
    args = parser.parse_args()
    generate_results(args.input, args.output)


if __name__ == "__main__":
    main()
