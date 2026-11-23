"""Grade a bet log against closing lines from the feed.

    python -m nfl_odds.clv path/to/bets.csv

bets.csv columns:
    placed_date  YYYY-MM-DD (used to pick the right meeting if teams play twice)
    game         AWAY@HOME, nflverse codes, e.g. TB@DET
    market       spread | total | ml
    pick         team code for spread/ml, or over/under
    line         the number you got from your side: +3.5, -9.5, 44.5 (blank for ml)
    price        American odds you got, e.g. -111
    book         optional
    notes        optional

CLV points  = how many points better your number was than the closing consensus.
EV at close = your price against the closing no-vig probability. Only shown when your
              number matches the closing number (otherwise the points column tells the story).
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import config
from .lines import decimal


def grade(bets: pd.DataFrame, closes: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, b in bets.iterrows():
        away, home = str(b.game).upper().split("@")
        cand = closes[(closes.away == away) & (closes.home == home)]
        if "placed_date" in b and pd.notna(b.placed_date):
            placed = pd.Timestamp(b.placed_date).tz_localize("UTC")
            cand = cand[pd.to_datetime(cand.commence_time, utc=True) >= placed]
        r = b.to_dict()
        if cand.empty:
            r.update(close_line=np.nan, clv_points=np.nan, close_prob=np.nan, ev_at_close=np.nan,
                     status="no closing line in feed")
            out.append(r)
            continue
        c = cand.sort_values("commence_time").iloc[0]
        mkt, pick = str(b.market).lower(), str(b.pick).upper()
        line = float(b.line) if pd.notna(b.get("line")) else np.nan
        close_line, close_prob = np.nan, np.nan

        if mkt == "spread":
            is_home = pick == home
            close_line = c.close_home_spread if is_home else -c.close_home_spread
            close_prob = c.close_home_cover_nv if is_home else 1 - c.close_home_cover_nv
            clv = line - close_line
        elif mkt == "total":
            close_line = c.close_total
            over = pick == "OVER"
            close_prob = c.close_over_nv if over else 1 - c.close_over_nv
            clv = (close_line - line) if over else (line - close_line)
        elif mkt == "ml":
            close_prob = c.close_home_ml_nv if pick == home else 1 - c.close_home_ml_nv
            clv = np.nan
            line = close_line = np.nan
        else:
            raise ValueError(f"unknown market {b.market!r}")

        same_number = mkt == "ml" or (np.isfinite(line) and np.isclose(line, close_line))
        ev = close_prob * decimal(float(b.price)) - 1 if same_number else np.nan
        r.update(close_line=close_line, clv_points=clv, close_prob=round(close_prob, 4),
                 ev_at_close=round(ev, 4) if np.isfinite(ev) else np.nan,
                 status="graded")
        out.append(r)
    return pd.DataFrame(out)


def main(argv=None) -> None:
    argv = argv or sys.argv[1:]
    path = argv[0] if argv else config.BETS_FILE
    closes_path = config.LATEST_DIR / "closing_lines.csv"
    if not closes_path.exists():
        raise SystemExit("No closing_lines.csv yet. Run the feed first.")
    g = grade(pd.read_csv(path), pd.read_csv(closes_path))
    pd.set_option("display.width", 200)
    print(g[["game", "market", "pick", "line", "price", "close_line", "clv_points",
             "close_prob", "ev_at_close", "status"]].to_string(index=False))
    graded = g[g.status == "graded"]
    if len(graded):
        print(f"\nAvg CLV points: {graded.clv_points.mean():+.2f} "
              f"({graded.clv_points.notna().sum()} spread/total bets) · "
              f"beat the close on {(graded.clv_points > 0).sum()} of {graded.clv_points.notna().sum()}")


if __name__ == "__main__":
    main()
