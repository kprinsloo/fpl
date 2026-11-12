"""Tiny helper for the public FPL API (stdlib only).

Set FPL_FIXTURES=<dir> to read responses from local JSON files instead of
the network (used by tests/make_fixtures.py). A request for
"event/3/live/" is read from "<dir>/event_3_live.json".
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://fantasy.premierleague.com/api/"
UA = "Mozilla/5.0 (fpl-tracker; GitHub Actions)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get(path, retries=3):
    fixtures = os.environ.get("FPL_FIXTURES")
    if fixtures:
        name = path.strip("/").replace("/", "_") + ".json"
        with open(os.path.join(fixtures, name), encoding="utf-8") as f:
            return json.load(f)
    url = BASE + path
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries - 1:
                raise RuntimeError(f"FPL API request failed: {url}: {e}")
            time.sleep(2 * (attempt + 1))


def season_of(bootstrap):
    """'2026-27' style season label from the first gameweek deadline."""
    first = bootstrap["events"][0]["deadline_time"][:4]
    y = int(first)
    return f"{y}-{str(y + 1)[2:]}"


def finished_gws(bootstrap):
    return [e["id"] for e in bootstrap["events"] if e.get("finished") and e.get("data_checked", True)]


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
