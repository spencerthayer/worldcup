#!/usr/bin/env python3
"""
Generate a visual results.md from bracket.json, comparing predictions against
actual match results stored in _data/results.json.

Handles partial groups — shows current standings as matches are played,
even mid-group. Final position scoring only locks in when all 6 matches
in a group are complete.

Scoring (203 points total):
- Group Stage Placement: +1pt per correct placement (48 picks, 48 max)
  Only scored when ALL 6 matches in a group have been played.
- Advance to Knockout: +1pt per correct team (32 picks, 32 max)
  Only scored when all groups are complete.
- Advance to Round of 16: +2pts per correct team (16 picks, 32 max)
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

from generate_bracket import nteam

# ── Country flag emojis ────────────────────────────────────────────────
FLAGS = {
    "Algeria": "🇩🇿", "Argentina": "🇦🇷", "Australia": "🇦🇺", "Austria": "🇦🇹",
    "Belgium": "🇧🇪", "Bosnia and Herzegovina": "🇧🇦", "Bosnia & Herzegovina": "🇧🇦", "Brazil": "🇧🇷",
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

# Prior-round winners determine whether a knockout advancement stage is resolved.
KNOCKOUT_ADVANCEMENT = [
    ("round_of_16", "round_of_16", range(73, 89), 16),
    ("quarter_finals", "quarter_finals", range(89, 97), 8),
    ("semi_finals", "semi_finals", range(97, 101), 4),
    ("finalists", "finalists", range(101, 103), 2),
    ("winner", "winner", range(104, 105), 1),
]

# FIFA 2026 knockout topology: child match_num -> (parent_a, parent_b).
# R32 matches 73-88 have no parents (seeded from groups).
BRACKET_CHILDREN = {
    89: (74, 77),
    90: (73, 75),
    91: (76, 78),
    92: (79, 80),
    93: (83, 84),
    94: (81, 82),
    95: (86, 88),
    96: (85, 87),
    97: (89, 90),
    98: (93, 94),
    99: (91, 92),
    100: (95, 96),
    101: (97, 98),
    102: (99, 100),
    104: (101, 102),
}

# Winning a match in this range advances the team into the listed prediction stage.
MATCH_ADVANCES_TO = {
    **{n: "round_of_16" for n in range(73, 89)},
    **{n: "quarter_finals" for n in range(89, 97)},
    **{n: "semi_finals" for n in range(97, 101)},
    **{n: "finalists" for n in range(101, 103)},
    104: "winner",
}

ROUND_LABEL = {
    "round_of_32": "R32",
    "round_of_16": "R16",
    "quarter_finals": "QF",
    "semi_finals": "SF",
    "final": "F",
    "winner": "Champ",
}

EMOJI_CHECK = "✅"
EMOJI_WRONG = "❌"
EMOJI_TIE = "🟰"
EMOJI_PENDING = "⏳"
EMOJI_LIVE = "🔴"


def flag(name):
    if not name or name == "—":
        return "🏳️"
    return FLAGS.get(name, FLAGS.get(nteam(name), "🏳️"))


def same_team(left, right):
    return nteam(left) == nteam(right)


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
    for key, match in matches.items():
        norm_key = key.replace(" ", "_")
        parsed[norm_key] = {
            "team1": match.get("team1", "").replace(" ", "_"),
            "team2": match.get("team2", "").replace(" ", "_"),
            "score1": match.get("score1"), "score2": match.get("score2"),
            "winner": match.get("winner"),
            "played": match.get("winner") is not None,
        }
    return parsed


def parse_knockout_results(results):
    knockout = results.get("knockout_matches", {})
    parsed = {}
    for key, match in knockout.items():
        winner = match.get("winner")
        played = bool(match.get("played")) and winner not in (None, "draw")
        parsed[key] = {
            "team1": match.get("team1", ""),
            "team2": match.get("team2", ""),
            "score1": match.get("score1"),
            "score2": match.get("score2"),
            "winner": winner,
            "match_num": match.get("match_num"),
            "round": match.get("round"),
            "played": played,
        }
    return parsed


def knockout_round_winners(ko_parsed, match_num_range):
    winners = set()
    for match in ko_parsed.values():
        match_num = match.get("match_num")
        if match_num not in match_num_range or not match.get("played"):
            continue
        winners.add(nteam(match["winner"]))
    return winners


def is_knockout_round_complete(ko_parsed, match_num_range, expected_matches):
    decided = [
        match for match in ko_parsed.values()
        if match.get("match_num") in match_num_range and match.get("played")
    ]
    return len(decided) >= expected_matches


def score_advancement_picks(scores, score_key, predicted, actual, points_per, total_played, total_correct):
    predicted_norm = {nteam(team) for team in predicted}
    actual_norm = {nteam(team) for team in actual}
    for team in sorted(predicted_norm):
        if team in actual_norm:
            scores[score_key]["correct"] += 1
            scores[score_key]["points"] += points_per
            total_correct += 1
        total_played += 1
    scores[score_key]["total"] = len(predicted_norm)
    return total_played, total_correct


def compute_group_standings(fixtures, results_parsed, group_letter):
    """Compute current group standings from played matches (handles partial)."""
    group_matches = [m for m in fixtures if m.get("group") == group_letter]
    teams = set()
    for m in group_matches:
        teams.add(m["team1"])
        teams.add(m["team2"])
    standings = {t: {"pts": 0, "gf": 0, "ga": 0, "gd": 0, "played": 0} for t in teams}
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
        standings[t1]["played"] += 1
        standings[t2]["played"] += 1
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
    return ranked, standings, group_matches


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


def count_played_matches(group_matches, results_parsed):
    """Count how many matches in a group have been played."""
    count = 0
    for m in group_matches:
        t1n = m["team1"].replace(" ", "_")
        t2n = m["team2"].replace(" ", "_")
        key = f"{t1n}_vs_{t2n}"
        rk = f"{t2n}_vs_{t1n}"
        r = results_parsed.get(key) or results_parsed.get(rk)
        if r and r.get("played"):
            count += 1
    return count


def compute_scores(bracket, fixtures, results_parsed, ko_parsed):
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
    group_total = 0
    for g in sorted(bracket["group_placements"].keys()):
        predicted = bracket["group_placements"][g]
        fixture_group = f"Group {g}" if not g.startswith("Group ") else g
        group_matches = [m for m in fixtures if m.get("group") == fixture_group]
        if not is_group_complete(group_matches, results_parsed):
            continue
        ranked, _, _ = compute_group_standings(fixtures, results_parsed, fixture_group)
        for pos in range(4):
            pred_team = predicted[pos] if pos < len(predicted) else None
            actual_team = ranked[pos] if pos < len(ranked) else None
            if pred_team and actual_team:
                if same_team(pred_team, actual_team):
                    scores["group_placement"]["correct"] += 1
                    scores["group_placement"]["points"] += 1
                    total_correct += 1
                group_total += 1
                total_played += 1
    scores["group_placement"]["total"] = group_total

    # ── R32 qualifiers (only when all groups complete) ──
    groups_list = sorted(set(m["group"] for m in fixtures if m.get("group")))
    all_groups_complete = all(
        is_group_complete(
            [m for m in fixtures if m.get("group") == g],
            results_parsed
        )
        for g in groups_list
    )
    if all_groups_complete:
        predicted_r32 = {nteam(team) for team in bracket.get("round_of_32", [])}
        actual_r32 = set()
        all_thirds = []
        for g in groups_list:
            ranked, standings, _ = compute_group_standings(fixtures, results_parsed, g)
            if len(ranked) >= 2:
                actual_r32.add(nteam(ranked[0]))
                actual_r32.add(nteam(ranked[1]))
            if len(ranked) >= 3:
                all_thirds.append((ranked[2], standings[ranked[2]]["pts"],
                                  standings[ranked[2]]["gd"], standings[ranked[2]]["gf"]))
        all_thirds.sort(key=lambda x: (-x[1], -x[2], -x[3]))
        for team, _, _, _ in all_thirds[:8]:
            actual_r32.add(nteam(team))
        for team in sorted(predicted_r32):
            if team in actual_r32:
                scores["round_of_32"]["correct"] += 1
                scores["round_of_32"]["points"] += 1
                total_correct += 1
            total_played += 1
        scores["round_of_32"]["total"] = len(predicted_r32)
    else:
        scores["round_of_32"]["pending"] = len(bracket.get("round_of_32", []))

    # ── Knockout advancement stages ──
    for score_key, bracket_key, match_num_range, expected_matches in KNOCKOUT_ADVANCEMENT:
        if score_key == "winner":
            predicted = [bracket.get("winner", "")] if bracket.get("winner") else []
        else:
            predicted = bracket.get(bracket_key, [])
        if not predicted:
            continue
        if not is_knockout_round_complete(ko_parsed, match_num_range, expected_matches):
            scores[score_key]["pending"] = len(predicted)
            continue
        actual = knockout_round_winners(ko_parsed, match_num_range)
        total_played, total_correct = score_advancement_picks(
            scores, score_key, predicted, actual, STAGE_POINTS[score_key],
            total_played, total_correct,
        )

    total_points = sum(s["points"] for s in scores.values())
    return scores, total_points, total_played, total_correct


def compute_expected_score_from_probs(bracket, per_team_probs):
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
        played = count_played_matches(group_matches, results_parsed)
        total = len(group_matches)
        ranked, standings, _ = compute_group_standings(fixtures, results_parsed, fixture_group)

        # Group header with match progress
        if complete:
            status = "✅ Final"
        elif played > 0:
            status = f"{EMOJI_LIVE} {played}/{total} matches played"
        else:
            status = f"{EMOJI_PENDING} Not started"
        lines.append(f"### Group {g} — {status}\n")

        lines.append("| Pos | Predicted | Actual | Pts | GD | Pld | Result |")
        lines.append("|:---:|:---|:---|:---:|:---:|:---:|:---:|")
        for pos in range(4):
            pred_team = predicted[pos] if pos < len(predicted) else "—"
            if pos < len(ranked):
                actual_team = ranked[pos]
                s = standings.get(actual_team, {})
                pts = s.get("pts", 0)
                gd = s.get("gd", 0)
                gd_str = f"+{gd}" if gd > 0 else str(gd)
                pld = s.get("played", 0)
            else:
                actual_team = "—"
                pts, gd_str, pld = "—", "—", "—"

            # Result marker
            if complete and pred_team != "—" and actual_team != "—":
                if same_team(pred_team, actual_team):
                    result = EMOJI_CHECK
                else:
                    result = EMOJI_WRONG
            elif played > 0 and pred_team != "—" and actual_team != "—":
                if same_team(pred_team, actual_team):
                    result = f"{EMOJI_LIVE} (projected)"
                else:
                    result = f"{EMOJI_LIVE} (projected)"
            else:
                result = EMOJI_PENDING

            pred_str = f"{flag(pred_team)} {pred_team}" if pred_team != "—" else "—"
            actual_str = f"{flag(actual_team)} {actual_team}" if actual_team != "—" else "—"
            pos_label = ["1st", "2nd", "3rd", "4th"][pos]
            lines.append(f"| {pos_label} | {pred_str} | {actual_str} | {pts} | {gd_str} | {pld} | {result} |")

        # Show upcoming matches for this group
        if not complete:
            upcoming = []
            for m in group_matches:
                t1n = m["team1"].replace(" ", "_")
                t2n = m["team2"].replace(" ", "_")
                key = f"{t1n}_vs_{t2n}"
                rk = f"{t2n}_vs_{t1n}"
                r = results_parsed.get(key) or results_parsed.get(rk)
                if not r or not r.get("played"):
                    date_str = m.get("date", "TBD")
                    time_str = m.get("time", "")
                    upcoming.append(f"  - {date_str} {time_str}: {flag(m['team1'])} {m['team1']} vs {flag(m['team2'])} {m['team2']}")
            if upcoming:
                lines.append(f"\n**Upcoming:**\n")
                for u in upcoming:
                    lines.append(u)

        lines.append("")
    return lines


def ko_by_match_num(ko_parsed):
    by_num = {}
    for match in ko_parsed.values():
        match_num = match.get("match_num")
        if match_num is not None:
            by_num[match_num] = match
    return by_num


def predicted_stage_sets(bracket):
    return {
        "round_of_16": {nteam(t) for t in bracket.get("round_of_16", [])},
        "quarter_finals": {nteam(t) for t in bracket.get("quarter_finals", [])},
        "semi_finals": {nteam(t) for t in bracket.get("semi_finals", [])},
        "finalists": {nteam(t) for t in bracket.get("finalists", [])},
        "winner": {nteam(bracket["winner"])} if bracket.get("winner") else set(),
        "round_of_32": {nteam(t) for t in bracket.get("round_of_32", [])},
    }


def mermaid_escape(text):
    """Escape text for Mermaid node labels (GitHub-compatible)."""
    return (
        str(text)
        .replace('"', "'")
        .replace("[", "(")
        .replace("]", ")")
        .replace("\n", " ")
    )


def short_team(name):
    """Compact display name for Mermaid nodes."""
    name = nteam(name) if name else "?"
    aliases = {
        "Bosnia and Herzegovina": "Bosnia",
        "Czech Republic": "Czechia",
        "South Korea": "S. Korea",
        "South Africa": "S. Africa",
        "Saudi Arabia": "Saudi",
        "New Zealand": "N. Zealand",
        "Ivory Coast": "C. d'Ivoire",
        "Netherlands": "Neth.",
        "Switzerland": "Swiss",
        "DR Congo": "DR Congo",
        "Cape Verde": "C. Verde",
        "United States": "USA",
    }
    return aliases.get(name, name)


def match_css_class(match, predicted_sets):
    """Color class for a match node: hit / miss / pending."""
    if not match or not match.get("played"):
        return "pending"
    winner = nteam(match["winner"])
    advances_to = MATCH_ADVANCES_TO.get(match.get("match_num"))
    if not advances_to:
        return "pending"
    if advances_to == "winner":
        return "hit" if winner in predicted_sets["winner"] else "miss"
    predicted = predicted_sets.get(advances_to, set())
    return "hit" if winner in predicted else "miss"


def format_match_label(match_num, match, round_key, compact=False):
    round_tag = ROUND_LABEL.get(round_key, str(match_num))
    if not match:
        return f"{round_tag} #{match_num}: TBD"
    t1 = f"{flag(match['team1'])} {short_team(match['team1'])}"
    t2 = f"{flag(match['team2'])} {short_team(match['team2'])}"
    if not match.get("played") or match.get("score1") is None or match.get("score2") is None:
        if compact:
            return f"{round_tag}: {t1} vs {t2}"
        return f"{round_tag} #{match_num}: {t1} vs {t2}"
    s1, s2 = match["score1"], match["score2"]
    w_short = f"{flag(match['winner'])} {short_team(match['winner'])}"
    suffix = "*" if s1 == s2 else ""  # * = AET/pens
    if compact:
        return f"{round_tag}: {t1} {s1}-{s2}{suffix} {t2} → {w_short}"
    return f"{round_tag} #{match_num}: {t1} {s1}-{s2} {t2}{suffix} → {w_short}"


def resolve_bracket_match(match_num, by_num, round_key):
    """Return match dict, synthesizing pending SF/Final from parent winners."""
    match = by_num.get(match_num)
    if match is not None:
        return match
    if match_num not in BRACKET_CHILDREN:
        return None
    pa, pb = BRACKET_CHILDREN[match_num]
    wa = by_num.get(pa)
    wb = by_num.get(pb)
    t1 = wa["winner"] if wa and wa.get("played") else f"W{pa}"
    t2 = wb["winner"] if wb and wb.get("played") else f"W{pb}"
    return {
        "team1": t1,
        "team2": t2,
        "score1": None,
        "score2": None,
        "winner": "draw",
        "played": False,
        "match_num": match_num,
        "round": round_key if round_key != "final" else "final",
    }


def placement_group_summary(bracket, fixtures, results_parsed, group_letter):
    """Return (label, css_class) for one group's predicted vs actual placement."""
    predicted = bracket["group_placements"].get(group_letter, [])
    fixture_group = f"Group {group_letter}"
    group_matches = [m for m in fixtures if m.get("group") == fixture_group]
    if not group_matches:
        return f"Group {group_letter}: n/a", "pending"
    if not is_group_complete(group_matches, results_parsed):
        return f"{group_letter}: pending", "pending"
    ranked, _, _ = compute_group_standings(fixtures, results_parsed, fixture_group)
    correct = sum(
        1 for i in range(4)
        if i < len(predicted) and i < len(ranked) and same_team(predicted[i], ranked[i])
    )
    # Keep full team names; Mermaid is configured to use its natural full width.
    marks = []
    for i in range(4):
        pred = (
            f"{flag(predicted[i])} {short_team(predicted[i])}"
            if i < len(predicted)
            else "?"
        )
        if same_team(predicted[i], ranked[i]):
            marks.append(f"{pred}+")
        else:
            marks.append(f"{pred}×")
    label = f"{group_letter}: {correct}/4 {' '.join(marks)}"
    if correct == 4:
        css = "hit"
    elif correct == 0:
        css = "miss"
    else:
        css = "partial"
    return label, css


