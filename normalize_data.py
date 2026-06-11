#!/usr/bin/env python3
"""
Normalize all raw World Cup 2026 odds data into a common schema.

Normalized schema (one row per source per match):
  - source          : data source name
  - match_id        : canonical match identifier
  - home_team       : normalized home team name
  - away_team       : normalized away team name
  - group           : group letter (A-L) if group stage
  - date            : match date (ISO 8601)
  - home_win_prob   : implied probability of home win (0-1)
  - draw_prob       : implied probability of draw (0-1)
  - away_win_prob   : implied probability of away win (0-1)
  - home_win_odds   : decimal odds for home win
  - draw_odds       : decimal odds for draw
  - away_win_odds   : decimal odds for away win
  - extra           : JSON blob for source-specific fields
"""

import csv
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

RAW = Path("_data/raw")
NORM = Path("_data/norm")
NORM.mkdir(parents=True, exist_ok=True)

rows = []
stats = {"sources": {}, "errors": []}


def add_row(**kwargs):
    fieldnames = [
        "source", "match_id", "home_team", "away_team", "group", "date",
        "home_win_prob", "draw_prob", "away_win_prob",
        "home_win_odds", "draw_odds", "away_win_odds",
        "extra",
    ]
    row = {k: kwargs.get(k, None) for k in fieldnames}
    if row["extra"] and not isinstance(row["extra"], str):
        row["extra"] = json.dumps(row["extra"])
    rows.append(row)


def log(source, count):
    stats["sources"][source] = count
    print(f"  {source}: {count} rows")


TEAM_ALIASES = {
    "czech republic": "Czech Republic", "czechia": "Czech Republic",
    "south korea": "South Korea", "korea republic": "South Korea",
    "bosnia-herzegovina": "Bosnia and Herzegovina",
    "bosnia herzegovina": "Bosnia and Herzegovina",
    "united states": "USA", "usa": "USA",
    "turkiye": "Turkey", "türkiye": "Turkey",
    "ivory coast": "Ivory Coast", "côte d'ivoire": "Ivory Coast",
    "cape verde": "Cape Verde", "cabo verde": "Cape Verde",
    "d-r congo": "DR Congo", "dr congo": "DR Congo",
    "d.r. congo": "DR Congo", "congo dr": "DR Congo",
    "saudi arabia": "Saudi Arabia", "new zealand": "New Zealand",
    "uzbekistan": "Uzbekistan", "jordan": "Jordan",
    "algeria": "Algeria", "senegal": "Senegal", "norway": "Norway",
    "iran": "Iran", "haiti": "Haiti",
    "curacao": "Curaçao", "curaçao": "Curaçao",
    "tunisia": "Tunisia", "panama": "Panama", "ghana": "Ghana",
    "morocco": "Morocco", "egypt": "Egypt", "ecuador": "Ecuador",
    "paraguay": "Paraguay", "uruguay": "Uruguay", "colombia": "Colombia",
    "japan": "Japan", "sweden": "Sweden", "netherlands": "Netherlands",
    "germany": "Germany", "belgium": "Belgium", "spain": "Spain",
    "france": "France", "england": "England", "portugal": "Portugal",
    "argentina": "Argentina", "brazil": "Brazil", "mexico": "Mexico",
    "canada": "Canada", "switzerland": "Switzerland", "austria": "Austria",
    "croatia": "Croatia", "scotland": "Scotland",
    "south africa": "South Africa", "qatar": "Qatar", "iraq": "Iraq",
}


def normalize_team(name):
    if not name:
        return name
    name = name.strip()
    key = name.lower()
    return TEAM_ALIASES.get(key, name)


def make_match_id(home, away):
    h = normalize_team(home).lower().replace(" ", "_")
    a = normalize_team(away).lower().replace(" ", "_")
    return f"{h}_vs_{a}"


def probs_from_odds(home_odds, draw_odds, away_odds):
    """Convert decimal odds to normalized implied probabilities."""
    try:
        hp = 1.0 / float(home_odds)
        dp = 1.0 / float(draw_odds)
        ap = 1.0 / float(away_odds)
        overround = hp + dp + ap
        if overround <= 0:
            return None, None, None
        return round(hp / overround, 6), round(dp / overround, 6), round(ap / overround, 6)
    except (ValueError, TypeError, ZeroDivisionError):
        return None, None, None


