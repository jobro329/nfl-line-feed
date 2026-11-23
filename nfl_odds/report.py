"""Readable summary of the board (data/nfl/odds/latest/summary.md)."""
from __future__ import annotations

import numpy as np
import pandas as pd

TZ = "America/New_York"


def _et(ts) -> str:
    return pd.Timestamp(ts).tz_convert(TZ).strftime("%a %b %-d %-I:%M %p ET")


def _pct(p) -> str:
    return "" if p is None or not np.isfinite(p) else f"{p * 100:.0f}%"


def _num(x, sign=False) -> str:
    if x is None or not np.isfinite(x):
        return ""
    return f"{x:+g}" if sign else f"{x:g}"


def _moved(r) -> str:
    m = r.spread_move
    if m is None or not np.isfinite(m) or m == 0:
        return ""
    return f"{abs(m):g} toward {r.moved_toward}"


def summary(board: pd.DataFrame, snapshot_utc: str, quota: dict) -> str:
    lines = [f"# NFL line feed: {_et(snapshot_utc)}", ""]
    rem = quota.get("x-requests-remaining")
    lines.append(f"Snapshot {snapshot_utc} UTC · {len(board)} upcoming games · "
                 f"API credits left this month: {rem if rem is not None else 'n/a'}")
    lines.append("")
    lines.append("Consensus = median across books. Spreads shown as favourite and line. "
                 "ML % = no-vig home win probability. Moves are vs the first pull that saw the game.")
    lines.append("")
    if board.empty:
        lines.append("No upcoming games in this pull.")
        return "\n".join(lines) + "\n"

    flagged = board[board["alerts"].astype(bool)]
    lines.append("## Flags")
    lines.append("")
    if flagged.empty:
        lines.append("Nothing over the flag thresholds.")
    for _, r in flagged.iterrows():
        lines.append(f"- **{r.game}** ({_et(r.commence_time)}): {r['alerts']}")
    lines.append("")

    lines.append("## Board")
    lines.append("")
    lines.append("| Game | Kickoff | Spread open → now | Moved | Pinnacle | Total open → now | "
                 "Home ML open → now | Books |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for _, r in board.iterrows():
        lines.append(
            f"| {r.game} | {_et(r.commence_time)} | {r.open_line} → {r.now_line} | "
            f"{_moved(r)} | {r.sharp_line} | "
            f"{_num(r.open_total)} → {_num(r.now_total)} | "
            f"{_pct(r.open_home_ml_nv)} → {_pct(r.now_home_ml_nv)} | {int(r.n_books)} |")
    lines.append("")

    lines.append("## Best available prices")
    lines.append("")
    lines.append("| Game | Away spread | Home spread | Over | Under | Away ML | Home ML |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, r in board.iterrows():
        cells = [r.get(c, "") for c in ("best_away_spread", "best_home_spread", "best_over",
                                         "best_under", "best_away_ml", "best_home_ml")]
        cells = ["" if (isinstance(c, float) and np.isnan(c)) else c for c in cells]
        lines.append(f"| {r.game} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)
