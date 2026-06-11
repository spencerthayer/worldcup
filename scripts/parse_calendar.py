#!/usr/bin/env python3
"""
parse_calendar.py
==================
Download and parse the 2026 World Cup ICS calendar to extract match data,
odds, group standings, wild card analysis, and knockout bracket picks.

Usage:
    python3 parse_calendar.py
"""

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ICS_URL = "https://calendar.kubeia.io/world-cup-with-alarm-with-score-tv-united-states-of-america-the.ics"
ICS_LOCAL = Path(__file__).parent / "world-cup-calendar.ics"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def implied_prob(odds: float) -> float:
    return 1.0 / odds


def clean_team(raw: str) -> str:
    """Strip flag emojis and extra whitespace from a team name."""
    return re.sub(r"[^\x00-\x7F]+", "", raw).strip()


# ---------------------------------------------------------------------------
# ICS download / load
# ---------------------------------------------------------------------------

def download_ics() -> str:
    import urllib.request
    print(f"Downloading calendar from {ICS_URL} ...")
    with urllib.request.urlopen(ICS_URL) as resp:
        data = resp.read().decode("utf-8")
    ICS_LOCAL.write_text(data)
    print(f"Saved to {ICS_LOCAL}")
    return data


def load_ics() -> str:
    if not ICS_LOCAL.exists():
        return download_ics()
    return ICS_LOCAL.read_text()


def unfold(raw: str) -> str:
    """Unfold ICS continuation lines (newline + space)."""
    return re.sub(r"\r?\n ", "", raw)


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_events(content: str) -> list[dict]:
    events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, re.DOTALL)
    result = []
    for ev in events:
        summary = re.search(r"SUMMARY:(.*?)\n", ev)
        summary = summary.group(1).strip() if summary else ""

        odds_m = re.search(r"Average odds: ([\d.]+)/([\d.]+)/([\d.]+)", ev)
        betexp = re.search(r"BetExplorer: (https://www\.betexplorer\.com\S+)", ev)
        dtstart = re.search(r"DTSTART[^:]*:(\d{8})T(\d{4})", ev)
        group_m = re.search(r"Group ([A-L])", summary)
        teams_m = re.match(r"(.+?)\s*-\s*(.+?)\s*\(Match", summary)

        dt = ""
        if dtstart:
            d, t = dtstart.group(1), dtstart.group(2)
            dt = f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:]}Z"

        entry = {
            "summary": summary,
            "date": dt,
            "group": group_m.group(1) if group_m else None,
            "home_odds": float(odds_m.group(1)) if odds_m else None,
            "draw_odds": float(odds_m.group(2)) if odds_m else None,
            "away_odds": float(odds_m.group(3)) if odds_m else None,
            "betexplorer": betexp.group(1).strip() if betexp else None,
        }
        if teams_m:
            entry["home_team"] = clean_team(teams_m.group(1))
            entry["away_team"] = clean_team(teams_m.group(2))

        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Group analysis
# ---------------------------------------------------------------------------

def build_groups(events: list[dict]) -> dict:
    groups: dict = {}
    for ev in events:
        g = ev.get("group")
        if g is None or ev.get("home_odds") is None:
            continue
        if g not in groups:
            groups[g] = {"matches": [], "teams": set()}
        groups[g]["matches"].append(ev)
        groups[g]["teams"].add(ev["home_team"])
        groups[g]["teams"].add(ev["away_team"])
    return groups


