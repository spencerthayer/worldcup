---

Agent Instructions:
 1. Read the brackets_info.md and create a comprehensive build plan.
 2. Spin up other `Owl Alpha~ subagents to expediate the build.
 3. Begin build phase.
 4. Regularly commit changes so stuff doesn't get lost.
 5. Code review the work.
 6. At the end update @brackets_info.md with the work you did at the very bottom of the file be verbose and detailed

 Notes: raw data and normalized data is available to you.

---

# World Cup Bracket Generator - Implementation Instructions

This file is the handoff spec for an agent that will build the local Python
script(s). The goal is to reproduce the statistical bracket analysis locally,
from the data already in this repository, and output a bracket that maximizes
expected points for the WC Bracket Challenge format.

Target first script:

```bash
python3 generate_bracket.py --sims 50000 --seed 42
```

Acceptable first implementation: one file, `generate_bracket.py`.

If it grows too large, split it into:

| File | Responsibility |
|---|---|
| `generate_bracket.py` | CLI orchestration and rendering |
| `bracket_model.py` | source merge, consensus probabilities, Elo fallback |
| `bracket_sim.py` | group and knockout Monte Carlo simulation |
| `bracket_optimize.py` | expected-points bracket optimizer |
| `bracket_validate.py` | invariants and prior comparison |

Do not change raw data files. The generator may write `_data/bracket.json`,
`_data/bracket.csv`, and `_data/bracket.md`.

---

## 1. What The Script Must Produce

The script must produce a complete bracket:

- ordered 1st/2nd/3rd/4th placement pick for each group A-L,
- 32 teams picked to reach the knockout bracket,
- 16 teams picked to reach the Round of 16,
- 8 teams picked to reach the Quarter-Finals,
- 4 teams picked to reach the Semi-Finals,
- 2 finalists,
- 1 winner.

The bracket must maximize expected challenge points, not simply pick the most
likely winner of every game.

Expected outputs:

- stdout summary,
- `_data/bracket.json` — full machine-readable result (config, picks, per-team
  probabilities, validation),
- `_data/bracket.csv` — tidy one-row-per-pick table for spreadsheets,
- `_data/bracket.md` — human-readable report mirroring the challenge layout.

All three artifacts are written from the same in-memory result object so they
never disagree. Selection is controlled by `--formats` (§12); the default emits
all three.

The JSON must contain:

```json
{
  "generated_at": "ISO-8601",
  "config": {
    "sims": 50000,
    "seed": 42,
    "model": "consensus",
    "strategy": "ev-bracket",
    "probabilities": "sim"
  },
  "expected_score": 0.0,
  "group_placements": {
    "A": ["Team 1", "Team 2", "Team 3", "Team 4"]
  },
  "round_of_32": [],
  "round_of_16": [],
  "quarter_finals": [],
  "semi_finals": [],
  "finalists": [],
  "winner": "",
  "per_team_probs": {},
  "validation": {}
}
```

---

## 2. Scoring Rules To Optimize

Total possible score is 203.

| Stage | Pick count | Points each | Max |
|---|---:|---:|---:|
| Group placement, exact ordered slots | 48 | 1 | 48 |
| Reach Round of 32 | 32 | 1 | 32 |
| Reach Round of 16 | 16 | 2 | 32 |
| Reach Quarter-Finals | 8 | 4 | 32 |
| Reach Semi-Finals | 4 | 6 | 24 |
| Reach Final | 2 | 10 | 20 |
| Champion | 1 | 15 | 15 |

The expected score for a submitted bracket `B` is:

```text
E[score(B)] =
  sum_groups sum_positions P(B[group,position] finishes position)
  + sum_{t in B_R32}   1  * P(t reaches R32)
  + sum_{t in B_R16}   2  * P(t reaches R16)
  + sum_{t in B_QF}    4  * P(t reaches QF)
  + sum_{t in B_SF}    6  * P(t reaches SF)
  + sum_{t in B_Final} 10 * P(t reaches Final)
  + 15 * P(B_winner wins tournament)
