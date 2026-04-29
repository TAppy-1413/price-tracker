"""
e燃費 (e-nenpi.com) — 実勢ガソリン価格

Fetches user-reported (実勢) fuel prices.

Data source: https://e-nenpi.com/gs/price_graph
The HTML embeds two JS variables:
  - realtime_data : current/latest value, per fuel type, with explicit labels
  - graph_data    : historical [v0, v1] pairs (semantics of v0/v1 not labelled
                    on the page; documented assumption: v1 ≈ average)

Strategy:
  - Use realtime_data for CURRENT value (it has explicit labels: レギュラー / 軽油)
  - Use graph_data values[1] for HISTORY (best-effort; flagged in JSON if uncertain)

robots.txt: /gs/ is allowed. /history/ is disallowed but we don't use it.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
COST_WATCH_DIR = SCRIPT_DIR.parent.parent / "cost_watch"
sys.path.insert(0, str(COST_WATCH_DIR))
from source_base import (  # noqa: E402
    REQUEST_TIMEOUT_SEC,
    USER_AGENT,
    HistoryPoint,
    SourceResult,
    now_utc_iso,
    polite_sleep,
    write_source_result,
)

SOURCE_NAME = "e燃費"

# (period_code, label). Dates returned vary by period:
#   1 = 1ヶ月  (daily, "M/D")
#   2 = 1年    (weekly, format TBD)
#   4 = 3年    (monthly, "YY/M")
#   6 = 5年    (monthly, "YY/M")
PERIOD_5Y = 6

# (fuel_code, label). Default fuel is regular.
FUEL_REGULAR = 1
FUEL_DIESEL = 3

REALTIME_KEY_REGULAR = "0"
REALTIME_KEY_DIESEL = "2"

URL_REALTIME = "https://e-nenpi.com/gs/price_graph"


def _fetch(url: str) -> str:
    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SEC,
    )
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def _extract_realtime(html: str) -> Optional[dict]:
    """Pull the realtime_data JSON object out of the page."""
    m = re.search(
        r"var\s+realtime_data\s*=\s*(\{.*?\});",
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _extract_graph_data(html: str) -> list[dict]:
    """Pull the graph_data JSON array."""
    m = re.search(
        r"var\s+graph_data\s*=\s*(\[.*?\]);",
        html,
        re.DOTALL,
    )
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return []


def _parse_yy_m_to_date(s: str) -> Optional[str]:
    """Parse 'YY/M' (e.g. '21/5' → '2021-05-01'). Returns ISO date for month-1st."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", s)
    if not m:
        return None
    yy, mm = int(m.group(1)), int(m.group(2))
    # YY is two-digit western year. If YY <= 50, assume 2000s+. else 1900s.
    year = 2000 + yy if yy < 70 else 1900 + yy
    if not (1 <= mm <= 12):
        return None
    return f"{year:04d}-{mm:02d}-01"


def _build_history_from_5y(html_5y: str) -> list[HistoryPoint]:
    """5-year page: monthly granularity, 'YY/M' date format."""
    arr = _extract_graph_data(html_5y)
    out: list[HistoryPoint] = []
    for entry in arr:
        d = _parse_yy_m_to_date(str(entry.get("date", "")))
        vs = entry.get("values") or []
        if d and len(vs) >= 2:
            try:
                # values[1] = lower of the two; assumed to be ~average (documented uncertainty)
                v = float(vs[1])
                out.append(HistoryPoint(date=d, value=v))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda h: h.date)
    return out


def _parse_realtime_date(date_str: str, update_time: str) -> str:
    """Convert realtime_data.prices.date 'M/D' to YYYY-MM-DD using update_time year."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", date_str)
    yy_match = re.match(r"^(\d{4})", update_time)
    year = int(yy_match.group(1)) if yy_match else datetime.now().year
    if not m:
        return f"{year:04d}-01-01"
    mm, dd = int(m.group(1)), int(m.group(2))
    return f"{year:04d}-{mm:02d}-{dd:02d}"


# Item registry: (item_id, fuel_code, realtime_key)
ITEMS = [
    ("regular_gasoline_national", FUEL_REGULAR, REALTIME_KEY_REGULAR),
    ("diesel_national",           FUEL_DIESEL,  REALTIME_KEY_DIESEL),
]


def fetch() -> list[SourceResult]:
    results: list[SourceResult] = []
    fetched_at = now_utc_iso()

    # Fetch realtime page once (carries realtime_data for all fuels)
    try:
        rt_html = _fetch(URL_REALTIME)
    except Exception as e:
        msg = f"realtime fetch failed: {e}"
        for item_id, _, _ in ITEMS:
            results.append(SourceResult(
                item_id=item_id,
                source_name=SOURCE_NAME,
                source_url=URL_REALTIME,
                status="failed",
                fetched_at=fetched_at,
                error=msg,
            ))
        return results

    realtime = _extract_realtime(rt_html) or {}
    polite_sleep()

    for item_id, fuel_code, rt_key in ITEMS:
        url_5y = f"https://e-nenpi.com/gs/price_graph/{PERIOD_5Y}/{fuel_code}/0/"
        # 5-year monthly history
        try:
            html_5y = _fetch(url_5y)
            history = _build_history_from_5y(html_5y)
        except Exception as e:
            print(f"[e_nenpi] {item_id} 5y fetch failed: {e}", file=sys.stderr)
            history = []
        polite_sleep()

        # Current value: realtime_data.prices.<rt_key>.value
        prices = realtime.get("prices") or {}
        current = None
        rt_node = prices.get(rt_key) or {}
        try:
            current = float(rt_node.get("value")) if rt_node.get("value") is not None else None
        except (TypeError, ValueError):
            current = None

        # Append realtime as today's history point (overwriting any same-date entry)
        if current is not None:
            today = _parse_realtime_date(prices.get("date", ""), realtime.get("update_time", ""))
            # Replace any existing point on same date
            history = [hp for hp in history if hp.date != today]
            history.append(HistoryPoint(date=today, value=current))
            history.sort(key=lambda h: h.date)

        if current is None and not history:
            status, error = "failed", "no realtime or history data extracted"
        elif current is None and history:
            current = history[-1].value
            status, error = "stale", "realtime missing; using latest history"
        else:
            status, error = "ok", None

        results.append(SourceResult(
            item_id=item_id,
            source_name=SOURCE_NAME,
            source_url=url_5y,
            status=status,
            current=current,
            history=history,
            fetched_at=fetched_at,
            error=error,
        ))
    return results


def main(_argv: list[str]) -> int:
    output_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cost-watch" / "_sources"
    print(f"[e_nenpi] start fetched_at={now_utc_iso()}")
    results = fetch()
    for r in results:
        out = write_source_result(r, output_dir)
        n = len(r.history)
        latest = f"{r.history[-1].date}={r.history[-1].value}" if r.history else "n/a"
        print(f"[e_nenpi] {r.item_id} status={r.status} current={r.current} points={n} latest={latest} -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
