# FPL Tracker

Weekly overview of the current Fantasy Premier League season, with a dashboard
on GitHub Pages: https://kprinsloo.github.io/fpl/

## What it shows

- **Overview**: manager average vs highest score, top 10 for any gameweek, player comparison,
  price and ownership charts (searchable), average points by position, team points heatmap,
  and a sortable player table with sparklines.
- **My team** (`#manager=<id>`): rank tiles with top %, overall and gameweek rank chart with chips,
  points by position, and a red-to-green squad points table.
- **Top performers**: one table per position (top 30), last 4 GWs or whole season, ~40 stats,
  your squad marked, and predicted points for the next 3 gameweeks.
- **Standings**: Premier League table with European and relegation zones, form and next match.

## How it refreshes

`.github/workflows/refresh.yml` runs every Tuesday at 06:00 UTC (and on pushes to `main`):

1. `scripts/fetch_fpl.py` pulls player data from the public FPL API, caches each finished
   gameweek in `data/<season>/gw/`, and writes `docs/data/fpl.json`, `stats.json`,
   `history.json` (price and ownership), `fixtures.json` and a CSV in `data/<season>/`.
2. `scripts/fetch_managers.py` fetches every manager listed in `managers.json`, including
   their picks each week (cached in `data/<season>/managers/`).
3. `scripts/predict.py` writes next-3-GW expected points to `docs/data/predictions.json`.
4. The data is committed and the `docs/` folder is deployed to GitHub Pages.

Scheduled and manual runs post a comment on the "Weekly refresh log" issue.

To track another manager: Actions → Refresh FPL data → Run workflow, and enter the manager ID.

## Testing offline

```
python tests/make_fixtures.py /tmp/fpl-fixtures
FPL_FIXTURES=/tmp/fpl-fixtures python scripts/fetch_fpl.py
FPL_FIXTURES=/tmp/fpl-fixtures python scripts/fetch_managers.py
python scripts/predict.py
```
The sample data is random. Don't commit what it produces.