```

The knockout picks must be nested and bracket-feasible:

```text
Winner subset Finalists subset SF subset QF subset R16 subset R32
```

Two teams that meet in the same simulated bracket match cannot both advance past
that match in the submitted bracket.

---

## 3. Data Inputs

Primary input:

```text
_data/norm/all_odds_normalized.csv
```

Schema:

```text
source, match_id, home_team, away_team, group, date,
home_win_prob, draw_prob, away_win_prob,
home_win_odds, draw_odds, away_win_odds, extra
```

Normalized sources:

| Source | Use |
|---|---|
| `betexplorer` | group-stage 1X2 bookmaker average |
| `oddsharvester` | group-stage 1X2 bookmaker average |
| `uanalyse` | group-stage model probabilities and xG |
| `worldcup-predictor` | group-stage Elo W/D/L probabilities |
| `polymarket` | small number of market probabilities, low coverage |
| `openfootball` | fixtures and full knockout skeleton |

Supplementary inputs:

| File | Use |
|---|---|
| `_data/raw/openfootball/worldcup-2026.json` | authoritative fixture and bracket topology |
| `_data/raw/hicruben/elo-calibrated.json` | Elo ratings for fallback match probabilities |
| `_data/raw/uanalyse/latest/tournament_probabilities.csv` | validation priors and optional blend |
| `_data/raw/uanalyse/latest/match_predictions.csv` | xG for optional Poisson score model |
| `_data/raw/worldcup-predictor/wc2026_predictions.csv` | extra Elo and neutral-site metadata |

The generator must read the bracket skeleton from `worldcup-2026.json`; do not
hard-code the bracket except as a validation assertion.

---

## 4. Team Canonicalization

Reuse the intent of `normalize_data.py` aliases. The generator must canonicalize
team names before joining sources.

Required aliases include:

| Variant | Canonical |
|---|---|
| `United States` | `USA` |
| `Czechia` | `Czech Republic` |
| `Bosnia-Herzegovina` | `Bosnia and Herzegovina` |
| `Bosnia & Herzegovina` | `Bosnia and Herzegovina` |
| `Turkiye`, `Türkiye`, `Trkiye` | `Turkey` |
| `Curaçao`, `Curacao`, `Curaao` | `Curaçao` |
| `DR Congo`, `Congo DR`, `Democratic Republic of the Congo` | `DR Congo` |
| `Cote d'Ivoire`, `Ivory Coast` | `Ivory Coast` |

Implementation requirement:

```python
def nteam(name: str) -> str:
    """Return canonical team name."""
```

Also implement:

```python
def match_key(team_a: str, team_b: str) -> tuple[str, str]:
    """Return sorted canonical pair."""
```

Do not join sources on `match_id` alone. Home/away orientation can flip between
neutral-venue sources.

---

## 5. Consensus Match Probability Model

Build:

```python
def match_probs(team_a: str, team_b: str) -> tuple[float, float, float]:
    """
    Return P(team_a regulation win), P(draw), P(team_b regulation win).
    Uses consensus group-stage probabilities when available, otherwise Elo.
    """
```

### 5.1 Source weighting

Default weights:

```python
SOURCE_WEIGHTS = {
    "betexplorer": 0.30,
    "oddsharvester": 0.25,
    "polymarket": 0.20,
    "uanalyse": 0.15,
    "worldcup-predictor": 0.10,
}
```

For each match key `k = sorted(team_i, team_j)`, align every source row to the
same sorted orientation.

For source `s`:

```text
p_s = [P_s(k_1 wins), P_s(draw), P_s(k_2 wins)]
w_s = SOURCE_WEIGHTS[s]
```

Merge:

```text
P_k = sum_s(w_s * p_s) / sum_s(w_s)
P_k = P_k / sum(P_k)
```

Skip a source row if any probability is missing or non-finite. If the triple
sums close to 1, keep it. If it sums to something positive but not exactly 1,
renormalize once. Do not remove bookmaker vig again; the normalized CSV already
stores fair probabilities.

### 5.2 Elo fallback

For unpriced pairings, use Elo from `_data/raw/hicruben/elo-calibrated.json`.

For teams `i` and `j`:

```text
q_i = 1 / (1 + 10 ** (-(R_i - R_j) / 400))
q_j = 1 - q_i
```

Convert this to regulation W/D/L:

```text
draw = clamp(0.26 - 0.04 * abs(R_i - R_j) / 400, 0.18, 0.30)
P(i wins regulation) = (1 - draw) * q_i
P(draw)              = draw
P(j wins regulation) = (1 - draw) * q_j
```

If a team is missing from Elo, use rating `1650`.

### 5.3 Knockout advancement

Knockout matches cannot end in draws. Convert regulation W/D/L to advancement:

```text
shootout_i = 0.5 + 0.20 * (q_i - 0.5)
P(i advances) = P(i regulation win) + P(draw) * shootout_i
P(j advances) = 1 - P(i advances)
```

A simpler first version may use `shootout_i = 0.5`, but keep the function
isolated so it can be calibrated later.