def emit_match_node(lines, node_classes, by_num, predicted_sets, match_num, round_key, indent="    "):
    """Append one Mermaid match node and record its CSS class."""
    match = resolve_bracket_match(match_num, by_num, round_key)
    label_round = "final" if match_num == 104 else round_key
    label = mermaid_escape(
        format_match_label(match_num, match, label_round, compact=True)
    )
    node_id = f"m{match_num}"
    css = match_css_class(match, predicted_sets)
    lines.append(f'{indent}{node_id}["{label}"]:::{css}')
    node_classes[node_id] = css


def render_bracket_mermaid(bracket, ko_parsed, fixtures=None, results_parsed=None):
    """
    GitHub-compatible Mermaid flowchart with both:

    1. Stage order: Placement → Knockout → R16 → QF → SF → Finals → Winner
    2. Bracket-path grouping inside each knockout stage (paths to each QF / SF)
    """
    by_num = ko_by_match_num(ko_parsed)
    predicted_sets = predicted_stage_sets(bracket)
    fixtures = fixtures or []
    results_parsed = results_parsed or {}
    lines = []
    lines.append("## 🗺️ Bracket Progress vs Prediction\n")
    lines.append(
        "Reads **top → bottom**: Placement → Knockout → R16 → QF → SF → Finals → Winner. "
        "Inside each stage, matches stay grouped by bracket path (`→ QF 97`, etc.). "
        "Node color shows prediction accuracy:\n"
    )
    lines.append("- 🟢 **Green** — predicted correctly for this stage")
    lines.append("- 🟡 **Yellow** — partial group placement hit")
    lines.append("- 🔴 **Red** — miss / upset vs prediction")
    lines.append("- ⚪ **Gray** — not resolved yet")
    lines.append("- `*` on a score — decided in extra time or penalties\n")

    pred_path = []
    if bracket.get("winner"):
        pred_path.append(f"Champion: {bracket['winner']}")
    if bracket.get("finalists"):
        pred_path.append("Final: " + " vs ".join(sorted(bracket["finalists"])))
    if bracket.get("semi_finals"):
        pred_path.append("SF: " + ", ".join(sorted(bracket["semi_finals"])))
    if pred_path:
        lines.append("**Predicted deep run:** " + " · ".join(pred_path) + "\n")

    def start_stage_chart(title):
        """Start a standalone stage diagram so GitHub cannot reorder stages."""
        lines.append(f"### {title}\n")
        lines.append("```mermaid")
        lines.append("flowchart TB")
        lines.append(
            "  classDef hit fill:#d1fae5,stroke:#059669,color:#064e3b,stroke-width:2px"
        )
        lines.append(
            "  classDef miss fill:#fee2e2,stroke:#dc2626,color:#7f1d1d,stroke-width:2px"
        )
        lines.append(
            "  classDef partial fill:#fef9c3,stroke:#ca8a04,color:#713f12,stroke-width:2px"
        )
        lines.append(
            "  classDef pending fill:#f3f4f6,stroke:#9ca3af,color:#374151,stroke-width:1px"
        )
        lines.append(
            "  classDef champ fill:#fef3c7,stroke:#d97706,color:#78350f,stroke-width:3px"
        )
        lines.append("")

    def end_stage_chart():
        lines.append("```")
        lines.append("")

    node_classes = {}

    # Path groupings that feed each quarter-final (used across Knockout / R16 / QF).
    qf_paths = [
        ("QF97", "→ QF 97", {
            "round_of_32": [73, 75, 74, 77],
            "round_of_16": [90, 89],
            "quarter_finals": [97],
        }),
        ("QF99", "→ QF 99", {
            "round_of_32": [76, 78, 79, 80],
            "round_of_16": [91, 92],
            "quarter_finals": [99],
        }),
        ("QF98", "→ QF 98", {
            "round_of_32": [81, 82, 83, 84],
            "round_of_16": [94, 93],
            "quarter_finals": [98],
        }),
        ("QF100", "→ QF 100", {
            "round_of_32": [85, 87, 86, 88],
            "round_of_16": [96, 95],
            "quarter_finals": [100],
        }),
    ]

    def chain_nodes(node_ids):
        """Force a vertical sequence inside a stage/path group."""
        for left, right in zip(node_ids, node_ids[1:]):
            lines.append(f"  {left} --> {right}")

    # Separate blocks enforce this exact Markdown order on GitHub.
    start_stage_chart("1. Placement")
    lines.append('  subgraph sgPlacement["Placement"]')
    lines.append("    direction TB")
    placement_bands = [
        ("placeAD", "Groups A–D", ["A", "B", "C", "D"]),
        ("placeEH", "Groups E–H", ["E", "F", "G", "H"]),
        ("placeIL", "Groups I–L", ["I", "J", "K", "L"]),
    ]
    placement_nodes = []
    for band_id, band_title, letters in placement_bands:
        lines.append(f'    subgraph {band_id}["{band_title}"]')
        lines.append("      direction TB")
        band_nodes = []
        for letter in letters:
            if letter not in bracket.get("group_placements", {}):
                continue
            label, css = placement_group_summary(
                bracket, fixtures, results_parsed, letter
            )
            node_id = f"grp{letter}"
            lines.append(f'      {node_id}["{mermaid_escape(label)}"]:::{css}')
            node_classes[node_id] = css
            band_nodes.append(node_id)
            placement_nodes.append(node_id)
        lines.append("    end")
        # Chain within band so groups stack, not sit side-by-side
        for left, right in zip(band_nodes, band_nodes[1:]):
            lines.append(f"      {left} --> {right}")
    lines.append("  end")
    lines.append("")
    # Chain bands: D → E, H → I
    if "grpD" in placement_nodes and "grpE" in placement_nodes:
        lines.append("  grpD --> grpE")
    if "grpH" in placement_nodes and "grpI" in placement_nodes:
        lines.append("  grpH --> grpI")
    lines.append("")
    end_stage_chart()

    # 2. Knockout (R32) — path groups stacked vertically
    start_stage_chart("2. Knockout")
    lines.append('  subgraph sgKnockout["Knockout (R32)"]')
    lines.append("    direction TB")
    knockout_path_tails = []
    knockout_path_heads = []
    for path_id, path_title, path_matches in qf_paths:
        lines.append(f'    subgraph ko{path_id}["{path_title}"]')
        lines.append("      direction TB")
        path_nodes = []
        for match_num in path_matches["round_of_32"]:
            emit_match_node(
                lines, node_classes, by_num, predicted_sets,
                match_num, "round_of_32", indent="      ",
            )
            path_nodes.append(f"m{match_num}")
        lines.append("    end")
        for left, right in zip(path_nodes, path_nodes[1:]):
            lines.append(f"      {left} --> {right}")
        knockout_path_heads.append(path_nodes[0])
        knockout_path_tails.append(path_nodes[-1])
    lines.append("  end")
    lines.append("")
    # Stack path groups under each other
    for left, right in zip(knockout_path_tails, knockout_path_heads[1:]):
        lines.append(f"  {left} --> {right}")
    lines.append("")
    end_stage_chart()

    # 3. R16 — path groups stacked vertically
    start_stage_chart("3. R16")
    lines.append('  subgraph sgR16["R16"]')
    lines.append("    direction TB")
    r16_path_tails = []
    r16_path_heads = []
    for path_id, path_title, path_matches in qf_paths:
        lines.append(f'    subgraph r16{path_id}["{path_title}"]')
        lines.append("      direction TB")
        path_nodes = []
        for match_num in path_matches["round_of_16"]:
            emit_match_node(
                lines, node_classes, by_num, predicted_sets,
                match_num, "round_of_16", indent="      ",
            )
            path_nodes.append(f"m{match_num}")
        lines.append("    end")
        for left, right in zip(path_nodes, path_nodes[1:]):
            lines.append(f"      {left} --> {right}")
        r16_path_heads.append(path_nodes[0])
        r16_path_tails.append(path_nodes[-1])
    lines.append("  end")
    lines.append("")
    for left, right in zip(r16_path_tails, r16_path_heads[1:]):
        lines.append(f"  {left} --> {right}")
    lines.append("")
    end_stage_chart()

    # 4. QF — path groups stacked vertically
    start_stage_chart("4. QF")
    lines.append('  subgraph sgQF["Quarter-Finals"]')
    lines.append("    direction TB")
    qf_nodes = []
    for path_id, path_title, path_matches in qf_paths:
        lines.append(f'    subgraph qf{path_id}["{path_title}"]')
        lines.append("      direction TB")
        for match_num in path_matches["quarter_finals"]:
            emit_match_node(
                lines, node_classes, by_num, predicted_sets,
                match_num, "quarter_finals", indent="      ",
            )
            qf_nodes.append(f"m{match_num}")
        lines.append("    end")
    lines.append("  end")
    lines.append("")
    chain_nodes(qf_nodes)
    lines.append("")
    end_stage_chart()

    # 5. SF — stacked
    start_stage_chart("5. SF")
    lines.append('  subgraph sgSF["Semi-Finals"]')
    lines.append("    direction TB")
    lines.append('    subgraph sf101["→ SF 101 (W97 vs W98)"]')
    lines.append("      direction TB")
    emit_match_node(
        lines, node_classes, by_num, predicted_sets, 101, "semi_finals", indent="      ",
    )
    lines.append("    end")
    lines.append('    subgraph sf102["→ SF 102 (W99 vs W100)"]')
    lines.append("      direction TB")
    emit_match_node(
        lines, node_classes, by_num, predicted_sets, 102, "semi_finals", indent="      ",
    )
    lines.append("    end")
    lines.append("  end")
    lines.append("")
    lines.append("  m101 --> m102")
    lines.append("")
    end_stage_chart()

    # 6. Finals
    start_stage_chart("6. Finals")
    lines.append('  subgraph sgFinals["Final"]')
    lines.append("    direction TB")
    emit_match_node(
        lines, node_classes, by_num, predicted_sets, 104, "final", indent="    ",
    )
    lines.append("  end")
    lines.append("")
    end_stage_chart()

    # 7. Winner
    start_stage_chart("7. Winner")
    lines.append('  subgraph sgWinner["Winner"]')
    lines.append("    direction TB")
    final_match = resolve_bracket_match(104, by_num, "final")
    if final_match and final_match.get("played"):
        champ = short_team(final_match["winner"])
        champion_css = (
            "champ" if nteam(final_match["winner"]) in predicted_sets["winner"] else "miss"
        )
        lines.append(
            f'    champion["Champion: {mermaid_escape(champ)}"]:::{champion_css}'
        )
        node_classes["champion"] = champion_css
    else:
        pred_champ = short_team(bracket.get("winner", "TBD"))
        lines.append(
            f'    champion["Champion TBD — predicted: {mermaid_escape(pred_champ)}"]:::pending'
        )
        node_classes["champion"] = "pending"
    lines.append("  end")
    lines.append("")
    end_stage_chart()

    # Compact prediction accuracy strip for knockout stages
    lines.append("### Knockout prediction hits\n")
    lines.append("| Stage | Predicted teams that arrived | Misses |")
    lines.append("|:---|:---|:---|")
    stage_rows = [
        ("R16", predicted_sets["round_of_16"], range(73, 89), 16),
        ("QF", predicted_sets["quarter_finals"], range(89, 97), 8),
        ("SF", predicted_sets["semi_finals"], range(97, 101), 4),
        ("Final", predicted_sets["finalists"], range(101, 103), 2),
        ("Champion", predicted_sets["winner"], range(104, 105), 1),
    ]
    for stage, pred, match_range, expected in stage_rows:
        if not is_knockout_round_complete(ko_parsed, match_range, expected):
            lines.append(f"| {stage} | _pending_ | _pending_ |")
            continue
        actual = knockout_round_winners(ko_parsed, match_range)
        hits = sorted(pred & actual)
        misses = sorted(pred - actual)
        hit_s = ", ".join(hits) if hits else "—"
        miss_s = ", ".join(misses) if misses else "—"
        lines.append(f"| {stage} | {hit_s} | {miss_s} |")
    lines.append("")
    return lines


