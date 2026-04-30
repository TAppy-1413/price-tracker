"""
Wages category scrapers — wrap existing min_wage.csv as multi-source view.

Sources:
  厚労省       : data/min_wage.csv (年次、2000-2025)
  JAPIA再集計  : data/japia_wage.csv (alternate aggregation, 2002-2025)
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

MHLW_URL = "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/koyou_roudou/roudoukijun/minimumichiran/"
JAPIA_URL = "https://www.japia.or.jp/"

YEARLY = 400


def fetch() -> list[SourceResult]:
    out: list[SourceResult] = []

    # 栃木県最低賃金
    out.append(fetch_from_csv(
        item_id="min_wage_tochigi",
        csv_path=DATA_DIR / "min_wage.csv",
        date_col="year",
        value_col="tochigi",
        source_name="厚労省",
        source_url=MHLW_URL,
        stale_days=YEARLY,
    ))
    out.append(fetch_from_csv(
        item_id="min_wage_tochigi",
        csv_path=DATA_DIR / "japia_wage.csv",
        date_col="year",
        value_col="tochigi",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=YEARLY,
    ))

    # 全国加重平均最低賃金
    out.append(fetch_from_csv(
        item_id="min_wage_nationwide",
        csv_path=DATA_DIR / "min_wage.csv",
        date_col="year",
        value_col="nationwide",
        source_name="厚労省",
        source_url=MHLW_URL,
        stale_days=YEARLY,
    ))
    out.append(fetch_from_csv(
        item_id="min_wage_nationwide",
        csv_path=DATA_DIR / "japia_wage.csv",
        date_col="year",
        value_col="nationwide",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=YEARLY,
    ))

    return out


def main(_argv: list[str]) -> int:
    output_dir = REPO_ROOT / "data" / "cost-watch" / "_sources"
    print(f"[wages] start fetched_at={now_utc_iso()}")
    for r in fetch():
        out = write_source_result(r, output_dir)
        latest = f"{r.history[-1].date}={r.history[-1].value}" if r.history else "n/a"
        print(f"[wages] {r.item_id:24s} via {r.source_name:8s} status={r.status:6s} pts={len(r.history):4d} latest={latest} -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