Implement:

```python
def advance_prob(team_a: str, team_b: str) -> float:
    """Return P(team_a advances over team_b)."""
```

---

## 6. Optional Poisson Scoreline Model

The default model can simulate W/D/L and synthesize tie-breaker scores. Add a
`--model poisson` option if time allows.

If xG exists for a group match:

```text
G_i ~ Poisson(lambda_i)
G_j ~ Poisson(lambda_j)
```

Score probability:

```text
P(G_i=a, G_j=b) =
  exp(-lambda_i) * lambda_i^a / a!
  * exp(-lambda_j) * lambda_j^b / b!
```

Use score support `0..10`. Add any probability tail to 10 goals.

Implied W/D/L:

```text
P(i wins) = sum_{a>b} P(a,b)
P(draw)   = sum_{a=b} P(a,b)
P(j wins) = sum_{a<b} P(a,b)
```

If xG is unavailable:

```text
total_goals = 2.55
lambda_i = max(0.2, total_goals * q_i)
lambda_j = max(0.2, total_goals * (1 - q_i))
```

Do not make Poisson the default until its output is validated against the market
probabilities.

---

## 7. Group-Stage Simulation

Simulate the complete group stage inside each Monte Carlo iteration.

For each group, initialize per-team state:

```text
points = 0
goals_for = 0
goals_against = 0
goal_difference = goals_for - goals_against
```

For every group fixture in `openfootball`:

1. get `match_probs(team_a, team_b)`,
2. sample home win / draw / away win,
3. add points,
4. produce a scoreline for tie-breakers.

If not using Poisson, synthesize tie-breaker scores:

```text
draw score: choose from [0-0, 1-1, 1-1, 2-2]
win margin: 1 + Bernoulli(0.28) + Bernoulli(0.10)
loser goals: choose from [0, 1, 1, 2]
winner goals: loser goals + margin
```

Rank each group by:

1. points,
2. goal difference,
3. goals scored,
4. head-to-head mini-table if implemented,
5. Elo rating,
6. seeded random tie-breaker.

Record indicators for each simulation `m`:

```text
I_m(team finishes 1st)
I_m(team finishes 2nd)
I_m(team finishes 3rd)
I_m(team finishes 4th)
I_m(team reaches R32)
```

After `N` simulations:

```text
P_hat(team finishes position r) =
  (1 / N) * sum_m I_m(team finishes position r)

P_hat(team reaches R32) =
  (1 / N) * sum_m I_m(team reaches R32)
```

Standard error:

```text
SE(P_hat) = sqrt(P_hat * (1 - P_hat) / N)
```

At `N = 50000`, worst-case standard error is about `0.00224`.

---

## 8. Third-Place Qualification And Slot Assignment

There are 12 third-place teams. Eight qualify for the Round of 32.

Within each simulation, rank third-place teams by:

1. points,
2. goal difference,
3. goals scored,
4. Elo rating, because fair-play data is unavailable,
5. seeded random tie-breaker.

The top eight qualify.

Implement one isolated function:

```python
def assign_thirds(qualified_thirds, bracket_slots, method="greedy"):
    """
    Return mapping from third-place slot match number to team.
    This is the only place where the third-place allocation rule lives.
    """
```

Correct future behavior:

```text
Use the official FIFA allocation table:
qualified group set -> assignment of groups to 3X slots.
```

Current fallback:

```text
For each 3X slot in Round-of-32 match order:
    choose the strongest unassigned qualified third-place team whose group
    is allowed by that slot placeholder.
```

Use the within-iteration third-place ranking as "strongest", not global Elo.

---

## 9. Knockout Simulation

Use the knockout matches from `worldcup-2026.json`.

Slot resolution:

```text
1A, 2A, ..., 1L, 2L -> simulated group placements
3A/B/C/...          -> assigned third-place qualifier
W74, W75, ...       -> winner of previous knockout match
```

Round mapping:

```text
matches 73-88  -> Round of 32
matches 89-96  -> Round of 16
matches 97-100 -> Quarter-Finals
matches 101-102 -> Semi-Finals
Final           -> W101 vs W102
```

For every knockout match:

```text
p = advance_prob(team_a, team_b)
u = Uniform(0, 1)
winner = team_a if u < p else team_b
```

Record indicators:

```text
R32 participant: seeded into matches 73-88
R16 participant: winners of 73-88
QF participant:  winners of 89-96
SF participant:  winners of 97-100
Finalist:        winners of 101-102
Champion:        winner of Final
```

After `N` simulations:

