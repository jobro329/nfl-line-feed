"""Pull one snapshot of NFL main-market odds and flatten it to rows."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import requests

from . import config
from .teams import abbr

COLUMNS = ["snapshot_utc", "event_id", "commence_time", "away", "home", "book",
           "market", "outcome", "point", "price", "book_update"]


def credits_left(key: str) -> float | None:
    """The /sports endpoint is free and returns the quota headers."""
    try:
        r = requests.get(f"{config.API_BASE}/sports", params={"apiKey": key}, timeout=30)
        v = r.headers.get("x-requests-remaining")
        return float(v) if v is not None else None
    except requests.RequestException:
        return None


def pull(key: str, retries: int = 3) -> tuple[list, dict]:
    """Call /odds once. Returns (events json, quota headers)."""
    url = f"{config.API_BASE}/sports/{config.SPORT}/odds"
    now = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "apiKey": key,
        "bookmakers": ",".join(config.BOOKMAKERS),
        "markets": ",".join(config.MARKETS),
        "oddsFormat": "american",
        "dateFormat": "iso",
        # Only games that haven't kicked off, so in-play odds never pollute the closing line.
        "commenceTimeFrom": now,
    }
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                raise SystemExit(f"Odds API refused the key ({r.status_code}): {r.text[:200]}")
            r.raise_for_status()
            quota = {k: r.headers.get(k) for k in
                     ("x-requests-remaining", "x-requests-used", "x-requests-last")}
            return r.json(), quota
        except requests.RequestException as e:  # network blips
            last = e
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"Odds API request failed after {retries} tries: {last}")


def flatten(events: list, snapshot_utc: str) -> pd.DataFrame:
    rows = []
    for ev in events:
        home, away = ev["home_team"], ev["away_team"]
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for oc in mk.get("outcomes", []):
                    name = oc["name"]
                    outcome = abbr(name) if name not in ("Over", "Under") else name
                    rows.append({
                        "snapshot_utc": snapshot_utc,
                        "event_id": ev["id"],
                        "commence_time": ev["commence_time"],
                        "away": abbr(away),
                        "home": abbr(home),
                        "book": bk["key"],
                        "market": mk["key"],
                        "outcome": outcome,
                        "point": oc.get("point"),
                        "price": oc["price"],
                        "book_update": mk.get("last_update", bk.get("last_update")),
                    })
    return pd.DataFrame(rows, columns=COLUMNS)
