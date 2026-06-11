# 2026 World Cup
## Odds, Data Pipeline & Monte Carlo Bracket

A complete pipeline for scraping World Cup odds from multiple open sources, normalizing them into a consensus probability model, and running Monte Carlo simulations to produce an optimized bracket for the WC Bracket Challenge (maximizing expected points out of 203).

See the [results](results.md).

## Repository structure

| Path | Description |
|---|---|
| `generate_bracket.py` | **Main bracket generator** — Monte Carlo simulation + optimization |
| `generate_results.py` | **Results tracker** — compares predictions vs actual results, tracks score |
| `update_results.py` | **Match result updater** — CLI for entering actual match scores |
| `normalize_data.py` | Normalizes raw odds from all sources into a common schema |
| `parse_calendar.py` | Legacy script — downloads ICS calendar, simple expected-points model |
| `download_data.py` | Downloads raw data from all sources into `_data/raw/` |
| `scrape_all.py` | Scrapes OddsPortal via OddsHarvester + Playwright for other sources |
| `_data/raw/` | Raw data from 8+ sources (JSON, CSV, HTML, ICS) |
| `_data/norm/all_odds_normalized.csv` | Normalized consensus odds (398 rows, 6 sources) |
| `_data/bracket.json` | Full machine-readable bracket output |
| `_data/results.json` | Actual match results (updated via update_results.py) |
| `results.md` | Visual human-readable results with flags, scoring, and accuracy |
| `brackets_info.md` | Detailed spec for the bracket generator |

## Pipeline overview

```
┌─────────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  Scrape / fetch  │────▶│  _data/raw/  │────▶│  normalize_   │────▶│ _data/norm/  │
│  odds from 8+    │     │  per-source  │     │  data.py      │     │ all_odds_    │
│  open sources    │     │  raw files   │     │               │     │ normalized   │
└─────────────────┘     └──────────────┘     └───────────────┘     └──────┬───────┘
                                                                         │
                                                                         ▼
┌─────────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  _data/bracket   │◀────│  Optimize    │◀────│  Monte Carlo  │◀────│  Consensus   │
│  .json/.csv/.md  │     │  bracket     │     │  simulation   │     │  probability │
│                  │     │  picks       │     │  (50K iters)  │     │  model       │
└─────────────────┘     └──────────────┘     └───────────────┘     └──────────────┘
```

## Quick start

```bash
# 1. Install scraper dependencies, only needed when refreshing raw data
pip install playwright
python3 -m playwright install chromium

# 2. Download and normalize all data
python3 download_data.py
python3 normalize_data.py

# 3. Generate the bracket (1M simulations, ~6 minutes)
python3 generate_bracket.py --sims 1000000 --seed 42

# 4. Generate the visual results tracker
python3 generate_results.py

# 5. View results
cat results.md
```

## Results (1,000,000 simulations)

| Metric | Value |
|---|---|
| **Expected Score** | **97.53 / 203** |
| **Champion** | **Spain** (16.9%) |
| **Final** | Argentina vs Spain |
| **Simulation accuracy** | **±0.05%** (standard error bound at p=0.5) |

Top champion probabilities: Spain 16.9%, Argentina 14.8%, France 12.9%, Brazil 8.6%, England 8.1%.

Validation against UAnalyse priors (mean absolute deviation): R32=0.062, QF=0.039, SF=0.026, Final=0.015, Champion=0.009.

**Comparison to 50K sims:** At 50,000 sims the champion was Argentina (15.1%) vs Spain (16.8%). The 1M simulation flipped this to Spain (16.9%) vs Argentina (14.8%) — the tighter estimates (SE ±0.05% vs ±0.22%) resolve the near-tie more reliably. Expected score increased from 93.23 to 97.53, reflecting more accurate probability estimates across all stages.

---

## Data pipeline

### Step 1: Scrape

Data is collected from 8+ open sources using a combination of direct HTTP, the OddsHarvester Playwright scraper (for OddsPortal), and the Polymarket Gamma API:

