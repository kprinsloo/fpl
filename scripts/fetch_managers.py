"""Fetch history and picks for every FPL manager listed in managers.json.

Usage: python scripts/fetch_managers.py [--add MANAGER_ID]
Writes docs/data/managers.json.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fpl_api import ROOT, get, read_json, write_json  # noqa: E402

LIST_FILE = os.path.join(ROOT, "managers.json")


def load_ids():
    return [int(i) for i in read_json(LIST_FILE, {"managers": []})["managers"]]


def save_ids(ids):
    with open(LIST_FILE, "w", encoding="utf-8") as f:
        json.dump({"managers": ids}, f, indent=2)
        f.write("\n")


def fetch_manager(mid, current_gw):
    entry = get(f"entry/{mid}/")
    hist = get(f"entry/{mid}/history/")
    picks = None
    gw = entry.get("current_event") or current_gw
    if gw:
        try:
            p = get(f"entry/{mid}/event/{gw}/picks/")
            picks = {"gw": gw, "chip": p.get("active_chip"), "picks": [
                {"id": x["element"], "pos": x["position"], "mult": x["multiplier"],
                 "c": x["is_captain"], "vc": x["is_vice_captain"]} for x in p["picks"]]}
        except Exception as e:  # picks are optional; history still useful
            print(f"  picks unavailable for {mid} GW{gw}: {e}")
    return {
        "id": mid,
        "team": entry.get("name"),
        "manager": f'{entry.get("player_first_name", "")} {entry.get("player_last_name", "")}'.strip(),
        "points": entry.get("summary_overall_points"),
        "rank": entry.get("summary_overall_rank"),
        "history": [{
            "gw": h["event"], "pts": h["points"], "total": h["total_points"],
            "rank": h.get("rank"), "overall": h.get("overall_rank"),
            "bench": h.get("points_on_bench", 0), "transfers": h.get("event_transfers", 0),
            "hit": h.get("event_transfers_cost", 0), "value": h.get("value", 0) / 10,
            "bank": h.get("bank", 0) / 10,
        } for h in hist.get("current", [])],
        "chips": [{"name": c["name"], "gw": c["event"]} for c in hist.get("chips", [])],
        "picks": picks,
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
    current = next((e["id"] for e in boot["events"] if e.get("is_current")), None)
    out = []
    for mid in ids:
        try:
            out.append(fetch_manager(mid, current))
            print(f"Manager {mid}: ok")
        except Exception as e:
            print(f"Manager {mid}: failed ({e})")
    write_json(os.path.join(ROOT, "docs", "data", "managers.json"), {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "default": ids[0] if ids else None,
        "managers": out,
    })


if __name__ == "__main__":
    main()