# ===================================================================
# 1. BetExplorer (from ICS calendar)
# ===================================================================
def parse_betexplorer():
    print("\n--- Parsing BetExplorer (ICS) ---")
    ics_path = RAW / "betexplorer" / "world-cup-calendar.ics"
    if not ics_path.exists():
        print("  [SKIP] ICS not found"); return

    content = re.sub(r"\r?\n ", "", ics_path.read_text())
    events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, re.DOTALL)
    count = 0
    for event in events:
        desc_m = re.search(r"DESCRIPTION:(.*?)(?:\r?\n[A-Z-]+:|$)", event, re.DOTALL)
        if not desc_m:
            continue
        text = desc_m.group(1)
        odds_m = re.search(r"Average odds:\s*([\d.]+)/([\d.]+)/([\d.]+)", text)
        if not odds_m:
            continue
        home_odds, draw_odds, away_odds = float(odds_m.group(1)), float(odds_m.group(2)), float(odds_m.group(3))

        # Extract teams from SUMMARY
        home_team = away_team = None
        summary = re.search(r"SUMMARY:(.*?)(?:\r?\n|$)", event)
        if summary:
            st = summary.group(1).strip()
            for sep in [" vs ", " - ", " v "]:
                if sep in st:
                    parts = st.split(sep, 1)
                    if len(parts) == 2:
                        home_team, away_team = parts[0].strip(), parts[1].strip()
                        break
        if not home_team:
            continue

        dtstart = re.search(r"DTSTART[^:]*:(\d{8})", event)
        date_str = f"{dtstart.group(1)[:4]}-{dtstart.group(1)[4:6]}-{dtstart.group(1)[6:8]}" if dtstart else ""
        group_m = re.search(r"Group ([A-L])", text)
        group = group_m.group(1) if group_m else ""

        hp, dp, ap = probs_from_odds(home_odds, draw_odds, away_odds)
        home_team = normalize_team(home_team)
        away_team = normalize_team(away_team)
        add_row(
            source="betexplorer", match_id=make_match_id(home_team, away_team),
            home_team=home_team, away_team=away_team, group=group, date=date_str,
            home_win_prob=hp, draw_prob=dp, away_win_prob=ap,
            home_win_odds=home_odds, draw_odds=draw_odds, away_win_odds=away_odds,
        )
        count += 1
    log("betexplorer", count)


# ===================================================================
# 2. uanalyse
# ===================================================================
def parse_uanalyse():
    print("\n--- Parsing uanalyse ---")
    csv_path = RAW / "uanalyse" / "latest" / "match_predictions.csv"
    if not csv_path.exists():
        print("  [SKIP] not found"); return
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            home = normalize_team(row.get("home_team", ""))
            away = normalize_team(row.get("away_team", ""))
            if not home or not away:
                continue
            stage = row.get("stage", "")
            group = ""
            g = re.search(r"Group ([A-L])", stage)
            if g:
                group = g.group(1)
            add_row(
                source="uanalyse", match_id=make_match_id(home, away),
                home_team=home, away_team=away, group=group,
                date=row.get("kickoff_date", ""),
                home_win_prob=round(float(row.get("prob_home_win", 0) or 0), 6),
                draw_prob=round(float(row.get("prob_draw", 0) or 0), 6),
                away_win_prob=round(float(row.get("prob_away_win", 0) or 0), 6),
                extra={"snapshot_date": row.get("snapshot_date", ""),
                       "stage": stage,
                       "exp_home_goals": row.get("exp_home_goals"),
                       "exp_away_goals": row.get("exp_away_goals")},
            )
            count += 1
    log("uanalyse", count)