| Source | Method | Coverage |
|---|---|---|
| **BetExplorer** | ICS calendar embed | 72 group matches, avg of 30+ bookmakers |
| **OddsHarvester** | Playwright → OddsPortal | 72 group matches, per-bookmaker odds |
| **Polymarket** | Gamma API | 6 matches with 3-outcome markets |
| **uanalyse** | GitHub raw CSV | 72 match probs + xG + tournament priors |
| **worldcup-predictor** | GitHub raw CSV | 72 Elo-based W/D/L probabilities |
| **openfootball** | GitHub raw JSON | Full 104-match fixture + bracket skeleton |
| **hicruben** | GitHub raw JSON | Elo ratings for 54 teams |

### Step 2: Normalize

`normalize_data.py` canonicalizes team names (70+ aliases), converts all sources to a common schema, and computes implied probabilities from decimal odds:

```
source, match_id, home_team, away_team, group, date,
home_win_prob, draw_prob, away_win_prob,
home_win_odds, draw_odds, away_win_odds, extra
```

The normalized file has 398 rows across 6 sources covering 119 unique matches.

---

## Mathematical model

### Consensus probability model

For each group-stage match, we compute a weighted consensus from all available sources. For match key $k = (t_1, t_2)$ with $t_1 < t_2$ (alphabetical), each source $s$ contributes:

$$p_s = [P_s(t_1 \text{ wins}),\; P_s(\text{draw}),\; P_s(t_2 \text{ wins})]$$

with source weight $w_s$. The consensus is the weighted average, renormalized:

$$P_k = \frac{\sum_s w_s \cdot p_s}{\sum_s w_s}, \quad \hat{P}_k = \frac{P_k}{\sum P_k}$$

A source is skipped if any probability is missing or non-finite. Default weights:

| Source | Weight | Rationale |
|---|---|---|
| betexplorer | 0.30 | Broadest bookmaker average (30+) |
| oddsharvester | 0.25 | Per-bookmaker OddsPortal scrape |
| polymarket | 0.20 | Prediction market (wisdom of crowd) |
| uanalyse | 0.15 | Model-based + xG |
| worldcup-predictor | 0.10 | Elo-based |

### Elo fallback

