"""Expected points for the next 3 gameweeks ("Option 2" model).

For each player and fixture the expected points are built from the parts of
the 2026/27 scoring rules (same as 2025/26):

  appearance   2 for 60+ min, 1 for under 60
  goals        GK 10, DEF 6, MID 5, FWD 4  x  xG per 90, adjusted for opponent
  assists      3  x  xA per 90, adjusted for opponent
  clean sheet  GK/DEF 4, MID 1  x  P(0 conceded), needs 60+ min
  conceded     GK/DEF -1 per 2 goals conceded
  saves        GK +1 per 3 saves
  def. contr.  +2 when DEF reach 10+ CBIT, MID/FWD 12+ CBIRT (historic hit rate)
  bonus        average bonus per appearance
  cards        yellow -1, red -3 (rate per 90)

Minutes come from the last 6 gameweeks and the injury/availability flag.
Double gameweeks add both fixtures; blanks give 0.

Reads data/<season>/ (written by fetch_fpl.py), writes docs/data/predictions.json.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fpl_api import ROOT, finished_gws, read_json, season_of, write_json  # noqa: E402

GOAL_PTS = {1: 10, 2: 6, 3: 5, 4: 4}
CS_PTS = {1: 4, 2: 4, 3: 1, 4: 0}
DC_THRESHOLD = {1: None, 2: 10, 3: 12, 4: 12}
HOME_ATTACK = 1.08
AWAY_ATTACK = 0.92
RECENT = 6
HORIZON = 3


def shrink(ratio, weight=0.5):
    """Pull a team ratio toward 1 so a few games don't swing it too far."""
    return 1 + weight * (ratio - 1)


def team_rates(fixtures):
    scored, conceded, games = {}, {}, {}
    for f in fixtures:
        if not f.get("finished") or f.get("team_h_score") is None:
            continue
        h, a = f["team_h"], f["team_a"]
        hs, as_ = f["team_h_score"], f["team_a_score"]
        for t, gf, ga in ((h, hs, as_), (a, as_, hs)):
            scored[t] = scored.get(t, 0) + gf
            conceded[t] = conceded.get(t, 0) + ga
            games[t] = games.get(t, 0) + 1
    total_games = sum(games.values())
    avg = (sum(scored.values()) / total_games) if total_games else 1.35
    rates = {}
    for t in games:
        rates[t] = {
            "att": shrink((scored[t] / games[t]) / avg) if avg else 1,
            "def": shrink((conceded[t] / games[t]) / avg) if avg else 1,
        }
    return avg, rates


def player_profile(pid, el, gw_data, gws):
    recent = gws[-RECENT:]
    apps = mins = 0
    starts60 = 0
    totals = {}
    dc_hits = dc_apps = 0
    pos = el["element_type"]
    thr = DC_THRESHOLD.get(pos)
    for gw in gws:
        s = gw_data[gw]["players"].get(pid)
        if not s or s.get("minutes", 0) <= 0:
            continue
        for k, v in s.items():
            totals[k] = totals.get(k, 0.0) + v
        if thr and s.get("minutes", 0) >= 60:
            dc_apps += 1
            if s.get("defensive_contribution", 0) >= thr:
                dc_hits += 1
    recent_apps = [gw_data[g]["players"].get(pid, {}).get("minutes", 0) for g in recent]
    played = [m for m in recent_apps if m > 0]
    apps = len(played)
    mins = sum(played)
    starts60 = sum(1 for m in played if m >= 60)

    p_play = apps / len(recent) if recent else 0
    chance = el.get("chance_of_playing_next_round")
    if chance is not None:
        p_play = min(p_play, chance / 100) if p_play else chance / 100 * 0.5
    elif el.get("status") in ("i", "s", "u", "n"):
        p_play = 0
    p60 = starts60 / apps if apps else 0
    min_share = (mins / apps / 90) if apps else 0

    season_mins = totals.get("minutes", 0)
    season_apps = sum(1 for gw in gws if gw_data[gw]["players"].get(pid, {}).get("minutes", 0) > 0)
    per90 = lambda k: (totals.get(k, 0) / season_mins * 90) if season_mins >= 90 else 0  # noqa: E731
    return {
        "pos": pos, "p_play": p_play, "p60": p60, "min_share": min_share,
        "xg90": per90("expected_goals"), "xa90": per90("expected_assists"),
        "saves90": per90("saves"), "y90": per90("yellow_cards"), "r90": per90("red_cards"),
        "bonus_app": (totals.get("bonus", 0) / season_apps) if season_apps else 0,
        "dc_rate": (dc_hits / dc_apps) if dc_apps else 0,
    }


