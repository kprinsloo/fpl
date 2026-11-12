"""Fetch history and weekly picks for every FPL manager in managers.json.

Usage: python scripts/fetch_managers.py [--add MANAGER_ID]
Run after fetch_fpl.py (it reads the cached gameweek data).
Writes docs/data/managers.json.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fpl_api import ROOT, finished_gws, get, read_json, season_of, write_json  # noqa: E402

LIST_FILE = os.path.join(ROOT, "managers.json")


def load_ids():
    return [int(i) for i in read_json(LIST_FILE, {"managers": []})["managers"]]


def save_ids(ids):
    with open(LIST_FILE, "w", encoding="utf-8") as f:
        json.dump({"managers": ids}, f, indent=2)
        f.write("\n")


def gw_picks(mid, gw, cache_dir, refresh):
    path = os.path.join(cache_dir, f"{gw}.json")
    cached = read_json(path)
    if cached and not refresh:
        return cached
    p = get(f"entry/{mid}/event/{gw}/picks/")
    write_json(path, p)
    return p


def score_picks(p, live):
    """Apply auto-subs and captaincy; return per-pick effective multipliers.

    The FPL picks feed keeps the picks as set before the deadline, so
    automatic substitutions and a vice-captain taking over are applied here.
    """
    chip = p.get("active_chip")
    mins = lambda e: live.get(str(e), {}).get("minutes", 0)  # noqa: E731
    picks = sorted(p["picks"], key=lambda x: x["position"])
    playing = {x["element"] for x in picks if x["position"] <= 11 or chip == "bboost"}
    for s in p.get("automatic_subs", []):
        playing.discard(s["element_out"])
        playing.add(s["element_in"])
    cap_mult = 3 if chip == "3xc" else 2
    cap = next((x["element"] for x in picks if x["is_captain"]), None)
    vc = next((x["element"] for x in picks if x["is_vice_captain"]), None)
    armband = cap if cap and mins(cap) > 0 else (vc if vc and mins(vc) > 0 else None)
    out = []
    for x in picks:
        e = x["element"]
        mult = (cap_mult if e == armband else 1) if e in playing else 0
        out.append({"id": e, "slot": x["position"], "mult": mult,
                    "c": x["is_captain"], "vc": x["is_vice_captain"], "played": e in playing})
    return out


def fetch_manager(mid, gws, latest, season_dir, live_by_gw, total_players):
    entry = get(f"entry/{mid}/")
    hist = get(f"entry/{mid}/history/")
    cache_dir = os.path.join(season_dir, "managers", str(mid))
    weeks = []
    for h in hist.get("current", []):
        gw = h["event"]
        if gw not in gws:
            continue
        try:
            p = gw_picks(mid, gw, cache_dir, refresh=(gw == latest))
        except Exception as e:
            print(f"  picks unavailable for {mid} GW{gw}: {e}")
            p = None
        squad = score_picks(p, live_by_gw.get(gw, {})) if p else []
        live = live_by_gw.get(gw, {})
        calc = sum(int(live.get(str(s["id"]), {}).get("total_points", 0)) * s["mult"] for s in squad)
        if squad and calc != h["points"]:
            print(f"  note: {mid} GW{gw} squad sum {calc} != official {h['points']}")
        weeks.append({
            "gw": gw, "pts": h["points"], "total": h["total_points"],
            "rank": h.get("rank"), "overall": h.get("overall_rank"),
            "bench": h.get("points_on_bench", 0), "transfers": h.get("event_transfers", 0),
            "hit": h.get("event_transfers_cost", 0), "value": h.get("value", 0) / 10,
            "bank": h.get("bank", 0) / 10, "chip": (p or {}).get("active_chip"), "squad": squad,
        })
    rank = entry.get("summary_overall_rank")
    return {
        "id": mid,
        "team": entry.get("name"),
        "manager": f'{entry.get("player_first_name", "")} {entry.get("player_last_name", "")}'.strip(),
        "points": entry.get("summary_overall_points"),
        "rank": rank,
        "top_pct": round(rank / total_players * 100, 2) if rank and total_players else None,
        "history": weeks,
        "chips": [{"name": c["name"], "gw": c["event"]} for c in hist.get("chips", [])],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", type=int, help="add a manager id to managers.json")
    args = ap.parse_args()
    ids = load_ids()
    if args.add and args.add not in ids:
        get(f"entry/{args.add}/")  # fail early on a bad id
        ids.append(args.add)
        save_ids(ids)
        print(f"Added manager {args.add}")

    boot = get("bootstrap-static/")
    season_dir = os.path.join(ROOT, "data", season_of(boot))
    gws = finished_gws(boot)
    latest = gws[-1] if gws else None
    live_by_gw = {}
    for gw in gws:
        d = read_json(os.path.join(season_dir, "gw", f"{gw}.json"))
        if d:
            live_by_gw[gw] = d["players"]
    out = []
    for mid in ids:
        try:
            out.append(fetch_manager(mid, gws, latest, season_dir, live_by_gw, boot.get("total_players")))
            print(f"Manager {mid}: ok")
        except Exception as e:
            print(f"Manager {mid}: failed ({e})")
    write_json(os.path.join(ROOT, "docs", "data", "managers.json"), {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "default": ids[0] if ids else None,
        "total_players": boot.get("total_players"),
        "managers": out,
    })


if __name__ == "__main__":
    main()