def compute_standings(groups: dict) -> dict:
    for grp_name, grp in groups.items():
        exp_pts: dict[str, float] = {}
        win_pct: dict[str, float] = {}
        draw_pct: dict[str, float] = {}
        loss_pct: dict[str, float] = {}

        for team in grp["teams"]:
            wins, draws, losses = [], [], []
            for m in grp["matches"]:
                h = implied_prob(m["home_odds"])
                d = implied_prob(m["draw_odds"])
                a = implied_prob(m["away_odds"])
                overround = h + d + a
                h_f = h / overround
                d_f = d / overround
                a_f = a / overround
                if m["home_team"] == team:
                    wins.append(h_f)
                    draws.append(d_f)
                    losses.append(a_f)
                elif m["away_team"] == team:
                    wins.append(a_f)
                    draws.append(d_f)
                    losses.append(h_f)

            w = sum(wins) / len(wins)
            d = sum(draws) / len(draws)
            l = sum(losses) / len(losses)
            win_pct[team] = w
            draw_pct[team] = d
            loss_pct[team] = l
            exp_pts[team] = w * 3 + d * 1

        ranked = sorted(exp_pts, key=lambda t: exp_pts[t], reverse=True)
        grp["exp_pts"] = exp_pts
        grp["win_pct"] = win_pct
        grp["draw_pct"] = draw_pct
        grp["loss_pct"] = loss_pct
        grp["ranked"] = ranked
        grp["1st"] = ranked[0]
        grp["2nd"] = ranked[1]
        grp["3rd"] = ranked[2]
    return groups


# ---------------------------------------------------------------------------
# Report: group odds spread
# ---------------------------------------------------------------------------

def print_group_odds(groups: dict) -> None:
    SEP = "=" * 100
    print(SEP)
    print("2026 WORLD CUP — ODDS SPREAD BY GROUP")
    print(SEP)
    print()
    print("Odds format: Home Win / Draw / Away Win (decimal odds)")
    print("Implied % = fair probability after removing bookmaker margin (overround)")
    print()

    for g in sorted(groups):
        grp = groups[g]
        print(f"{SEP}")
        print(f"GROUP {g}")
        print(f"{SEP}")

        for m in grp["matches"]:
            h = implied_prob(m["home_odds"])
            d = implied_prob(m["draw_odds"])
            a = implied_prob(m["away_odds"])
            over = h + d + a - 1.0
            tot = 1 + over
            print(f"  {m['home_team']:30s} vs {m['away_team']:30s}")
            print(f"    Odds: {m['home_odds']:.2f} / {m['draw_odds']:.2f} / {m['away_odds']:.2f}")
            print(f"    Implied: {h/tot*100:5.1f}% / {d/tot*100:5.1f}% / {a/tot*100:5.1f}%  (margin: {over*100:.1f}%)")

        print(f"\n  --- Team Summary (avg per match) ---")
        print(f"  {'Team':30s} {'Avg Win%':>10s} {'Avg Draw%':>10s} {'Avg Loss%':>10s} {'Exp Pts':>10s}")
        print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
        for team in grp["ranked"]:
            w = grp["win_pct"][team] * 100
            d = grp["draw_pct"][team] * 100
            l = grp["loss_pct"][team] * 100
            print(f"  {team:30s} {w:9.1f}% {d:9.1f}% {l:9.1f}% {grp['exp_pts'][team]:9.2f}")
        print()


# ---------------------------------------------------------------------------
# Wild card analysis
# ---------------------------------------------------------------------------

WILD_CARD_SLOTS: dict[str, list[str]] = {
    "74": ["A", "B", "C", "D", "E", "F"],
    "77": ["C", "D", "F", "G", "H"],
    "79": ["C", "E", "F", "H", "I"],
    "80": ["E", "H", "I", "J", "K"],
    "81": ["B", "E", "F", "I", "J"],
    "82": ["A", "E", "H", "I", "J"],
    "85": ["E", "F", "G", "I", "J"],
    "87": ["D", "E", "I", "J", "L"],
}