def render_vertical_bracket_mermaid(
    bracket, ko_parsed, fixtures=None, results_parsed=None
):
    """
    Render one strictly top-to-bottom Mermaid chart.

    Mermaid may reorder nested subgraphs regardless of ``flowchart TB``. This
    representation uses stage and path header nodes in one explicit chain, so
    GitHub must preserve Placement → Winner order while retaining grouping.
    """
    by_num = ko_by_match_num(ko_parsed)
    predicted_sets = predicted_stage_sets(bracket)
    fixtures = fixtures or []
    results_parsed = results_parsed or {}

    lines = []
    lines.append("## 🗺️ Bracket Progress vs Prediction\n")
    lines.append(
        "One chart with stage rows read **top → bottom**. Within each row, "
        "the requested groups run **left → right**.\n"
    )
    lines.append("- 🟢 **Green** — predicted correctly for this stage")
    lines.append("- 🟡 **Yellow** — partial group placement hit")
    lines.append("- 🔴 **Red** — miss / upset vs prediction")
    lines.append("- ⚪ **Gray** — not resolved yet")
    lines.append("- `*` on a score — decided in extra time or penalties\n")

    pred_path = []
    if bracket.get("winner"):
        pred_path.append(f"Champion: {bracket['winner']}")
    if bracket.get("finalists"):
        pred_path.append("Final: " + " vs ".join(sorted(bracket["finalists"])))
    if bracket.get("semi_finals"):
        pred_path.append("SF: " + ", ".join(sorted(bracket["semi_finals"])))
    if pred_path:
        lines.append("**Predicted deep run:** " + " · ".join(pred_path) + "\n")

    lines.append("```mermaid")
    lines.append(
        "%%{init: {\"flowchart\": {\"useMaxWidth\": false, \"nodeSpacing\": 48, "
        "\"rankSpacing\": 48}, \"themeVariables\": {\"fontSize\": \"14px\"}}}%%"
    )
    lines.append("flowchart TB")
    lines.append(
        "  classDef hit fill:#d1fae5,stroke:#059669,color:#064e3b,stroke-width:2px"
    )
    lines.append(
        "  classDef miss fill:#fee2e2,stroke:#dc2626,color:#7f1d1d,stroke-width:2px"
    )
    lines.append(
        "  classDef partial fill:#fef9c3,stroke:#ca8a04,color:#713f12,stroke-width:2px"
    )
    lines.append(
        "  classDef pending fill:#f3f4f6,stroke:#9ca3af,color:#374151,stroke-width:1px"
    )
    lines.append(
        "  classDef champ fill:#fef3c7,stroke:#d97706,color:#78350f,stroke-width:3px"
    )
    lines.append("")

    def append_match(match_num, round_key, indent="      "):
        match = resolve_bracket_match(match_num, by_num, round_key)
        label_round = "final" if match_num == 104 else round_key
        label = mermaid_escape(
            format_match_label(match_num, match, label_round, compact=True)
        )
        css = match_css_class(match, predicted_sets)
        lines.append(f'{indent}m{match_num}["{label}"]:::{css}')

    def append_match_group(group_id, title, match_nums, round_key):
        lines.append(f'    subgraph {group_id}["{title}"]')
        lines.append("      direction TB")
        node_ids = []
        for match_num in match_nums:
            append_match(match_num, round_key)
            node_ids.append(f"m{match_num}")
        for left, right in zip(node_ids, node_ids[1:]):
            lines.append(f"      {left} --> {right}")
        lines.append("    end")

    # Path order requested for every knockout row.
    qf_paths = [
        ("97", [73, 75, 74, 77], [90, 89], [97]),
        ("98", [81, 82, 83, 84], [94, 93], [98]),
        ("99", [76, 78, 79, 80], [91, 92], [99]),
        ("100", [85, 87, 86, 88], [96, 95], [100]),
    ]

    # Row 1: Placement; three horizontal groups with vertical contents.
    lines.append('  subgraph sgPlacement["1. Placement"]')
    lines.append("    direction LR")
    placement_bands = [
        ("placeAD", "Groups A–D", ["A", "B", "C", "D"]),
        ("placeEH", "Groups E–H", ["E", "F", "G", "H"]),
        ("placeIL", "Groups I–L", ["I", "J", "K", "L"]),
    ]
    for band_id, band_title, letters in placement_bands:
        lines.append(f'    subgraph {band_id}["{band_title}"]')
        lines.append("      direction TB")
        group_nodes = []
        for letter in letters:
            if letter not in bracket.get("group_placements", {}):
                continue
            label, css = placement_group_summary(
                bracket, fixtures, results_parsed, letter
            )
            lines.append(
                f'      grp{letter}["{mermaid_escape(label)}"]:::{css}'
            )
            group_nodes.append(f"grp{letter}")
        for left, right in zip(group_nodes, group_nodes[1:]):
            lines.append(f"      {left} --> {right}")
        lines.append("    end")
    # Linking the subgraphs (not their nodes) preserves each group's TB
    # direction and forces the group containers onto one LR row.
    lines.append("    placeAD --> placeEH")
    lines.append("    placeEH --> placeIL")
    lines.append("  end")
    lines.append("")

    # Row 2: Knockout; four horizontal QF-path groups.
    lines.append('  subgraph sgKnockout["2. Knockout"]')
    lines.append("    direction LR")
    for path_id, r32_matches, _, _ in qf_paths:
        append_match_group(
            f"koPath{path_id}", f"QF {path_id}", r32_matches, "round_of_32"
        )
    lines.append("    koPath97 --> koPath98")
    lines.append("    koPath98 --> koPath99")
    lines.append("    koPath99 --> koPath100")
    lines.append("  end")
    lines.append("")

    # Row 3: R16; same four horizontal path groups.
    lines.append('  subgraph sgR16["3. R16"]')
    lines.append("    direction LR")
    for path_id, _, r16_matches, _ in qf_paths:
        append_match_group(
            f"r16Path{path_id}", f"QF {path_id}", r16_matches, "round_of_16"
        )
    lines.append("    r16Path97 --> r16Path98")
    lines.append("    r16Path98 --> r16Path99")
    lines.append("    r16Path99 --> r16Path100")
    lines.append("  end")
    lines.append("")

    # Row 4: QF; one match in each horizontal path group.
    lines.append('  subgraph sgQF["4. QF"]')
    lines.append("    direction LR")
    for path_id, _, _, qf_matches in qf_paths:
        append_match_group(
            f"qfPath{path_id}", f"QF {path_id}", qf_matches, "quarter_finals"
        )
    lines.append("    qfPath97 --> qfPath98")
    lines.append("    qfPath98 --> qfPath99")
    lines.append("    qfPath99 --> qfPath100")
    lines.append("  end")
    lines.append("")

    # Row 5: SF; two horizontal bracket halves.
    lines.append('  subgraph sgSF["5. SF"]')
    lines.append("    direction LR")
    append_match_group(
        "sfPath101", "SF 101 · W97 vs W98", [101], "semi_finals"
    )
    append_match_group(
        "sfPath102", "SF 102 · W99 vs W100", [102], "semi_finals"
    )
    lines.append("    sfPath101 --> sfPath102")
    lines.append("  end")
    lines.append("")

    # Rows 6–7: Finalists and Winner.
    lines.append('  subgraph sgFinalists["6. Finalists"]')
    lines.append("    direction LR")
    append_match(104, "final", indent="    ")
    lines.append("  end")
    lines.append("")

    lines.append('  subgraph sgWinner["7. Winner"]')
    lines.append("    direction LR")
    final_match = resolve_bracket_match(104, by_num, "final")
    if final_match and final_match.get("played"):
        champ = (
            f"{flag(final_match['winner'])} "
            f"{short_team(final_match['winner'])}"
        )
        css = (
            "champ"
            if nteam(final_match["winner"]) in predicted_sets["winner"]
            else "miss"
        )
        lines.append(f'    champion["Champion: {mermaid_escape(champ)}"]:::{css}')
    else:
        predicted_winner = bracket.get("winner", "TBD")
        predicted = (
            f"{flag(predicted_winner)} {short_team(predicted_winner)}"
        )
        lines.append(
            f'    champion["Champion TBD · predicted: {mermaid_escape(predicted)}"]:::pending'
        )
    lines.append("  end")
    lines.append("")

    # Explicit subgraph-to-subgraph edges force stage rows top → bottom.
    lines.append("  sgPlacement --> sgKnockout")
    lines.append("  sgKnockout --> sgR16")
    lines.append("  sgR16 --> sgQF")
    lines.append("  sgQF --> sgSF")
    lines.append("  sgSF --> sgFinalists")
    lines.append("  sgFinalists --> sgWinner")
    lines.append("```")
    lines.append("")

    lines.append("### Knockout prediction hits\n")
    lines.append("| Stage | Predicted teams that arrived | Misses |")
    lines.append("|:---|:---|:---|")
    stage_rows = [
        ("R16", predicted_sets["round_of_16"], range(73, 89), 16),
        ("QF", predicted_sets["quarter_finals"], range(89, 97), 8),
        ("SF", predicted_sets["semi_finals"], range(97, 101), 4),
        ("Final", predicted_sets["finalists"], range(101, 103), 2),
        ("Champion", predicted_sets["winner"], range(104, 105), 1),
    ]
    for stage, pred, match_range, expected in stage_rows:
        if not is_knockout_round_complete(ko_parsed, match_range, expected):
            lines.append(f"| {stage} | _pending_ | _pending_ |")
            continue
        actual = knockout_round_winners(ko_parsed, match_range)
        hits = sorted(pred & actual)
        misses = sorted(pred - actual)
        hit_s = ", ".join(hits) if hits else "—"
        miss_s = ", ".join(misses) if misses else "—"
        lines.append(f"| {stage} | {hit_s} | {miss_s} |")
    lines.append("")
    return lines


def render_knockout_bracket(bracket, per_team_probs):
    lines = []
    lines.append("## 🏆 Predicted Knockout Picks\n")
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
    ko_parsed = parse_knockout_results(actual_results)

    actual_scores, actual_points, total_played, total_correct = compute_scores(
        bracket, fixtures, results_parsed, ko_parsed,
    )
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
    L.extend(
        render_vertical_bracket_mermaid(
            bracket, ko_parsed, fixtures, results_parsed
        )
    )
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
