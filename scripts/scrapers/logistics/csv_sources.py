"""
Logistics category scrapers.

Sources:
  日銀 SPPI : data/sppi.csv (道路貨物輸送指数, monthly, 2000-)
  JAPIA     : data/japia_truck.csv (軽油価格&燃料サーチャージ, monthly, 1990-)
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
COST_WATCH_DIR = SCRIPT_DIR.parent.parent / "cost_watch"
sys.path.insert(0, str(COST_WATCH_DIR))
from source_base import (  # noqa: E402
    SourceResult,
    fetch_from_csv,
    now_utc_iso,
    write_source_result,
)

REPO_ROOT = SCRIPT_DIR.parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

BOJ_URL = "https://www.boj.or.jp/statistics/pi/sppi_2020/index.htm"
JAPIA_URL = "https://www.japia.or.jp/"
JTA_URL = "https://www.jta.or.jp/"

MONTHLY = 90


def fetch() -> list[SourceResult]:
    out: list[SourceResult] = []

    # トラック運賃指数 (BoJ SPPI 道路貨物輸送)
    out.append(fetch_from_csv(
        item_id="road_freight_index",
        csv_path=DATA_DIR / "sppi.csv",
        date_col="date",
        value_col="road_freight",
        source_name="日銀SPPI",
        source_url=BOJ_URL,
        stale_days=MONTHLY,
    ))

    # トラック軽油価格 (JAPIA 全ト協代理)
    out.append(fetch_from_csv(
        item_id="diesel_truck",
        csv_path=DATA_DIR / "japia_truck.csv",
        date_col="date",
        value_col="diesel_national",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))

    # 燃料サーチャージ (JAPIA)
    out.append(fetch_from_csv(
        item_id="truck_surcharge",
        csv_path=DATA_DIR / "japia_truck.csv",
        date_col="date",
        value_col="truck_surcharge",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))

    return out


def main(_argv: list[str]) -> int:
    output_dir = REPO_ROOT / "data" / "cost-watch" / "_sources"
    print(f"[logistics] start fetched_at={now_utc_iso()}")
    for r in fetch():
        out = write_source_result(r, output_dir)
        latest = f"{r.history[-1].date}={r.history[-1].value}" if r.history else "n/a"
        print(f"[logistics] {r.item_id:22s} via {r.source_name:10s} status={r.status:6s} pts={len(r.history):4d} latest={latest} -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