def print_wildcard_analysis(groups: dict) -> None:
    SEP = "=" * 80
    print(SEP)
    print("WILD CARD QUALIFICATION — 3rd Place Odds by Group")
    print(SEP)
    print()
    print("Likely 3rd-place finisher per group (by expected points):\n")

    # Count paths per group
    group_paths: dict[str, int] = {}
    for slot_groups in WILD_CARD_SLOTS.values():
        for grp in slot_groups:
            group_paths[grp] = group_paths.get(grp, 0) + 1

    data = []
    for g in sorted(groups):
        grp = groups[g]
        third = grp["3rd"]
        pts = grp["exp_pts"][third]
        paths = group_paths.get(g, 0)
        data.append((g, third, pts, paths))

    data.sort(key=lambda x: x[2], reverse=True)

    print(f"  {'Group':8s} {'Likely 3rd':30s} {'Exp Pts':>10s} {'WC Paths':>10s}")
    print(f"  {'-'*8} {'-'*30} {'-'*10} {'-'*10}")
    for g, third, pts, paths in data:
        print(f"  {g:8s} {third:30s} {pts:10.2f} {paths:10d}")

    # Slot breakdown
    print(f"\n{SEP}")
    print("WILD CARD SLOT ANALYSIS")
    print(SEP)
    print()
    print("Each slot's candidate groups, ranked by 3rd-place team strength:\n")

    for slot, grp_list in WILD_CARD_SLOTS.items():
        candidates = [(g, groups[g]["3rd"], groups[g]["exp_pts"][groups[g]["3rd"]]) for g in grp_list]
        candidates.sort(key=lambda x: x[2], reverse=True)
        print(f"  Match {slot} candidates:")
        for g, third, pts in candidates:
            print(f"    Group {g}: {third} ({pts:.2f} exp pts)")
        print()

    # Overall ranking
    print(SEP)
    print("OVERALL WILD CARD PROBABILITY (approximate)")
    print(SEP)
    print()
    print("Ranking all 12 groups' 3rd-place teams by expected points:")
    print("(Higher = more likely to be among the 8 best 3rd-place finishers)\n")

    print(f"  {'Rank':6s} {'Group':8s} {'3rd Place Team':30s} {'Exp Pts':>10s} {'WC Paths':>10s} {'Likelihood':>12s}")
    print(f"  {'-'*6} {'-'*8} {'-'*30} {'-'*10} {'-'*10} {'-'*12}")
    for i, (g, third, pts, paths) in enumerate(data, 1):
        if i <= 4:
            likelihood = "Very High"
        elif i <= 8:
            likelihood = "High"
        elif i <= 10:
            likelihood = "Medium"
        else:
            likelihood = "Low"
        print(f"  {i:6d} {g:8s} {third:30s} {pts:10.2f} {paths:10d} {likelihood:>12s}")

    print()
    print("Key insight: Groups E (Ivory Coast) and I (Senegal) have both strong")
    print("3rd-place teams AND the most wild card paths (6+ each). Groups B, K,")
    print("and L have the weakest 3rd-place teams and fewest paths.")


# ---------------------------------------------------------------------------
# Bracket picks
# ---------------------------------------------------------------------------

def team_strength(team: str, groups: dict) -> float:
    """Return a team's expected points from their group."""
    for g in groups.values():
        if team in g["exp_pts"]:
            return g["exp_pts"][team]
    return 1.0


def pick_winner(t1: str, t2: str, groups: dict) -> str:
    return t1 if team_strength(t1, groups) >= team_strength(t2, groups) else t2