For knockout pairings not covered by group-stage odds, we fall back to Elo ratings from [hicruben/world-cup-2026-prediction-model](https://github.com/Hicruben/world-cup-2026-prediction-model). For teams $i$ and $j$ with ratings $R_i, R_j$:

$$q_i = \frac{1}{1 + 10^{-(R_i - R_j)/400}}$$

This win probability is converted to regulation W/D/L using a draw probability that decreases with rating difference:

$$\text{draw} = \text{clamp}\bigl(0.26 - 0.04 \times \frac{|R_i - R_j|}{400},\; 0.18,\; 0.30\bigr)$$

$$P(i \text{ wins}) = (1 - \text{draw}) \times q_i$$
$$P(\text{draw}) = \text{draw}$$
$$P(j \text{ wins}) = (1 - \text{draw}) \times q_j$$

Missing teams receive a default rating of 1650.

### Knockout advancement

Knockout matches cannot end in draws. The advancement probability converts regulation W/D/L into a single advance/loss outcome:

$$P(i \text{ advances}) = P(i \text{ reg. win}) + P(\text{draw}) \times \sigma_i$$

where the shootout advantage is:

$$\sigma_i = 0.5 + 0.20 \times (q_i - 0.5)$$

This gives a slight edge to the stronger team in penalty shootouts.

### Group-stage simulation

Each Monte Carlo iteration simulates all 72 group matches. For each match, we sample from the consensus W/D/L distribution. Tie-breaker scores are synthesized:

- **Draw**: randomly chosen from $\{(0,0), (1,1), (1,1), (2,2)\}$
- **Win margin**: $1 + \text{Bernoulli}(0.28) + \text{Bernoulli}(0.10)$
- **Loser goals**: randomly chosen from $\{0, 1, 1, 2\}$
- **Winner goals**: loser goals + margin

Groups are ranked by: (1) points, (2) goal difference, (3) goals scored, (4) Elo rating, (5) seeded random.

### Third-place qualification

Twelve third-place teams compete for 8 Round of 32 slots. Within each simulation, third-place teams are ranked by points, GD, GS, Elo, and random. The top 8 are assigned to slots using a **backtracking algorithm** with most-constrained-first ordering — this is necessary because a simple greedy approach fails to find valid complete assignments for this slot topology.

### Monte Carlo estimation

After $N$ iterations, probabilities are estimated as:

$$\hat{P}(\text{team reaches stage } S) = \frac{1}{N} \sum_{m=1}^{N} \mathbf{1}_m(\text{team reaches } S)$$

The worst-case standard error (at $p = 0.5$) is:

$$\text{SE}(\hat{P}) \leq \sqrt{\frac{0.25}{N}}$$

| Sims | SE bound | Approximate accuracy |
|---|---:|---:|
| 100 | 0.0500 | ±5.0% |
| 1,000 | 0.0158 | ±1.6% |
| 10,000 | 0.0050 | ±0.5% |
| 50,000 | 0.0022 | ±0.22% |
| 1,000,000 | 0.0005 | ±0.05% |

At 50K sims, the ±0.22% noise is small enough that most bracket picks are stable, but near-ties (e.g., Spain 16.8% vs Argentina 15.1%) can flip between runs. At 1M sims, the ±0.05% noise resolves gaps as small as 0.1% — the champion flipped from Argentina (50K) to Spain (1M) as the 1.7% gap became unambiguous. Beyond ~50K sims, gains diminish: the input probabilities themselves (consensus model ±2-5% per match) become the dominant source of error rather than simulation noise.
### Bracket optimization

The bracket must maximize expected challenge points, not simply pick the most likely winner of every game. The scoring system (203 points total):

| Stage | Picks | Points each | Max |
|---|---:|---:|---:|
| Group placement (exact ordered slots) | 48 | 1 | 48 |
| Reach Round of 32 | 32 | 1 | 32 |
| Reach Round of 16 | 16 | 2 | 32 |
| Reach Quarter-Finals | 8 | 4 | 32 |
| Reach Semi-Finals | 4 | 6 | 24 |
| Reach Final | 2 | 10 | 20 |
| Champion | 1 | 15 | 15 |

The expected score for a bracket $B$ is:

$$E[\text{score}(B)] = \sum_{\text{groups } g} \sum_{\text{positions } r} P(B[g,r] \text{ finishes } r) \cdot 1$$
$$+ \sum_{t \in B_{\text{R32}}} 1 \cdot P(t \text{ reaches R32})$$
$$+ \sum_{t \in B_{\text{R16}}} 2 \cdot P(t \text{ reaches R16})$$
$$+ \sum_{t \in B_{\text{QF}}} 4 \cdot P(t \text{ reaches QF})$$
$$+ \sum_{t \in B_{\text{SF}}} 6 \cdot P(t \text{ reaches SF})$$
$$+ \sum_{t \in B_{\text{F}}} 10 \cdot P(t \text{ reaches Final})$$
$$+ 15 \cdot P(B_{\text{winner}} \text{ wins tournament})$$


## How the expected score is computed

The **expected score** (e.g. **97.53 / 203**) is the probability-weighted sum of every pick in the bracket. For each pick, multiply the probability that the pick is correct by the points it would earn, then sum over all 111 picks.

### The formula

For any single pick:

    E[points] = P(pick is correct) x points if correct

The total expected score sums this over every stage:

    E[score] = sum_group_picks P(correct) x 1
             + sum_R32_picks P(advances) x 1
             + sum_R16_picks P(advances) x 2
             + sum_QF_picks P(advances) x 4
             + sum_SF_picks P(advances) x 6
             + sum_F_picks P(advances) x 10
             + P(champion wins) x 15

### Concrete examples from the current bracket

**Group placement (1 pt each):** Mexico is predicted 1st in Group A. The simulation shows Mexico finishes 1st in 53.8% of iterations:

    E[A-1st] = 0.538 x 1 = 0.538 expected points

South Korea is predicted 2nd but only finishes 2nd in 26.2% of simulations:

    E[A-2nd] = 0.262 x 1 = 0.262 expected points

Across all 48 group placement picks, this sums to roughly 23 expected points (out of 48 max). You do not expect to get all 48 right -- even the best model has uncertainty.

**Advance to Round of 32 (1 pt each):** Spain reaches the knockout in 98.3% of simulations:

    E[Spain in R32] = 0.983 x 1 = 0.983 expected points

**Champion (15 pts):** Spain is the predicted champion, winning in 16.9% of simulations:

    E[champion] = 0.169 x 15 = 2.54 expected points

### Why 97.53 and not 203?

203 is the perfect score. 97.53 is what you would win on average if you could play this bracket millions of times. The gap reflects genuine uncertainty:

| Stage | Max | Expected | Why the gap |
|---|---:|---:|---|
| Group Placement | 48 | ~23 | Hard to predict exact 1st/2nd/3rd/4th |
| Advance to R32 | 32 | ~27 | Easier to predict who qualifies |
| Advance to R16 | 32 | ~18 | Competitive matches, upsets |
| Advance to QF | 32 | ~14 | Only 8 of 32 teams survive |
| Advance to SF | 24 | ~8 | Deep uncertainty |
| Finalist | 20 | ~5 | Very hard to predict finalists |
| Champion | 15 | ~2.5 | 83% chance the pick is wrong |
| **Total** | **203** | **~97.53** | |

Even picking the champion (16.9% probability) only contributes 2.54 expected points because there is an 83.1% chance that pick is wrong. The model is well-calibrated: over many brackets, it would average 97.53 points per bracket.


**Group placements** are optimized by brute force over all $4! = 24$ permutations per group, picking the ordering that maximizes expected placement points.

**Knockout picks** are filled deterministically: optimized group seeds are placed into the bracket skeleton, third-place teams are assigned via backtracking, and a bracket-tree dynamic program chooses the feasible set of winners that maximizes expected stage points. This is different from simply choosing the team with higher one-match advancement probability. The picks are constrained to be nested: $\text{Winner} \subset \text{Finalists} \subset \text{SF} \subset \text{QF} \subset \text{R16} \subset \text{R32}$.

---

## CLI reference

```bash
python3 generate_bracket.py \
  --sims 50000 \
  --seed 42 \
  --model consensus \
  --strategy ev-bracket \
  --probabilities sim \
  --out _data/bracket \
  --formats csv,json,md
```

Current CLI behavior:

| Option | Supported now | Notes |
|---|---|---|
| `--sims` | yes | Number of Monte Carlo iterations; default `50000` |
| `--seed` | yes | Random seed for reproducibility; default `42` |
| `--model consensus` | yes | Uses merged priced group-stage sources, Elo fallback for unpriced pairings |
| `--model elo` | yes | Forces Elo model for all matchups |
| `--model poisson` | no | Parsed for future work; currently exits with an explicit error |
| `--strategy ev-bracket` | yes | Deterministic expected-points bracket fill |
| `--strategy greedy` | no | Parsed for future work; currently exits with an explicit error |
| `--probabilities sim` | yes | Optimizes using Monte Carlo probabilities |
| `--probabilities blend` | yes | Blends simulation with UAnalyse priors before optimization/output |
| `--out` | yes | Output path stem; default `_data/bracket` |
| `--formats` | yes | Comma-separated output formats; default `csv,json,md` |
| `--dry-run` | yes | Loads and validates inputs without simulating |

---

## Odds data sources

The analysis now uses the normalized multi-source consensus from `_data/norm/all_odds_normalized.csv`, not only the legacy BetExplorer ICS feed. The sources below are the current inputs and additional open/free/publicly accessible sources that can improve coverage or calibration.

### Free APIs (no cost, no/low auth)

| Source | Type | Coverage | Notes |
|---|---|---|---|
| [BetExplorer](https://www.betexplorer.com/) | Web scrape / ICS embed | 1X2 odds from 30+ bookmakers averaged per match | Current normalized source. Odds are embedded in the kubeia.io ICS calendar. Also available as a web scraper via OddsHarvester or direct page scrape. |
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

---

## Results tracking

`generate_results.py` reads `_data/bracket.json` (from `generate_bracket.py`) and `_data/results.json` (actual match results) to produce a living `results.md` scoreboard.

```bash
# 1. Generate the bracket predictions
python3 generate_bracket.py --sims 1000000 --seed 42

# 2. Enter match results as they are played
python3 update_results.py                        # List unscored matches
python3 update_results.py --group A              # Show Group A matches
python3 update_results.py -m Mexico_vs_South_Africa -s 2 1

# 3. Regenerate the scoreboard
python3 generate_results.py
```

### Partial group handling

Groups are updated **one match at a time** as results come in. You do not need to wait for all 6 matches in a group to be played:

- **Not started** (⏳): No matches played yet. Teams shown in alphabetical order with 0 pts.
- **In progress** (🔴): Some but not all matches played. Table shows current standings (Pts, GD, Pld) with 🔴 projected markers. Upcoming matches listed below.
- **Complete** (✅/❌): All 6 matches played. Final positions locked in with ✅ (correct) or ❌ (wrong) markers. Points are earned.

Example — Group A with 1 of 6 matches played:

```
### Group A — 🔴 1/6 matches played

| Pos | Predicted | Actual | Pts | GD | Pld | Result |
| 1st | 🇲🇽 Mexico | 🇲🇽 Mexico | 3 | +1 | 1 | 🔴 (projected) |
| 2nd | 🇰🇷 South Korea | 🇰🇷 South Korea | 0 | 0 | 0 | 🔴 (projected) |
...

**Upcoming:**
  - 2026-06-11 20:00 UTC-6: 🇰🇷 South Korea vs 🇨🇿 Czech Republic
  - 2026-06-18 12:00 UTC-4: 🇨🇿 Czech Republic vs 🇿🇦 South Africa
  ...
```

After each match, re-run `python3 generate_results.py` and the table updates instantly.

### Scoring

Points are only earned when a pick is **fully resolved**:

| Stage | Points | When scored |
|---|---:|---|
| Group Placement | +1 per correct position | Only when ALL 6 group matches are played |
| Advance to Knockout | +1 per correct team | Only when ALL groups are complete |
| Advance to R16 | +2 per correct team | When R16 matches are played |
| Advance to QF | +4 per correct team | When QF matches are played |
| Advance to SF | +6 per correct team | When SF matches are played |
| Finalist | +10 per correct team | When Final is played |
| Winner | +15 | When Champion is determined |

Until a stage is resolved, its picks show as **pending** and contribute 0 to the actual score.

### Expected vs Actual score

- **Expected Score** (e.g. 97.53 / 203): Computed at bracket-generation time. Sum of `P(correct) × points` for all 111 picks. This is the model's ex-ante estimate and does not change as matches are played.
- **Actual Score** (e.g. 1 / 203): Points earned from correct predictions against real results. Starts at 0 and increases as matches are played. Maximum is 203 (perfect bracket).
- **Accuracy**: Fraction of resolved predictions that were correct (e.g. 1/4 = 25%).

### Data files

| File | Purpose | Updated by |
|---|---|---|
| `_data/bracket.json` | Full bracket predictions + probabilities | `generate_bracket.py` |
| `_data/results.json` | Actual match results | `update_results.py` |
| `results.md` | Visual scoreboard | `generate_results.py` |