```text
P_hat(team reaches stage S) =
  (1 / N) * sum_m I_m(team reaches stage S)
```

Assert monotonicity:

```text
P(R32) >= P(R16) >= P(QF) >= P(SF) >= P(Final) >= P(Champion)
```

---

## 10. Validation Against UAnalyse Priors

Load:

```text
_data/raw/uanalyse/latest/tournament_probabilities.csv
```

Compare simulation probabilities to priors for:

```text
prob_reach_round_of_32
prob_reach_quarterfinals
prob_reach_semifinals
prob_reach_final
prob_champion
```

Mean absolute deviation:

```text
MAD(stage) =
  (1 / teams) * sum_t abs(P_sim(t, stage) - P_prior(t, stage))
```

Also report Spearman rank correlation by stage if easy to implement.

Optional probability blend for optimizer:

```text
P_blend(t, stage) =
  alpha_stage * P_sim(t, stage)
  + (1 - alpha_stage) * P_prior(t, stage)
```

Recommended first-pass `alpha_stage`:

| Stage | Alpha |
|---|---:|
| R32 | 0.80 |
| R16 | 1.00 |
| QF | 0.65 |
| SF | 0.60 |
| Final | 0.55 |
| Champion | 0.55 |

There is no UAnalyse R16 prior. Use simulation-only for R16.

If blending is used, enforce monotonicity afterward by clipping deeper-stage
probabilities to the previous stage.

The first implementation may optimize with simulation-only probabilities, but
the report must show validation deltas.

---

## 11. Pick Optimization

### 11.1 Group placement optimizer

For every group `g`, build a 4x4 matrix:

```text
M[team, position] = P(team finishes position)
```

Choose the ordered placement that maximizes expected group-placement points:

```text
best_order_g =
  argmax permutation pi of the 4 teams
    sum_{position=1..4} M[pi[position], position]
```

Implement by brute force over `4! = 24` permutations.

### 11.2 Knockout bracket optimizer

Do not independently pick top teams per stage; that can create impossible
brackets. The selected knockout picks must come from one filled bracket.

Acceptable first-pass optimizer:

1. Choose deterministic group seeds from the optimized group placements.
2. Choose deterministic third-place qualifiers using the highest R32 or
   third-place qualification probabilities.
3. Fill the Round-of-32 bracket.
4. For each knockout match, choose the advancing team with higher downstream
   expected value, not just higher one-match win probability.

For a candidate filled bracket `b`:

```text
EV_knockout(b) =
  sum_{t in b_R32}   1  * P(t reaches R32)
  + sum_{t in b_R16} 2  * P(t reaches R16)
  + sum_{t in b_QF}  4  * P(t reaches QF)
  + sum_{t in b_SF}  6  * P(t reaches SF)
  + sum_{t in b_F}   10 * P(t reaches Final)
  + 15 * P(b_champion wins tournament)
```

Better optimizer if time allows:

1. Extract the top `K=25` most common Round-of-32 seed maps from simulations.
2. For each seed map, enumerate or dynamically optimize feasible winner choices.
3. Score each filled bracket by expected points.
4. Keep the global max.

Champion/finalist coupling matters because those picks are worth 15 and 10
points. Explicitly evaluate at least the top 10 champion candidates by
`P(champion)` and find the best feasible bracket conditioned on each candidate
winning.

---

## 12. Required CLI

Use `argparse`.

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

Options:

| Option | Values | Default |
|---|---|---|
| `--sims` | positive int | `50000` |
| `--seed` | int | `42` |
| `--model` | `consensus`, `elo`, `poisson` | `consensus` |
| `--strategy` | `ev-bracket`, `greedy` | `ev-bracket` |
| `--probabilities` | `sim`, `blend` | `sim` |
| `--out` | path stem (no extension) | `_data/bracket` |
| `--formats` | comma list of `csv`, `json`, `md` | `csv,json,md` |
| `--dry-run` | flag | false |

`--out` is a path **stem**: the chosen formats are written by appending the
matching extension (`<stem>.json`, `<stem>.csv`, `<stem>.md`). For backward
compatibility, if `--out` ends in `.json`, `.csv`, or `.md`, strip the extension
to recover the stem and continue to honor `--formats`. The same seed and inputs
must produce identical output across every format.

---

## 13. Rendering Requirements

All formats are serialized from one result object, so values must match exactly
across JSON, CSV, and markdown (differing only in rounding/presentation).

### 13.1 JSON (`<stem>.json`)