def print_bracket(groups: dict, wild_card_picks: dict[str, str]) -> None:
    """Print the full knockout bracket with picks."""
    SEP = "=" * 70

    # Assign wild cards greedily to slots
    used_groups: set[str] = set()
    slot_winner: dict[str, str] = {}
    for slot, eligible in WILD_CARD_SLOTS.items():
        best_team, best_grp, best_pts = None, None, -1
        for grp in eligible:
            if grp in used_groups:
                continue
            team = wild_card_picks.get(grp)
            if team:
                pts = groups[grp]["exp_pts"][team]
                if pts > best_pts:
                    best_pts, best_team, best_grp = pts, team, grp
        if best_team:
            slot_winner[slot] = best_team
            used_groups.add(best_grp)

    def resolve(pos: str) -> str:
        if pos.startswith("slot"):
            return slot_winner.get(pos[4:], "???")
        group, rank = pos[1], pos[0]
        return groups[group]["1st"] if rank == "1" else groups[group]["2nd"]

    # ---- Round of 32 ----
    ro32 = [
        ("73", "2A", "2B"), ("74", "1E", "slot74"), ("75", "1F", "2C"),
        ("76", "1C", "2F"), ("77", "1I", "slot77"), ("78", "2E", "2I"),
        ("79", "1A", "slot79"), ("80", "1L", "slot80"), ("81", "1D", "slot81"),
        ("82", "1G", "slot82"), ("83", "2K", "2L"), ("84", "1H", "2J"),
        ("85", "1B", "slot85"), ("86", "1J", "2H"), ("87", "1K", "slot87"),
        ("88", "2D", "2G"),
    ]

    print("ROUND OF 32 — PICKS")
    print(SEP)
    r32_winners: dict[str, str] = {}
    for m, t1p, t2p in ro32:
        t1, t2 = resolve(t1p), resolve(t2p)
        w = pick_winner(t1, t2, groups)
        r32_winners[m] = w
        print(f"  Match {m}: {t1:30s} vs {t2:30s} → {w}")
    print()

    # ---- Round of 16 ----
    ro16 = [
        ("89", "74", "77"), ("90", "73", "75"), ("91", "76", "78"),
        ("92", "79", "80"), ("93", "83", "84"), ("94", "81", "82"),
        ("95", "86", "88"), ("96", "85", "87"),
    ]
    print("ROUND OF 16 — PICKS")
    print(SEP)
    r16_winners: dict[str, str] = {}
    for m, w1r, w2r in ro16:
        t1, t2 = r32_winners[w1r], r32_winners[w2r]
        w = pick_winner(t1, t2, groups)
        r16_winners[m] = w
        print(f"  Match {m}: {t1:30s} vs {t2:30s} → {w}")
    print()

    # ---- Quarter Finals ----
    qf = [
        ("97", "89", "90"), ("98", "93", "94"),
        ("99", "91", "92"), ("100", "95", "96"),
    ]
    print("QUARTER FINALS — PICKS")
    print(SEP)
    qf_winners: dict[str, str] = {}
    for m, w1r, w2r in qf:
        t1, t2 = r16_winners[w1r], r16_winners[w2r]
        w = pick_winner(t1, t2, groups)
        qf_winners[m] = w
        print(f"  Match {m}: {t1:30s} vs {t2:30s} → {w}")
    print()

    # ---- Semi Finals ----
    print("SEMI FINALS — PICKS")
    print(SEP)
    sf1_t1, sf1_t2 = qf_winners["97"], qf_winners["98"]
    sf1_w = pick_winner(sf1_t1, sf1_t2, groups)
    sf2_t1, sf2_t2 = qf_winners["99"], qf_winners["100"]
    sf2_w = pick_winner(sf1_t1, sf1_t2, groups) if False else pick_winner(sf2_t1, sf2_t2, groups)
    print(f"  Match 101: {sf1_t1:30s} vs {sf1_t2:30s} → {sf1_w}")
    print(f"  Match 102: {sf2_t1:30s} vs {sf2_t2:30s} → {sf2_w}")
    print()

    # ---- Final ----
    print("FINAL — PICK")
    print(SEP)
    champion = pick_winner(sf1_w, sf2_w, groups)
    print(f"  Match 104: {sf1_w:30s} vs {sf2_w:30s} → {champion}")
    print(f"\n  🏆 CHAMPION: {champion}\n")


# ---------------------------------------------------------------------------
# Bracket structure (for reference)
# ---------------------------------------------------------------------------

