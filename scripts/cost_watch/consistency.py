"""
Multi-source consistency flag and statistics utilities for cost-watch.

Pure-logic module (no I/O). Imported by scrapers and merger.

Flag thresholds (deviation = (max - min) / mean * 100):
    consistent: dev < 2%
    warning   : 2% <= dev < 5%
    divergent : dev >= 5%
    single    : only 1 source available
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional


WARNING_THRESHOLD_PCT = 2.0
DIVERGENT_THRESHOLD_PCT = 5.0


@dataclass(frozen=True)
class ConsistencyResult:
    flag: str
    sources_count: int
    value_min: Optional[float]
    value_max: Optional[float]
    max_deviation_pct: Optional[float]


def evaluate_consistency(values: Iterable[Optional[float]]) -> ConsistencyResult:
    nums = [float(v) for v in values if v is not None]
    n = len(nums)
    if n == 0:
        return ConsistencyResult("single", 0, None, None, None)
    if n == 1:
        return ConsistencyResult("single", 1, nums[0], nums[0], 0.0)

    vmin, vmax = min(nums), max(nums)
    mean = sum(nums) / n
    deviation = 0.0 if mean == 0 else (vmax - vmin) / mean * 100.0

    if deviation < WARNING_THRESHOLD_PCT:
        flag = "consistent"
    elif deviation < DIVERGENT_THRESHOLD_PCT:
        flag = "warning"
    else:
        flag = "divergent"

    return ConsistencyResult(flag, n, vmin, vmax, round(deviation, 2))


def _parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s[:10])


def calc_comparisons(
    history: list[dict],
    current_date: Optional[str] = None,
) -> dict:
    """
    history: [{"date": "YYYY-MM-DD", "value": float}, ...] (any order)
    current_date: anchor date; defaults to latest history entry.

    Returns wow / mom / yoy percentage changes.
    "Nearest prior" lookup is used (latest entry on or before target),
    so weekly-cadence sources still produce sensible week-over-week values.
    """
    if not history:
        return {"wow_pct": None, "mom_pct": None, "yoy_pct": None}

    sorted_h = sorted(history, key=lambda h: h["date"])
    if current_date is None:
        current = sorted_h[-1]
    else:
        match = [h for h in sorted_h if h["date"] == current_date]
        current = match[0] if match else sorted_h[-1]

    cur_dt = _parse_date(current["date"])
    cur_val = float(current["value"])

    def find_prior(days: int) -> Optional[float]:
        target = cur_dt - timedelta(days=days)
        prior = [h for h in sorted_h if _parse_date(h["date"]) <= target]
        if not prior:
            return None
        return float(prior[-1]["value"])

    def pct_change(prev: Optional[float]) -> Optional[float]:
        if prev is None or prev == 0:
            return None
        return round((cur_val - prev) / prev * 100.0, 2)

    return {
        "wow_pct": pct_change(find_prior(7)),
        "mom_pct": pct_change(find_prior(30)),
        "yoy_pct": pct_change(find_prior(365)),
    }
