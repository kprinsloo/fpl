"""Fetch weekly player points from the FPL API and build dashboard data.

Outputs:
  data/<season>/gw/<gw>.json        cached live data per finished gameweek
  data/<season>/bootstrap.json      latest bootstrap-static snapshot
  data/<season>/fixtures.json       all fixtures (used by predict.py)
  data/<season>/player_points.csv   one row per player, one column per GW
  docs/data/fpl.json                players, teams and weekly points
  docs/data/stats.json              season and last-4-GW stat totals
  docs/data/history.json            price and ownership per player per GW
  docs/data/fixtures.json           slim fixture list (standings, next match)
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
POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
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


def update_history(season_dir, boot, gws):
    """Price (and % owned) per player per finished GW.

    Missing weeks are backfilled once from element-summary (FPL only gives a
    raw ownership count there, converted with today's manager total). The
    latest week is a snapshot of bootstrap's exact numbers.
    """
    path = os.path.join(season_dir, "history.json")
    hist = read_json(path, {})
    total = boot.get("total_players") or 1
    latest = gws[-1] if gws else None
    needs_backfill = any(str(gw) not in hist.get("_gws", []) for gw in gws[:-1])
    if needs_backfill:
        print("Backfilling price and ownership history from element-summary...")
        for el in boot["elements"]:
            pid = str(el["id"])
            try:
                summ = get(f"element-summary/{el['id']}/")
            except Exception as e:
                print(f"  {pid}: {e}")
                continue
            rec = hist.setdefault(pid, {})
            for h in summ.get("history", []):
                gw = h["round"]
                if gw in gws:  # last fixture of a double GW wins
                    rec[str(gw)] = [h["value"] / 10, round(h["selected"] / total * 100, 2)]
        hist["_gws"] = [str(g) for g in gws]
    if latest:
        for el in boot["elements"]:
            hist.setdefault(str(el["id"]), {})[str(latest)] = [el["now_cost"] / 10, num(el.get("selected_by_percent"))]
        hist["_gws"] = sorted(set(hist.get("_gws", [])) | {str(latest)}, key=int)
    write_json(path, hist)
    out = {}
    for el in boot["elements"]:
        rec = hist.get(str(el["id"]), {})
        out[str(el["id"])] = {
            "p": [rec.get(str(g), [None, None])[0] for g in gws],
            "o": [rec.get(str(g), [None, None])[1] for g in gws],
        }
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
        pts, mins = [], []
        for gw in gws:
            s = gw_data[gw]["players"].get(pid)
            pts.append(int(s["total_points"]) if s else 0)
            mins.append(int(s["minutes"]) if s else 0)
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
            "start_cost": (el["now_cost"] - el.get("cost_change_start", 0)) / 10,
            "net_tr": el.get("transfers_in_event", 0) - el.get("transfers_out_event", 0),
            "pts": pts,
            "min": mins,
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
    events = {e["id"]: e for e in boot["events"]}
    gw_info = [{"gw": g, "avg": events[g].get("average_entry_score"), "high": events[g].get("highest_score")} for g in gws]
    hist = update_history(season_dir, boot, gws)
    slim_fx = [{"gw": f.get("event"), "h": f["team_h"], "a": f["team_a"], "hs": f.get("team_h_score"),
                "as": f.get("team_a_score"), "fin": bool(f.get("finished")), "ko": f.get("kickoff_time")}
               for f in fixtures]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(os.path.join(ROOT, "docs", "data", "fpl.json"), {
        "season": season, "updated": now, "current_gw": current, "gws": gws,
        "total_players": boot.get("total_players"), "gw_info": gw_info,
        "teams": teams, "players": players,
    })
    write_json(os.path.join(ROOT, "docs", "data", "history.json"), {"gws": gws, "players": hist})
    write_json(os.path.join(ROOT, "docs", "data", "fixtures.json"), slim_fx)
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
    summary_file = os.environ.get("SUMMARY_FILE")
    if summary_file and gws:
        i = len(gws) - 1
        top3 = sorted(players, key=lambda p: -p["pts"][i])[:3]
        lines = [f"**Gameweek {gws[-1]}** is in.", "",
                 "Top scorers this week: " + ", ".join(f'{p["name"]} ({p["pts"][i]})' for p in top3),
                 f'Season leader: {players[0]["name"]} ({players[0]["total"]} pts)']
        if gw_info[-1]["avg"] is not None:
            lines.append(f'Manager average {gw_info[-1]["avg"]}, highest {gw_info[-1]["high"]}')
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