The full machine-readable result using the schema in §1: `generated_at`,
`config`, `expected_score`, `group_placements`, the six knockout pick lists,
`per_team_probs`, and `validation`. Numbers are written unrounded (full float
precision); rounding is a presentation concern handled only in CSV/markdown.

### 13.2 CSV (`<stem>.csv`)

A tidy, one-row-per-pick table (long format), sorted by stage order then group
then slot. Header and columns:

```text
stage,group,slot,team,reach_prob,points_if_correct,expected_points
```

| Column | Meaning |
|---|---|
| `stage` | one of `group_placement`, `round_of_32`, `round_of_16`, `quarter_finals`, `semi_finals`, `finalist`, `winner` |
| `group` | group letter `A`–`L` for `group_placement` rows; empty otherwise |
| `slot` | placement rank `1`–`4` for `group_placement` rows; empty otherwise |
| `team` | canonical team name |
| `reach_prob` | simulated probability the team achieves that stage (for `group_placement`, the probability the team finishes in that exact slot) |
| `points_if_correct` | per-pick points for the stage from the §2 table (`1`, `1`, `2`, `4`, `6`, `10`, `15`) |
| `expected_points` | `reach_prob * points_if_correct` |

Row counts per file: 48 `group_placement` + 32 + 16 + 8 + 4 + 2 + 1 = **111 pick
rows** plus the header. The sum of the `expected_points` column must equal
`expected_score` in the JSON (within float tolerance). Quote fields containing
commas (team names generally do not, but quote defensively) and write UTF-8 so
names like `Curaçao` and `Türkiye` round-trip. Use `reach_prob` rounded to six
decimals and `expected_points` to six decimals in the CSV (machine-friendly);
markdown applies coarser display rounding per §13.3.

### 13.3 Markdown (`<stem>.md`)

The markdown report should include:

- model config,
- source weights,
- number of simulations,
- expected score out of 203,
- group placement table with probabilities,
- R32/R16/QF/SF/finalist/winner picks,
- per-stage expected point contribution,
- top champion probabilities,
- validation MAD against UAnalyse priors,
- known data issues.

Round probabilities should be rounded to one decimal percentage point. Expected
points should be rounded to two decimals.

Known data issues to call out:

- `Bosnia & Herzegovina` must canonicalize to `Bosnia and Herzegovina`.
- `Curaao` must canonicalize to `Curaçao`.
- Polymarket slugs should not be trusted unless the teams in the slug match the
  parsed teams.
- Exact FIFA 2026 third-place allocation table is not present yet; fallback must
  be documented in output.

---

## 14. Invariants And Tests

Minimum assertions:

- every group placement is a permutation of exactly four teams,
- exactly 32 R32 picks,
- exactly 16 R16 picks,
- exactly 8 QF picks,
- exactly 4 SF picks,
- exactly 2 finalists,
- exactly 1 winner,
- nested stage sets are valid,
- winner is one of the finalists,
- finalist teams are among semi-finalists,
- no impossible same-match co-advancement in the filled bracket,
- probabilities are finite and in `[0,1]`,
- per-team stage probabilities are monotonic:
  `R32 >= R16 >= QF >= SF >= Final >= Champion`,
- perfect oracle scoring function returns 203,
- the CSV holds exactly 111 pick rows (48 + 32 + 16 + 8 + 4 + 2 + 1) plus header,
- the CSV `expected_points` column sums to the JSON `expected_score` within a
  small float tolerance,
- JSON, CSV, and markdown report identical picks and identical `expected_score`.

Dry run should:

1. load all inputs,
2. canonicalize teams,
3. build consensus probabilities,
4. parse bracket skeleton,
5. validate no missing group fixtures,
6. print data quality warnings,
7. exit without simulating.

---

## 15. Prototype Analysis To Reproduce

I ran a prototype of this analysis in-memory using:

```text
sims = 50000
seed = 42
model = consensus for group-stage priced matches
fallback = Elo for unpriced knockout pairings
third-place assignment = greedy fallback
```

The future script does not need to hard-code these results, but it should be able
to reproduce a similar report from the current data.

Prototype validation against UAnalyse priors was approximately:

| Stage | MAD |
|---|---:|
| R32 | 0.063 |
| QF | 0.050 |
| SF | 0.033 |
| Final | 0.019 |
| Champion | 0.011 |

The prototype's highest expected-points final was Spain vs Argentina with Spain
as champion. Treat that as a regression smoke test, not as a required hard-coded
answer. If the final implementation changes because of better third-place
allocation, Poisson tie-breakers, or probability blending, explain the delta in
the generated report.
