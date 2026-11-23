"""Turn raw snapshot rows into one consensus line per game, and track it over time."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config


# ----------------------------------------------------------------- price helpers
def implied(american) -> np.ndarray:
    a = np.asarray(american, dtype=float)
    return np.where(a > 0, 100.0 / (a + 100.0), -a / (-a + 100.0))


def to_american(p: float) -> float:
    if p is None or not np.isfinite(p) or p <= 0 or p >= 1:
        return np.nan
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def decimal(american: float) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def fmt_spread(home: str, away: str, home_spread: float) -> str:
    """Book convention (negative = home favoured) -> 'DET -3.5'."""
    if home_spread is None or not np.isfinite(home_spread):
        return ""
    if home_spread == 0:
        return "PK"
    fav = home if home_spread < 0 else away
    return f"{fav} -{abs(home_spread):g}"


def season_of(ts: pd.Timestamp) -> int:
    return ts.year if ts.month >= 3 else ts.year - 1


# ----------------------------------------------------------------- per snapshot
def _two_way(df: pd.DataFrame, side_a: str, side_b: str) -> pd.DataFrame:
    """Per event and book: point of side A and no-vig probability of side A."""
    a = df[df.outcome == side_a][["event_id", "book", "point", "price"]]
    b = df[df.outcome == side_b][["event_id", "book", "price"]]
    m = a.merge(b, on=["event_id", "book"], suffixes=("_a", "_b"))
    pa, pb = implied(m.price_a), implied(m.price_b)
    m["nv_a"] = pa / (pa + pb)
    return m


def consensus(snap: pd.DataFrame) -> pd.DataFrame:
    """One row per game for a single snapshot: median line across books, no-vig
    probabilities, the sharp book's line, and the best price on each side."""
    out = []
    for eid, g in snap.groupby("event_id"):
        home, away = g.home.iloc[0], g.away.iloc[0]
        row = {"event_id": eid, "snapshot_utc": g.snapshot_utc.iloc[0],
               "commence_time": g.commence_time.iloc[0], "away": away, "home": home,
               "n_books": g.book.nunique()}

        sp = g[g.market == "spreads"]
        s = _two_way(sp, home, away)
        if len(s):
            row["home_spread"] = float(np.median(s.point))
            at_cons = s[np.isclose(s.point, row["home_spread"])]
            row["home_cover_nv"] = float((at_cons if len(at_cons) else s).nv_a.median())
            sh = s[s.book == config.SHARP_BOOK]
            row["sharp_home_spread"] = float(sh.point.iloc[0]) if len(sh) else np.nan
            # best number for each side, then best price at that number
            hb = sp[sp.outcome == home].sort_values(["point", "price"], ascending=False).iloc[0]
            ab = sp[sp.outcome == away].sort_values(["point", "price"], ascending=False).iloc[0]
            row["best_home_spread"] = f"{hb.point:+g} {hb.price:+.0f} {hb.book}"
            row["best_away_spread"] = f"{ab.point:+g} {ab.price:+.0f} {ab.book}"

        tt = g[g.market == "totals"]
        t = _two_way(tt, "Over", "Under")
        if len(t):
            row["total"] = float(np.median(t.point))
            at_cons = t[np.isclose(t.point, row["total"])]
            row["over_nv"] = float((at_cons if len(at_cons) else t).nv_a.median())
            sh = t[t.book == config.SHARP_BOOK]
            row["sharp_total"] = float(sh.point.iloc[0]) if len(sh) else np.nan
            ob = tt[tt.outcome == "Over"].sort_values(["point", "price"], ascending=[True, False]).iloc[0]
            ub = tt[tt.outcome == "Under"].sort_values(["point", "price"], ascending=[False, False]).iloc[0]
            row["best_over"] = f"o{ob.point:g} {ob.price:+.0f} {ob.book}"
            row["best_under"] = f"u{ub.point:g} {ub.price:+.0f} {ub.book}"

        ml = g[g.market == "h2h"]
        h = _two_way(ml, home, away)
        if len(h):
            row["home_ml_nv"] = float(h.nv_a.median())
            sh = h[h.book == config.SHARP_BOOK]
            row["sharp_home_ml_nv"] = float(sh.nv_a.iloc[0]) if len(sh) else np.nan
            hb = ml[ml.outcome == home].sort_values("price", ascending=False).iloc[0]
            ab = ml[ml.outcome == away].sort_values("price", ascending=False).iloc[0]
            row["best_home_ml"] = f"{hb.price:+.0f} {hb.book}"
            row["best_away_ml"] = f"{ab.price:+.0f} {ab.book}"
        out.append(row)
    return pd.DataFrame(out)


# ----------------------------------------------------------------- storage
def snapshot_path(snapshot_utc: str) -> Path:
    ts = pd.Timestamp(snapshot_utc)
    return config.SNAPSHOT_DIR / str(season_of(ts)) / f"{ts.strftime('%Y-%m-%dT%H%MZ')}.csv.gz"


