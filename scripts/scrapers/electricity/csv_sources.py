"""
Electricity category scrapers.

Sources:
  JAPIA : data/japia_electricity.csv (10電力会社別、円/kWh、monthly、2011-)
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

JAPIA_URL = "https://www.japia.or.jp/"

MONTHLY = 90


def fetch() -> list[SourceResult]:
    out: list[SourceResult] = []

    # 東電管内
    out.append(fetch_from_csv(
        item_id="elec_tepco",
        csv_path=DATA_DIR / "japia_electricity.csv",
        date_col="date",
        value_col="tepco",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))

    # 関西電力
    out.append(fetch_from_csv(
        item_id="elec_kansai",
        csv_path=DATA_DIR / "japia_electricity.csv",
        date_col="date",
        value_col="kansai",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))

    # 中部電力 (IKS本社が栃木のため、関東+中部圏の参考に)
    out.append(fetch_from_csv(
        item_id="elec_chubu",
        csv_path=DATA_DIR / "japia_electricity.csv",
        date_col="date",
        value_col="chubu",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))

    return out


def main(_argv: list[str]) -> int:
    output_dir = REPO_ROOT / "data" / "cost-watch" / "_sources"
    print(f"[electricity] start fetched_at={now_utc_iso()}")
    for r in fetch():
        out = write_source_result(r, output_dir)
        latest = f"{r.history[-1].date}={r.history[-1].value}" if r.history else "n/a"
        print(f"[electricity] {r.item_id:14s} via {r.source_name:8s} status={r.status:6s} pts={len(r.history):4d} latest={latest} -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