# ===================================================================
# 3. worldcup-predictor
# ===================================================================
def parse_worldcup_predictor():
    print("\n--- Parsing worldcup-predictor ---")
    csv_path = RAW / "worldcup-predictor" / "wc2026_predictions.csv"
    if not csv_path.exists():
        print("  [SKIP] not found"); return
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            home = normalize_team(row.get("home_team", ""))
            away = normalize_team(row.get("away_team", ""))
            if not home or not away:
                continue
            add_row(
                source="worldcup-predictor", match_id=make_match_id(home, away),
                home_team=home, away_team=away,
                date=row.get("date", ""),
                home_win_prob=round(float(row.get("p_home", 0) or 0), 6),
                draw_prob=round(float(row.get("p_draw", 0) or 0), 6),
                away_win_prob=round(float(row.get("p_away", 0) or 0), 6),
                extra={"elo_home": row.get("elo_home"), "elo_away": row.get("elo_away"),
                       "neutral": row.get("neutral"), "city": row.get("city", ""),
                       "pick": row.get("pick", "")},
            )
            count += 1
    log("worldcup-predictor", count)


# ===================================================================
# 4. Polymarket — Gamma API events
# ===================================================================
def parse_polymarket():
    print("\n--- Parsing Polymarket ---")
    json_path = RAW / "polymarket" / "events_worldcup.json"
    if not json_path.exists():
        print("  [SKIP] not found"); return

    with open(json_path) as f:
        events = json.load(f)

    # Also load match-level events if available
    match_path = RAW / "polymarket" / "gamma-events-matchlevel.json"
    if match_path.exists():
        with open(match_path) as f:
            events += json.load(f)

    count = 0
    seen_match_keys = set()
    for event in events:
        title = event.get("title", "")
        slug = (event.get("slug") or "").lower()
        etitle = title.lower()

        # Only FIFA World Cup sports events (not politics, esports, etc.)
        tags = event.get("tags", [])
        tag_labels = [t.get("label", "").lower() if isinstance(t, dict) else str(t).lower() for t in tags]
        is_fifa = any("fifa" in t or ("world cup" in t and "soccer" in tag_labels) for t in tag_labels)
        if not is_fifa and "fifwc" not in slug:
            continue

        # Skip tournament-level futures
        if any(x in etitle for x in ["winner", "champion", "group winner", "top scorer",
                                       "fed decision", "iran", "peru", "elon", "counter-strike",
                                       "cs2-", "stuttgart", "atp-", "bo3", "tweets"]):
            continue

        markets = event.get("markets", [])
        for market in markets:
            question = market.get("question", "")
            qlower = question.lower()
            outcomes = market.get("outcomes", [])
            prices_raw = market.get("outcomePrices", [])
            if not outcomes or not prices_raw:
                continue

            prices = []
            for p in prices_raw:
                try:
                    prices.append(float(p))
                except (ValueError, TypeError):
                    prices.append(None)

            home_team = away_team = None

            # Pattern: "Will {team} win on {date}?" — match moneyline
            win_m = re.match(r"Will (.+?) win on (\d{4}-\d{2}-\d{2})\?", question)
            if win_m and len(outcomes) == 2 and len(prices) == 2:
                team = win_m.group(1).strip()
                date_str = win_m.group(2)
                # This is a single-team market (yes/no), skip — we need head-to-head
                continue

            # Pattern: vs markets with spreads or match winner
            for sep in [" vs ", " - ", " @ "]:
                if sep in title:
                    parts = title.split(sep, 1)
                    if len(parts) == 2:
                        home_team = parts[0].strip().title()
                        away_team = parts[1].strip().title()
                        # Clean up suffixes like " - More Markets"
                        for suffix in [" - More Markets", " - Live", " - Pre-Match"]:
                            home_team = home_team.split(suffix)[0].strip()
                            away_team = away_team.split(suffix)[0].strip()
                        break

            if not home_team:
                continue

            # Spread markets: outcomes are team names
            if len(outcomes) == 2 and all(o in [home_team.title(), away_team.title()] for o in outcomes):
                home_team = normalize_team(home_team)
                away_team = normalize_team(away_team)
                match_id = make_match_id(home_team, away_team)
                key = (match_id, market.get("slug", ""))

                map_home = home_team.title() in outcomes[0]
                home_prob = prices[0] if map_home else prices[1]
                away_prob = prices[1] if map_home else prices[0]

                if key not in seen_match_keys and home_prob is not None and away_prob is not None:
                    seen_match_keys.add(key)
                    add_row(
                        source="polymarket", match_id=match_id,
                        home_team=home_team, away_team=away_team,
                        date=event.get("startDate", "")[:10] if event.get("startDate") else "",
                        home_win_prob=round(home_prob, 6),
                        away_win_prob=round(away_prob, 6),
                        extra={"question": question, "market_slug": market.get("slug", ""),
                               "market_type": "spread", "outcomes": outcomes},
                    )
                    count += 1

            # 3-outcome markets: home/draw/away
            elif len(outcomes) == 3 and len(prices) >= 3:
                home_team = normalize_team(home_team)
                away_team = normalize_team(away_team)
                add_row(
                    source="polymarket", match_id=make_match_id(home_team, away_team),
                    home_team=home_team, away_team=away_team,
                    date=event.get("startDate", "")[:10] if event.get("startDate") else "",
                    home_win_prob=round(prices[0], 6) if prices[0] is not None else None,
                    draw_prob=round(prices[1], 6) if prices[1] is not None else None,
                    away_win_prob=round(prices[2], 6) if prices[2] is not None else None,
                    extra={"question": question, "outcomes": outcomes},
                )
                count += 1

    log("polymarket", count)


