"""Fetch weekly player points from the FPL API and build dashboard data.

Outputs:
  data/<season>/gw/<gw>.json        cached live data per finished gameweek
  data/<season>/bootstrap.json      latest bootstrap-static snapshot
  data/<season>/fixtures.json       all fixtures (used by predict.py)
  data/<season>/player_points.csv   one row per player, one column per GW
  docs/data/fpl.json                players, teams and weekly points
  docs/data/stats.json              season and last-4-GW stat totals
"""
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fpl_api import ROOT, finished_gws, get, read_json, season_of, write_json  # noqa: E402

# Bump when the set of stored stats changes; cached GW files with another
# version are fetched again.
STATS_VERSION = 2
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
# Stats summed into stats.json (anything numeric in the live data is kept,
# these are listed first in the dashboard).
FLOAT_STATS = {"influence", "creativity", "threat", "ict_index", "expected_goals",
               "expected_assists", "expected_goal_involvements", "expected_goals_conceded"}
SKIP_STATS = {"in_dreamteam"}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_gw(season_dir, gw, refresh=False):
    path = os.path.join(season_dir, "gw", f"{gw}.json")
    cached = read_json(path)
    if cached and cached.get("v") == STATS_VERSION and not refresh:
        return cached
    live = get(f"event/{gw}/live/")
    out = {"v": STATS_VERSION, "gw": gw, "players": {}}
    for el in live["elements"]:
        stats = {k: num(v) for k, v in el["stats"].items() if k not in SKIP_STATS}
        out["players"][str(el["id"])] = stats
    write_json(path, out)
    return out


def main():
    boot = get("bootstrap-static/")
    season = season_of(boot)
    season_dir = os.path.join(ROOT, "data", season)
    write_json(os.path.join(season_dir, "bootstrap.json"), boot)
    fixtures = get("fixtures/")
    write_json(os.path.join(season_dir, "fixtures.json"), fixtures)

    gws = finished_gws(boot)
    current = next((e["id"] for e in boot["events"] if e.get("is_current")), gws[-1] if gws else 0)
    latest = gws[-1] if gws else None
    # Always refetch the latest finished GW: bonus points can be corrected late.
    gw_data = {gw: load_gw(season_dir, gw, refresh=(gw == latest)) for gw in gws}

    teams = {t["id"]: {"name": t["name"], "short": t["short_name"]} for t in boot["teams"]}
    players = []
    stat_keys = set()
    for gd in gw_data.values():
        for s in gd["players"].values():
            stat_keys.update(s.keys())
    stat_keys = sorted(stat_keys)
    last4 = gws[-4:]
    stats_out = {}

    for el in boot["elements"]:
        pid = str(el["id"])
        pts = []
        for gw in gws:
            s = gw_data[gw]["players"].get(pid)
            pts.append(int(s["total_points"]) if s else 0)
        players.append({
            "id": el["id"],
            "name": el["web_name"],
            "full": f'{el["first_name"]} {el["second_name"]}',
            "team": el["team"],
            "pos": POSITIONS.get(el["element_type"], "?"),
            "cost": el["now_cost"] / 10,
            "total": el["total_points"],
            "form": num(el.get("form")),
            "sel": num(el.get("selected_by_percent")),
            "status": el.get("status", "a"),
            "chance": el.get("chance_of_playing_next_round"),
            "news": el.get("news", ""),
            "pts": pts,
        })
        season_tot = {k: 0.0 for k in stat_keys}
        last4_tot = {k: 0.0 for k in stat_keys}
        for gw in gws:
            s = gw_data[gw]["players"].get(pid)
            if not s:
                continue
            for k in stat_keys:
                v = s.get(k, 0.0)
                season_tot[k] += v
                if gw in last4:
                    last4_tot[k] += v
        rnd = lambda d: {k: (round(v, 2) if k in FLOAT_STATS else int(v)) for k, v in d.items()}  # noqa: E731
        stats_out[pid] = {"season": rnd(season_tot), "last4": rnd(last4_tot)}

    players.sort(key=lambda p: -p["total"])
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(os.path.join(ROOT, "docs", "data", "fpl.json"), {
        "season": season, "updated": now, "current_gw": current, "gws": gws,
        "teams": teams, "players": players,
    })
    write_json(os.path.join(ROOT, "docs", "data", "stats.json"), {
        "season": season, "updated": now, "gws": gws, "last4": last4,
        "keys": stat_keys, "players": stats_out,
    })

    with open(os.path.join(season_dir, "player_points.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "team", "pos", "cost", "total"] + [f"GW{g}" for g in gws])
        for p in players:
            w.writerow([p["id"], p["name"], teams[p["team"]]["short"], p["pos"], p["cost"], p["total"]] + p["pts"])

    print(f"{season}: {len(players)} players, {len(gws)} finished gameweeks (current GW{current})")


if __name__ == "__main__":
    main()
