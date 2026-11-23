"""Settings for the NFL line feed. Everything here can be changed without touching the code."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"

# Main markets only. Each market costs 1 credit per pull.
MARKETS = ["h2h", "spreads", "totals"]

# Up to 10 bookmakers count as ONE region for billing, and they can come from any
# region. Pinnacle (eu) is the sharp reference; the rest are the main US books.
# Caesars (williamhill_us) and Fanatics are paid-plan only, so they're left out.
BOOKMAKERS = [
    "pinnacle",
    "draftkings",
    "fanduel",
    "betmgm",
    "betrivers",
    "espnbet",
    "betonlineag",
    "lowvig",
    "bovada",
]
SHARP_BOOK = "pinnacle"

# Free plan is 500 credits a month. Stop pulling if we drop below this.
MIN_CREDITS_LEFT = int(os.getenv("ODDS_MIN_CREDITS_LEFT", "6"))

DATA_DIR = ROOT / "data" / "nfl" / "odds"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
LATEST_DIR = DATA_DIR / "latest"
BETS_FILE = ROOT / "data" / "nfl" / "bets" / "bets.csv"

# Flags in the movement table
KEY_SPREADS = (3, 7, 10)
KEY_TOTALS = (37, 41, 44, 47, 51)
SPREAD_MOVE_FLAG = 1.0      # points
TOTAL_MOVE_FLAG = 1.5       # points
ML_PROB_MOVE_FLAG = 0.03    # 3 percentage points of no-vig win probability


def api_key() -> str:
    key = os.getenv("ODDS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ODDS_API_KEY is not set. Add it as a GitHub secret (see docs/NFL_ODDS_FEED.md).")
    return key
