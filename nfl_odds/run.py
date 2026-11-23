"""One feed run: pull odds, save the snapshot, rebuild movement tables.

    python -m nfl_odds.run                # live pull (needs ODDS_API_KEY)
    python -m nfl_odds.run --rebuild      # rebuild tables from saved snapshots, no API call
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from . import config, fetch, lines, report


def _last_quota() -> dict:
    """Quota from the previous run, so --rebuild and skipped runs still report it."""
    p = config.LATEST_DIR / "run_info.json"
    if p.exists():
        try:
            return json.loads(p.read_text()).get("quota", {})
        except json.JSONDecodeError:
            pass
    return {}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="skip the API call")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    snapshot_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    quota = _last_quota()
    pulled = 0

    if not args.rebuild:
        key = config.api_key()
        rem = fetch.credits_left(key)
        if rem is not None and rem < config.MIN_CREDITS_LEFT:
            print(f"Only {rem:g} credits left on the plan; skipping the pull.")
            quota["x-requests-remaining"] = f"{rem:g}"
        else:
            events, quota = fetch.pull(key)
            rows = fetch.flatten(events, snapshot_utc)
            pulled = len(events)
            if len(rows):
                path = lines.snapshot_path(snapshot_utc)
                path.parent.mkdir(parents=True, exist_ok=True)
                rows.to_csv(path, index=False, compression="gzip")
                print(f"Saved {len(rows)} prices for {pulled} games -> {path}")
            else:
                print("No games returned (off-season or between slates). Nothing saved.")
            print("Credits:", quota)

    season = lines.season_of(pd.Timestamp(now))
    hist = lines.load_history(season)
    board, closes = lines.movement(hist)
    latest_snap = hist.snapshot_utc.max() if len(hist) else snapshot_utc

    out = config.LATEST_DIR
    out.mkdir(parents=True, exist_ok=True)
    num = board.select_dtypes("number").columns
    board.assign(**{c: board[c].round(4) for c in num}).to_csv(out / "line_movement.csv", index=False)
    if len(closes):
        num = closes.select_dtypes("number").columns
        closes.assign(**{c: closes[c].round(4) for c in num}).to_csv(out / "closing_lines.csv", index=False)
    (out / "summary.md").write_text(report.summary(board, latest_snap, quota))
    (out / "run_info.json").write_text(json.dumps({
        "generated_utc": snapshot_utc, "latest_snapshot_utc": latest_snap, "season": season,
        "games_in_pull": pulled, "upcoming_games": len(board), "games_closed": len(closes),
        "quota": quota, "bookmakers": config.BOOKMAKERS, "markets": config.MARKETS,
    }, indent=2))
    print(f"Board: {len(board)} upcoming games, {len(closes)} closed games on file.")


if __name__ == "__main__":
    main()
