# FPL Tracker

Weekly overview of the current Fantasy Premier League season, with a dashboard
on GitHub Pages: https://kprinsloo.github.io/fpl/

## What it shows

- **Overview**: every player's points per gameweek, cumulative points for the top 10, search and filters.
- **My team**: overall rank and points per gameweek for each tracked manager, plus the current squad.
- **Top performers**: season or last-4-GW totals for any stat, with expected points (xP) for the next 3 gameweeks.

## How it refreshes

`.github/workflows/refresh.yml` runs every Tuesday at 06:00 UTC (and on pushes to `main`):

1. `scripts/fetch_fpl.py` pulls player data from the public FPL API, caches each finished
   gameweek in `data/<season>/gw/`, and writes `docs/data/fpl.json`, `docs/data/stats.json`
   and a CSV in `data/<season>/`.
2. `scripts/fetch_managers.py` fetches every manager listed in `managers.json`.
3. `scripts/predict.py` writes next-3-GW expected points to `docs/data/predictions.json`.
4. The data is committed and the `docs/` folder is deployed to GitHub Pages.

Scheduled and manual runs post a comment on the "Weekly refresh log" issue.

To track another manager: Actions → Weekly refresh → Run workflow, and enter the manager ID.

## Testing offline

```
python tests/make_fixtures.py /tmp/fpl-fixtures
FPL_FIXTURES=/tmp/fpl-fixtures python scripts/fetch_fpl.py
FPL_FIXTURES=/tmp/fpl-fixtures python scripts/fetch_managers.py
python scripts/predict.py
```
The sample data is random. Don't commit what it produces.