def load_history(season: int) -> pd.DataFrame:
    """Consensus rows for every snapshot this season (cached per snapshot)."""
    d = config.SNAPSHOT_DIR / str(season)
    files = sorted(d.glob("*.csv.gz")) if d.exists() else []
    frames = []
    for f in files:
        raw = pd.read_csv(f)
        if len(raw):
            frames.append(consensus(raw))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------- movement
def _crossed(a: float, b: float, keys) -> str:
    if not (np.isfinite(a) and np.isfinite(b)) or a == b:
        return ""
    lo, hi = min(a, b), max(a, b)
    hits = [k for k in keys for v in (k, -k) if lo <= v <= hi]
    return ",".join(str(k) for k in sorted(set(hits)))


def movement(hist: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (board for upcoming games, open/close table for every game seen)."""
    if hist.empty:
        return pd.DataFrame(), pd.DataFrame()
    hist = hist.sort_values("snapshot_utc")
    latest_snap = hist.snapshot_utc.max()
    rows = []
    for eid, g in hist.groupby("event_id"):
        o, c = g.iloc[0], g.iloc[-1]
        p = g.iloc[-2] if len(g) > 1 else g.iloc[-1]
        r = {
            "event_id": eid, "game": f"{c.away}@{c.home}", "away": c.away, "home": c.home,
            "commence_time": c.commence_time, "first_seen_utc": o.snapshot_utc,
            "last_seen_utc": c.snapshot_utc, "snapshots": len(g),
            # kickoff still ahead of the newest pull
            "upcoming": pd.Timestamp(c.commence_time) > pd.Timestamp(latest_snap),
        }
        for col in ("home_spread", "total", "home_ml_nv", "home_cover_nv", "over_nv"):
            r[f"open_{col}"] = o.get(col, np.nan)
            r[f"prev_{col}"] = p.get(col, np.nan)
            r[f"now_{col}"] = c.get(col, np.nan)
        for col in ("sharp_home_spread", "sharp_total", "sharp_home_ml_nv", "n_books",
                    "best_home_spread", "best_away_spread", "best_over", "best_under",
                    "best_home_ml", "best_away_ml"):
            r[col] = c.get(col, np.nan)
        rows.append(r)
    t = pd.DataFrame(rows)

    t["spread_move"] = t.now_home_spread - t.open_home_spread      # negative = toward home
    t["spread_move_since_last"] = t.now_home_spread - t.prev_home_spread
    t["total_move"] = t.now_total - t.open_total
    t["total_move_since_last"] = t.now_total - t.prev_total
    t["home_ml_move"] = t.now_home_ml_nv - t.open_home_ml_nv
    t["spread_keys_crossed"] = [_crossed(a, b, config.KEY_SPREADS)
                                for a, b in zip(t.open_home_spread, t.now_home_spread)]
    t["total_keys_crossed"] = [_crossed(a, b, config.KEY_TOTALS)
                               for a, b in zip(t.open_total, t.now_total)]
    t["open_line"] = [fmt_spread(h, a, s) for h, a, s in zip(t.home, t.away, t.open_home_spread)]
    t["now_line"] = [fmt_spread(h, a, s) for h, a, s in zip(t.home, t.away, t.now_home_spread)]
    t["sharp_line"] = [fmt_spread(h, a, s) for h, a, s in zip(t.home, t.away, t.sharp_home_spread)]
    t["moved_toward"] = np.where(t.spread_move < 0, t.home, np.where(t.spread_move > 0, t.away, ""))

    flags = []
    for _, r in t.iterrows():
        f = []
        if abs(r.spread_move) >= config.SPREAD_MOVE_FLAG:
            f.append(f"spread {r.spread_move:+g} toward {r.moved_toward}")
        if r.spread_keys_crossed:
            f.append(f"crossed {r.spread_keys_crossed}")
        if abs(r.total_move) >= config.TOTAL_MOVE_FLAG:
            f.append(f"total {r.total_move:+g}")
        if abs(r.home_ml_move) >= config.ML_PROB_MOVE_FLAG:
            f.append(f"ML {r.home_ml_move * 100:+.0f}pts {r.home}")
        if np.isfinite(r.sharp_home_spread) and np.isfinite(r.now_home_spread) \
                and abs(r.sharp_home_spread - r.now_home_spread) >= 1:
            f.append(f"Pinnacle off market ({r.sharp_line})")
        if abs(r.spread_move_since_last) >= 1 or abs(r.total_move_since_last) >= 1.5:
            f.append("big move since last pull")
        flags.append("; ".join(f))
    t["alerts"] = flags
    t = t.sort_values("commence_time").reset_index(drop=True)

    board = t[t.upcoming].drop(columns=["upcoming"]).reset_index(drop=True)
    closes = t.drop(columns=["upcoming"]).rename(columns=lambda c: c.replace("now_", "close_"))
    # a game's "close" only means something once it has kicked off
    closes = closes[~t.upcoming.values].reset_index(drop=True)
    return board, closes
