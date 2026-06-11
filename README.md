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