# ===================================================================
# 5. openfootball (fixtures only)
# ===================================================================
def parse_openfootball():
    print("\n--- Parsing openfootball ---")
    json_path = RAW / "openfootball" / "worldcup-2026.json"
    if not json_path.exists():
        print("  [SKIP] not found"); return
    with open(json_path) as f:
        data = json.load(f)
    count = 0
    for match in data.get("matches", []):
        home = normalize_team(match.get("team1", ""))
        away = normalize_team(match.get("team2", ""))
        if not home or not away:
            continue
        group = match.get("group", "")
        if group.startswith("Group "):
            group = group.replace("Group ", "")
        add_row(
            source="openfootball", match_id=make_match_id(home, away),
            home_team=home, away_team=away, group=group,
            date=match.get("date", ""),
            extra={"round": match.get("round", ""), "time": match.get("time", ""),
                   "ground": match.get("ground", "")},
        )
        count += 1
    log("openfootball", count)


# ===================================================================
# 6. FiveThirtyEight (2014 historical — tournament-level)
# ===================================================================
def parse_fivethirtyeight():
    print("\n--- Parsing FiveThirtyEight ---")
    csv_path = RAW / "fivethirtyeight" / "wc-2014-final-predictions.csv"
    if not csv_path.exists():
        print("  [SKIP] not found"); return
    # This file has tournament-level predictions (not match-level)
    # Save as-is for methodology reference, but don't normalize to match rows
    print("  [INFO] Tournament-level data only — skipping match normalization")
    log("fivethirtyeight-2014", 0)


# ===================================================================
# 7. OddsHarvester (OddsPortal scrape)
# ===================================================================
def parse_oddsharvester():
    print("\n--- Parsing OddsHarvester ---")
    csv_path = RAW / "oddsharvester" / "worldcup-2026-odds.csv"
    json_path = RAW / "oddsharvester" / "worldcup-2026-odds.json"

    if csv_path.exists():
        _parse_oh_csv(csv_path)
    elif json_path.exists():
        _parse_oh_json(json_path)
    else:
        print("  [SKIP] No OddsHarvester output found")


