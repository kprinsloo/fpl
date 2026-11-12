"""Generate fake FPL API responses for offline testing.

  python tests/make_fixtures.py /tmp/fpl-fixtures
  FPL_FIXTURES=/tmp/fpl-fixtures python scripts/fetch_fpl.py
  FPL_FIXTURES=/tmp/fpl-fixtures python scripts/fetch_managers.py
  python scripts/predict.py

The numbers are random; only the shape matches the real API.
"""
import json
import os
import random
import sys

random.seed(7)
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fpl-fixtures"
FINISHED = 10
TEAMS = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Burnley", "Chelsea",
         "Crystal Palace", "Everton", "Fulham", "Leeds", "Liverpool", "Man City", "Man Utd",
         "Newcastle", "Nott'm Forest", "Sunderland", "Spurs", "West Ham", "Wolves"]


def dump(name, obj):
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump(obj, f)


def main():
    os.makedirs(OUT, exist_ok=True)
    teams = [{"id": i + 1, "name": n, "short_name": n[:3].upper()} for i, n in enumerate(TEAMS)]
    events = [{"id": g, "name": f"Gameweek {g}", "deadline_time": f"2026-08-{(g % 28) + 1:02d}T10:00:00Z",
               "finished": g <= FINISHED, "data_checked": g <= FINISHED,
               "is_current": g == FINISHED, "is_next": g == FINISHED + 1,
               "average_entry_score": random.randint(40, 65) if g <= FINISHED else 0,
               "highest_score": random.randint(110, 160) if g <= FINISHED else None} for g in range(1, 39)]
    elements = []
    pid = 1
    for t in teams:
        for pos, n in ((1, 2), (2, 5), (3, 5), (4, 3)):
            for k in range(n):
                elements.append({
                    "id": pid, "web_name": f"{t['short_name']}{pos}{k}", "first_name": "Test",
                    "second_name": f"Player{pid}", "team": t["id"], "element_type": pos,
                    "now_cost": random.randint(40, 140), "total_points": 0,
                    "form": f"{random.uniform(0, 8):.1f}", "selected_by_percent": f"{random.uniform(0, 40):.1f}",
                    "status": random.choice("aaaaaaad"), "chance_of_playing_next_round": None, "news": "",
                    "cost_change_start": random.randint(-3, 8), "transfers_in_event": random.randint(0, 90000),
                    "transfers_out_event": random.randint(0, 90000),
                })
                pid += 1
    fixtures = []
    fid = 1
    for g in range(1, 39):
        order = random.sample(range(1, 21), 20)
        for i in range(0, 20, 2):
            fin = g <= FINISHED
            fixtures.append({"id": fid, "event": g, "team_h": order[i], "team_a": order[i + 1],
                             "finished": fin, "team_h_score": random.randint(0, 4) if fin else None,
                             "team_a_score": random.randint(0, 3) if fin else None})
            fid += 1
    totals = {e["id"]: 0 for e in elements}
    for g in range(1, FINISHED + 1):
        live = []
        for e in elements:
            starter = random.random() < (0.5 if e["element_type"] == 1 else 0.7)
            minutes = random.choice([90, 90, 85, 72]) if starter else random.choice([0, 0, 15, 30])
            goals = random.random() < 0.05 * e["element_type"] if minutes else False
            pts = (2 if minutes >= 60 else 1 if minutes else 0) + (5 if goals else 0) + random.randint(0, 3) * bool(minutes)
            totals[e["id"]] += pts
            live.append({"id": e["id"], "stats": {
                "minutes": minutes, "goals_scored": int(goals), "assists": int(random.random() < 0.08),
                "clean_sheets": int(minutes >= 60 and random.random() < 0.3), "goals_conceded": random.randint(0, 3) if minutes else 0,
                "own_goals": 0, "penalties_saved": 0, "penalties_missed": 0,
                "yellow_cards": int(random.random() < 0.1), "red_cards": 0,
                "saves": random.randint(0, 6) if e["element_type"] == 1 and minutes else 0,
                "bonus": random.choice([0, 0, 0, 1, 2, 3]) if minutes else 0, "bps": random.randint(0, 40),
                "influence": f"{random.uniform(0, 60):.1f}", "creativity": f"{random.uniform(0, 50):.1f}",
                "threat": f"{random.uniform(0, 60):.1f}", "ict_index": f"{random.uniform(0, 15):.1f}",
                "starts": int(starter), "expected_goals": f"{random.uniform(0, 0.6):.2f}",
                "expected_assists": f"{random.uniform(0, 0.4):.2f}",
                "expected_goal_involvements": f"{random.uniform(0, 0.9):.2f}",
                "expected_goals_conceded": f"{random.uniform(0, 2):.2f}",
                "defensive_contribution": random.randint(0, 16) if minutes else 0,
                "total_points": pts, "in_dreamteam": False}})
        dump(f"event_{g}_live", {"elements": live})
    for e in elements:
        e["total_points"] = totals[e["id"]]
    total_players = 11_000_000
    for e in elements:
        price, own = e["now_cost"] - e["cost_change_start"], random.uniform(0.1, 40)
        hist = []
        for g in range(1, FINISHED + 1):
            price += random.choice([0, 0, 0, 1, -1])
            own = max(0.05, own * random.uniform(0.85, 1.15))
            hist.append({"round": g, "value": price, "selected": int(own / 100 * total_players)})
        dump(f"element-summary_{e['id']}", {"history": hist})
    dump("bootstrap-static", {"total_players": total_players, "events": events, "teams": teams, "elements": elements,
                              "element_types": [{"id": i, "singular_name_short": s} for i, s in
                                                ((1, "GKP"), (2, "DEF"), (3, "MID"), (4, "FWD"))]})
    dump("fixtures", fixtures)

    mid = 2020911
    rank = 2_000_000
    hist, total = [], 0
    for g in range(1, FINISHED + 1):
        p = random.randint(35, 85)
        total += p
        rank = max(1000, int(rank * random.uniform(0.75, 1.2)))
        hist.append({"event": g, "points": p, "total_points": total, "rank": random.randint(1, 9_000_000),
                     "overall_rank": rank, "bank": 5, "value": 1003, "event_transfers": random.randint(0, 2),
                     "event_transfers_cost": 0, "points_on_bench": random.randint(0, 12)})
    dump(f"entry_{mid}", {"id": mid, "name": "Rockers", "player_first_name": "Kobus", "player_last_name": "",
                          "summary_overall_points": total, "summary_overall_rank": rank, "current_event": FINISHED})
    dump(f"entry_{mid}_history", {"current": hist, "chips": [{"name": "wildcard", "event": 4}]})
    squad = random.sample(elements, 15)
    for g in range(1, FINISHED + 1):
        if g in (4, 7):  # a couple of transfers
            squad[random.randint(0, 14)] = random.choice([e for e in elements if e not in squad])
        chip = {4: "wildcard", 6: "bboost", 8: "3xc"}.get(g)
        dump(f"entry_{mid}_event_{g}_picks", {"active_chip": chip, "automatic_subs": [], "picks": [
            {"element": e["id"], "position": i + 1, "multiplier": 2 if i == 0 else (1 if i < 11 else 0),
             "is_captain": i == 0, "is_vice_captain": i == 1} for i, e in enumerate(squad)]})
    print(f"Fixtures written to {OUT}")


if __name__ == "__main__":
    main()