def fixture_xp(p, team, opp, home, avg, rates):
    if p["p_play"] <= 0:
        return 0.0
    tr = rates.get(team, {"att": 1, "def": 1})
    orr = rates.get(opp, {"att": 1, "def": 1})
    att_f = orr["def"] * (HOME_ATTACK if home else AWAY_ATTACK)
    lam_conceded = avg * tr["def"] * orr["att"] * (AWAY_ATTACK if home else HOME_ATTACK)
    pos = p["pos"]
    play, p60, share = p["p_play"], p["p60"], p["min_share"]

    xp = play * (p60 * 2 + (1 - p60) * 1)
    xp += play * share * att_f * (p["xg90"] * GOAL_PTS[pos] + p["xa90"] * 3)
    xp += play * p60 * CS_PTS[pos] * math.exp(-lam_conceded)
    if pos in (1, 2):
        xp -= play * share * lam_conceded / 2
    if pos == 1:
        xp += play * share * p["saves90"] / 3
    xp += play * p60 * p["dc_rate"] * 2
    xp += play * p["bonus_app"]
    xp -= play * share * (p["y90"] + 3 * p["r90"])
    return xp


def main():
    boot = None
    data_dir = os.path.join(ROOT, "data")
    seasons = sorted(d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d)))
    if not seasons:
        sys.exit("No season data yet; run fetch_fpl.py first")
    season_dir = os.path.join(data_dir, seasons[-1])
    boot = read_json(os.path.join(season_dir, "bootstrap.json"))
    fixtures = read_json(os.path.join(season_dir, "fixtures.json"), [])
    gws = finished_gws(boot)
    gw_data = {gw: read_json(os.path.join(season_dir, "gw", f"{gw}.json")) for gw in gws}
    gw_data = {g: d for g, d in gw_data.items() if d}
    gws = [g for g in gws if g in gw_data]

    upcoming = [e["id"] for e in boot["events"] if not e.get("finished")][:HORIZON]
    avg, rates = team_rates(fixtures)
    by_gw = {gw: [f for f in fixtures if f.get("event") == gw] for gw in upcoming}

    out = {}
    for el in boot["elements"]:
        pid = str(el["id"])
        prof = player_profile(pid, el, gw_data, gws)
        row = []
        for gw in upcoming:
            total = 0.0
            for f in by_gw[gw]:
                if f["team_h"] == el["team"]:
                    total += fixture_xp(prof, el["team"], f["team_a"], True, avg, rates)
                elif f["team_a"] == el["team"]:
                    total += fixture_xp(prof, el["team"], f["team_h"], False, avg, rates)
            row.append(round(total, 1))
        out[pid] = row

    opponents = {}
    for gw in upcoming:
        for f in by_gw[gw]:
            opponents.setdefault(str(f["team_h"]), {}).setdefault(str(gw), []).append([f["team_a"], "H"])
            opponents.setdefault(str(f["team_a"]), {}).setdefault(str(gw), []).append([f["team_h"], "A"])

    write_json(os.path.join(ROOT, "docs", "data", "predictions.json"), {
        "season": season_of(boot), "gws": upcoming, "model": "option-2-xpts",
        "players": out, "fixtures": opponents,
    })
    print(f"Predictions for GW{upcoming} written for {len(out)} players")


if __name__ == "__main__":
    main()