def _parse_oh_csv(path):
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            home = normalize_team(row.get("home_team", ""))
            away = normalize_team(row.get("away_team", ""))
            if not home or not away:
                continue
            date_str = row.get("match_date", "")[:10]
            market_str = row.get("1x2_market", "")
            bookmakers = []
            try:
                bookmakers = json.loads(market_str.replace("'", '"'))
            except (json.JSONDecodeError, AttributeError):
                pass

            # Compute average odds across bookmakers
            h_odds, d_odds, a_odds = [], [], []
            for b in bookmakers:
                try:
                    h_odds.append(float(b.get("1", 0)))
                    d_odds.append(float(b.get("X", 0)))
                    a_odds.append(float(b.get("2", 0)))
                except (ValueError, TypeError):
                    pass

            avg_h = round(sum(h_odds) / len(h_odds), 2) if h_odds else None
            avg_d = round(sum(d_odds) / len(d_odds), 2) if d_odds else None
            avg_a = round(sum(a_odds) / len(a_odds), 2) if a_odds else None
            hp, dp, ap = probs_from_odds(avg_h, avg_d, avg_a) if (avg_h and avg_d and avg_a) else (None, None, None)

            add_row(
                source="oddsharvester", match_id=make_match_id(home, away),
                home_team=home, away_team=away, date=date_str,
                home_win_prob=hp, draw_prob=dp, away_win_prob=ap,
                home_win_odds=avg_h, draw_odds=avg_d, away_win_odds=avg_a,
                extra={"num_bookmakers": len(bookmakers),
                       "bookmaker_names": [b.get("bookmaker_name", "") for b in bookmakers],
                       "url": row.get("match_link", ""),
                       "venue": row.get("venue", "")},
            )
            count += 1
    log("oddsharvester", count)


def _parse_oh_json(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("matches", data.get("data", [data]))
    count = 0
    for match in data:
        home = normalize_team(match.get("home_team", ""))
        away = normalize_team(match.get("away_team", ""))
        if not home or not away:
            continue
        date_str = str(match.get("match_date", ""))[:10]
        market_str = match.get("1x2_market", "")
        bookmakers = []
        try:
            bookmakers = json.loads(market_str.replace("'", '"')) if isinstance(market_str, str) else market_str
        except (json.JSONDecodeError, AttributeError):
            pass
        h_odds, d_odds, a_odds = [], [], []
        for b in bookmakers:
            try:
                h_odds.append(float(b.get("1", 0)))
                d_odds.append(float(b.get("X", 0)))
                a_odds.append(float(b.get("2", 0)))
            except (ValueError, TypeError):
                pass
        avg_h = round(sum(h_odds) / len(h_odds), 2) if h_odds else None
        avg_d = round(sum(d_odds) / len(d_odds), 2) if d_odds else None
        avg_a = round(sum(a_odds) / len(a_odds), 2) if a_odds else None
        hp, dp, ap = probs_from_odds(avg_h, avg_d, avg_a) if (avg_h and avg_d and avg_a) else (None, None, None)
        add_row(
            source="oddsharvester", match_id=make_match_id(home, away),
            home_team=home, away_team=away, date=date_str,
            home_win_prob=hp, draw_prob=dp, away_win_prob=ap,
            home_win_odds=avg_h, draw_odds=avg_d, away_win_odds=avg_a,
            extra={"num_bookmakers": len(bookmakers),
                   "bookmaker_names": [b.get("bookmaker_name", "") for b in bookmakers]},
        )
        count += 1
    log("oddsharvester", count)


# ===================================================================
# Write output
# ===================================================================
def write_output():
    print("\n--- Writing normalized output ---")
    output_path = NORM / "all_odds_normalized.csv"
    fieldnames = [
        "source", "match_id", "home_team", "away_team", "group", "date",
        "home_win_prob", "draw_prob", "away_win_prob",
        "home_win_odds", "draw_odds", "away_win_odds", "extra",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Written {len(rows)} rows to {output_path}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_rows": len(rows),
        "sources": stats["sources"],
        "unique_matches": len(set(r["match_id"] for r in rows)),
    }
    (NORM / "normalization_report.json").write_text(json.dumps(report, indent=2))
    print(f"\n{'='*50}")
    print(f"Normalization complete")
    print(f"  Total rows:     {len(rows)}")
    print(f"  Unique matches: {report['unique_matches']}")
    for src, cnt in stats["sources"].items():
        print(f"    {src}: {cnt} rows")


def main():
    print("=" * 60)
    print("World Cup 2026 — Data Normalizer")
    print("=" * 60)
    parse_betexplorer()
    parse_uanalyse()
    parse_worldcup_predictor()
    parse_polymarket()
    parse_openfootball()
    parse_fivethirtyeight()
    parse_oddsharvester()
    write_output()


if __name__ == "__main__":
    main()
