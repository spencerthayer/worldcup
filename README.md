# 2026 World Cup — Odds & Bracket Analysis

Analysis of the 2026 FIFA World Cup based on average BetExplorer odds from the
[kubeia.io calendar](https://calendar.kubeia.io/world-cup-with-alarm-with-score-tv-united-states-of-america-the.ics).

## What's here

| File | Description |
|---|---|
| `parse_calendar.py` | Main script — downloads the ICS calendar, parses all matches, computes odds spreads, wild card analysis, and full bracket picks |
| `world-cup-calendar.ics` | Cached copy of the ICS calendar (auto-downloaded on first run) |

## Quick start

```bash
python3 parse_calendar.py
```

The script will:

1. Download the ICS calendar (if not already cached)
2. Print the **odds spread for all 12 groups** (implied win/draw/loss probabilities)
3. Print the **full knockout bracket structure** with dates
4. Print the **wild card analysis** (which 3rd-place teams are most likely to qualify)
5. Print the **full bracket picks** from Round of 32 through the Final

## Methodology

### Odds parsing

- Average BetExplorer decimal odds (Home Win / Draw / Away Win) are extracted from each match's ICS description.
- **Implied probability** = `1 / decimal_odds`
- **Overround** (bookmaker margin) is removed to get fair probabilities:
  `fair_prob = implied_prob / (1 + overround)`
- **Expected points** per match = `win_prob * 3 + draw_prob * 1`

### Group standings

Teams are ranked by expected points across their 3 group matches. This gives projected 1st, 2nd, and 3rd place per group.

### Wild card qualification

- 12 groups, 8 wild card slots for 3rd-place teams
- Each slot draws from a specific subset of groups (FIFA bracket rules)
- Groups are ranked by their projected 3rd-place team's expected points
- Wild card slots are assigned greedily: strongest available 3rd-place team to first eligible slot

### Bracket picks

- Every knockout match is decided by comparing the two teams' expected points from group stage
- Higher expected points = pick to win
- Wild card teams are assigned to slots before bracket simulation begins

## Key findings

### Group favorites

| Group | 1st | 2nd | 3rd |
|---|---|---|---|
| A | Mexico | South Korea | Czech Republic |
| B | Switzerland | Canada | Bosnia and Herzegovina |
| C | Brazil | Morocco | Scotland |
| D | USA | Turkey | Paraguay |
| E | Germany | Ecuador | Ivory Coast |
| F | Netherlands | Japan | Sweden |
| G | Belgium | Egypt | Iran |
| H | Spain | Uruguay | Cape Verde |
| I | France | Norway | Senegal |
| J | Argentina | Austria | Algeria |
| K | Portugal | Colombia | DR Congo |
| L | England | Croatia | Ghana |

### Wild card picks (8 of 12)

| Group | 3rd Place Team | Exp Pts | WC Paths |
|---|---|---|---|
| E | Ivory Coast | 1.45 | 7 |
| I | Senegal | 1.32 | 6 |
| A | Czech Republic | 1.31 | 2 |
| B | Bosnia and Herzegovina | 1.24 | 2 |
| J | Algeria | 1.23 | 5 |
| C | Scotland | 1.23 | 3 |
| D | Paraguay | 1.23 | 3 |
| F | Sweden | 1.22 | 5 |

### Bracket result

**Champion: Spain**

Path: Austria → Colombia → Belgium → Germany → Brazil (Final)

## Customization

To change wild card picks, edit the `wild_card_picks` dict in `main()`:

```python
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
```

To change bracket picks, modify the `pick_winner()` function or override individual match results in `print_bracket()`.

## Odds data sources

The analysis currently uses one source (average BetExplorer 1X2 odds from the ICS calendar).
Below are additional **open / free / publicly accessible** sources for World Cup match odds
you can integrate to improve coverage, cross-reference bookmakers, or build a consensus model.

### Free APIs (no cost, no/low auth)

| Source | Type | Coverage | Notes |
|---|---|---|---|
| [BetExplorer](https://www.betexplorer.com/) | Web scrape / ICS embed | 1X2 odds from 30+ bookmakers averaged per match | The current source. Odds are embedded in the kubeia.io ICS calendar. Also available as a web scraper via OddsHarvester or direct page scrape. |
| [BALLDONTLIE FIFA API](https://fifa.balldontlie.io/) | REST API (JSON) | 2018, 2022, 2026 tournaments | Free API key; includes moneyline, spread, total odds from FanDuel, DraftKings, etc. Cursor-based pagination. |
| [The Odds API](https://the-odds-api.com/) | REST API (JSON) | ~40 bookmakers (Bet365, DraftKings, FanDuel, William Hill…) | 500 free credits/mo. Covers 1X2, spreads, totals. No Pinnacle / Betfair. SDKs on GitHub under Apache-2.0. |
| [OddsPapi](https://oddspapi.io/) | REST API (JSON) | 350+ bookmakers (incl. Pinnacle, Singbet, Betfair Exchange) | 250 free requests/mo. Each request returns all bookmakers. Historical odds included. |
| [football-data.org](https://www.football-data.org/) | REST API (JSON) | FIFA World Cup included | Free tier: 10 calls/min. Good for fixtures + basic odds prototyping. |
| [Polymarket Gamma API](https://docs.polymarket.com/market-data/overview) | REST API (JSON) | Prediction-market odds for every match, group, knockout round, tournament winner | No auth, no key, no wallet required. Real-time probabilities from the largest prediction market. |
| [Betfair Exchange API](https://developer.betfair.com/) | REST API (JSON) | Full exchange odds (back/lay) for World Cup matches | Free with active Betfair account (Delayed App Key). Live key £499 one-off. Best for true market-implied probabilities. |
| [worldcup2026](https://github.com/rezarahiminia/worldcup2026) | Self-hosted REST API (Docker) | Teams, groups, matches, stadiums, standings | Open-source, no API key. Demo at `worldcup26.ir`. Can be self-hosted. |

### Open datasets & GitHub repos

| Source | Format | What's included |
|---|---|---|
| [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) | JSON | Full 2026 match schedule (fixtures, dates, times, venues, groups). Public domain, no key. Raw: `raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json` |
| [openfootball/worldcup](https://github.com/openfootball/worldcup) | Football.TXT | Historical + 2026 World Cup data in plain-text format. |
| [FiveThirtyEight /data/world-cup-predictions](https://github.com/fivethirtyeight/data/tree/master/world-cup-predictions) | CSV | Historical World Cup predictions with SPI-based win probabilities. Methodology for knockout-round projection. |
| [uanalyse/world-cup-2026-predictions](https://github.com/uanalyse/world-cup-2026-predictions) | JSON/CSV | Daily timestamped 2026 forecasts, published pre-kickoff, append-only. |
| [hjjbh1314/worldcup-predictor](https://github.com/hjjbh1314/worldcup-predictor) | Python + data | Elo-based W/D/L predictor with optional free odds overlay. 60% backtest accuracy. |
| [Hicruben/world-cup-2026-prediction-model](https://github.com/Hicruben/world-cup-2026-prediction-model) | Python | Open-source Elo + Dixon-Coles + Monte Carlo model for 2026. |

### Scrapers & tools (build your own odds collector)

| Source | Language | Target |
|---|---|---|
| [OddsHarvester](https://github.com/jordantete/OddsHarvester) | Python (Playwright) | Scrapes OddsPortal — 10 sports, 100+ leagues, dozens of markets. Outputs JSON/CSV/S3. |
| [Sports-Betting-Data-Scraping](https://github.com/morrisndurere/Sports-Betting-Data-Scraping) | Python | OddsPortal scraper focused on football odds → CSV. |
| [betScrapeR](https://github.com/dashee87/betScrapeR) | R | Combines Betfair API exchange data with scraped bookmaker odds. |
| [Apify Polymarket Scraper](https://apify.com/louisdeconinck/polymarket-events-scraper/api) | No-code / API | Scrapes Polymarket prediction markets → CSV/JSON. No API key. |

### Prediction-market dashboards (manual export)

| Source | Notes |
|---|---|
| [Polymarket World Cup](https://polymarket.com/sports/world-cup/props) | Real-time match & futures odds. Use the free Gamma API above for programmatic access. |
| [FIFA VOdds / polyanalytics.co](https://fifavodds.com/) | Aggregates Polymarket + Kalshi + sportsbooks. CSV export from dashboard. |
| [Nate Silver's PELE model](https://www.natesilver.net/p/world-cup-2026-odds-predictions) | 100K simulations for all 48 teams & 104 matches. Published odds tables. |

### Historical odds archives

| Source | Coverage |
|---|---|
| [Covers Sports odds history](https://www.covers.com/world-cup/odds) | Pre-tournament outright odds from 2002 onward (decimal). |
| [OddsPortal archives](https://www.oddsportal.com/football/world/world-championship-2026/) | Pre-match 1X2 odds comparison across bookmakers (web UI; scrape with tools above). |

**Recommendation for multi-source consensus:** Combine BALLDONTLIE (structured US bookmaker odds) + Polymarket Gamma API (prediction-market probabilities) + Betfair Exchange API (true market odds with overround near 0) for the broadest free coverage. Add OddsPapi if you need 350+ bookmakers in a single call.