def print_bracket_structure() -> None:
    print("=" * 80)
    print("2026 WORLD CUP — KNOCKOUT BRACKET STRUCTURE")
    print("=" * 80)
    print()
    print("12 Groups (A–L): 48 teams")
    print("  • 24 automatic qualifiers (1st + 2nd from each group)")
    print("  • 8 wild card spots (best 3rd-place finishers)")
    print()

    ro32_info = [
        ("73", "2A", "2B", "Jun 28 19:00Z"), ("74", "1E", "3ABCDF", "Jun 29 20:30Z"),
        ("75", "1F", "2C", "Jun 30 01:00Z"), ("76", "1C", "2F", "Jun 29 17:00Z"),
        ("77", "1I", "3CDFGH", "Jun 30 21:00Z"), ("78", "2E", "2I", "Jun 30 17:00Z"),
        ("79", "1A", "3CEFHI", "Jul 01 01:00Z"), ("80", "1L", "3EHIJK", "Jul 01 16:00Z"),
        ("81", "1D", "3BEFIJ", "Jul 02 00:00Z"), ("82", "1G", "3AEHIJ", "Jul 01 20:00Z"),
        ("83", "2K", "2L", "Jul 02 23:00Z"), ("84", "1H", "2J", "Jul 02 19:00Z"),
        ("85", "1B", "3EFGIJ", "Jul 03 03:00Z"), ("86", "1J", "2H", "Jul 03 22:00Z"),
        ("87", "1K", "3DEIJL", "Jul 04 01:30Z"), ("88", "2D", "2G", "Jul 03 18:00Z"),
    ]
    print("ROUND OF 32")
    print("-" * 80)
    for m, t1, t2, dt in ro32_info:
        print(f"  Match {m:>3s}: {t1:10s} vs {t2:10s}  —  {dt}")

    ro16_info = [
        ("89", "W74", "W77", "Jul 04 21:00Z"), ("90", "W73", "W75", "Jul 04 17:00Z"),
        ("91", "W76", "W78", "Jul 05 20:00Z"), ("92", "W79", "W80", "Jul 06 00:00Z"),
        ("93", "W83", "W84", "Jul 06 19:00Z"), ("94", "W81", "W82", "Jul 07 00:00Z"),
        ("95", "W86", "W88", "Jul 07 16:00Z"), ("96", "W85", "W87", "Jul 07 20:00Z"),
    ]
    print("\nROUND OF 16")
    print("-" * 80)
    for m, t1, t2, dt in ro16_info:
        print(f"  Match {m:>3s}: {t1:6s} vs {t2:6s}  —  {dt}")

    qf_info = [
        ("97", "W89", "W90", "Jul 09 20:00Z"), ("98", "W93", "W94", "Jul 10 19:00Z"),
        ("99", "W91", "W92", "Jul 11 21:00Z"), ("100", "W95", "W96", "Jul 12 01:00Z"),
    ]
    print("\nQUARTER FINALS")
    print("-" * 80)
    for m, t1, t2, dt in qf_info:
        print(f"  Match {m:>3s}: {t1:6s} vs {t2:6s}  —  {dt}")

    print("\nSEMI FINALS")
    print("-" * 80)
    print("  Match 101: W97  vs W98   —  Jul 14 19:00Z")
    print("  Match 102: W99  vs W100  —  Jul 15 19:00Z")
    print("\nTHIRD PLACE")
    print("-" * 80)
    print("  Match 103: RU101 vs RU102  —  Jul 18 21:00Z")
    print("\nFINAL")
    print("-" * 80)
    print("  Match 104: W101 vs W102  —  Jul 19 19:00Z")

    print(f"\n{'='*80}")
    print("WILD CARD PATHS (3rd-Place Qualification)")
    print("=" * 80)
    print()
    print("The 8 best 3rd-place teams across 12 groups advance to Round of 32.")
    print("They are slotted into specific positions based on which groups they come from:\n")
    for slot, grp_list in WILD_CARD_SLOTS.items():
        groups_str = ", ".join(f"Group {g}" for g in grp_list)
        print(f"  Match {slot}: {groups_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    content = load_ics()
    content = unfold(content)
    events = parse_events(content)
    groups = build_groups(events)
    groups = compute_standings(groups)

    # --- Section 1: Group odds spread ---
    print_group_odds(groups)

    # --- Section 2: Bracket structure ---
    print()
    print_bracket_structure()
    print()

    # --- Section 3: Wild card analysis ---
    print()
    print_wildcard_analysis(groups)
    print()

    # --- Section 4: Bracket picks ---
    # My wild card picks: 8 of 12 third-place teams
    wild_card_picks: dict[str, str] = {
        "A": "Czech Republic",
        "B": "Bosnia and Herzegovina",
        "C": "Scotland",
        "D": "Paraguay",
        "E": "Ivory Coast",
        "F": "Sweden",
        "I": "Senegal",
        "J": "Algeria",
    }

    print("=" * 70)
    print("BRACKET PICKS")
    print("=" * 70)
    print()
    print("Wild card selections:")
    for grp, team in sorted(wild_card_picks.items()):
        print(f"  Group {grp}: {team}")
    print()

    print_bracket(groups, wild_card_picks)


if __name__ == "__main__":
    main()
