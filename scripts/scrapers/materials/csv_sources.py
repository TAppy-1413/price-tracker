"""
Materials category scrapers — wrap existing repo CSVs as SourceResults.

Sources (all from this repository's existing pipelines):
  JAPIA      : data/japia_steel.csv (1974-) / japia_aluminum.csv / japia_copper.csv
  World Bank : data/metals.csv (Pink Sheet, monthly aggregated → also used)
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

JAPIA_URL = "https://www.japia.or.jp/" + "?topics=press-release"
WB_URL = "https://www.worldbank.org/en/research/commodity-markets"

# stale thresholds (days)
MONTHLY = 90
WEEKLY = 14


def fetch() -> list[SourceResult]:
    out: list[SourceResult] = []

    # 鋼材 (熱延鋼板)
    out.append(fetch_from_csv(
        item_id="steel_hot_rolled",
        csv_path=DATA_DIR / "japia_steel.csv",
        date_col="date",
        value_col="hot_rolled",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))

    # アルミ A5052 / アルミ地金
    out.append(fetch_from_csv(
        item_id="aluminum_a5052",
        csv_path=DATA_DIR / "japia_aluminum.csv",
        date_col="date",
        value_col="al_ingot",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))
    out.append(fetch_from_csv(
        item_id="aluminum_a5052",
        csv_path=DATA_DIR / "metals.csv",
        date_col="date",
        value_col="aluminum",
        source_name="World Bank",
        source_url=WB_URL,
        stale_days=WEEKLY,
    ))

    # 銅
    out.append(fetch_from_csv(
        item_id="copper",
        csv_path=DATA_DIR / "japia_copper.csv",
        date_col="date",
        value_col="copper",
        source_name="JAPIA",
        source_url=JAPIA_URL,
        stale_days=MONTHLY,
    ))
    out.append(fetch_from_csv(
        item_id="copper",
        csv_path=DATA_DIR / "metals.csv",
        date_col="date",
        value_col="copper",
        source_name="World Bank",
        source_url=WB_URL,
        stale_days=WEEKLY,
    ))

    # ニッケル (チタン/インコネル系の代理指標)
    out.append(fetch_from_csv(
        item_id="nickel_proxy",
        csv_path=DATA_DIR / "metals.csv",
        date_col="date",
        value_col="nickel",
        source_name="World Bank",
        source_url=WB_URL,
        stale_days=WEEKLY,
    ))

    return out


def main(_argv: list[str]) -> int:
    output_dir = REPO_ROOT / "data" / "cost-watch" / "_sources"
    print(f"[materials] start fetched_at={now_utc_iso()}")
    for r in fetch():
        out = write_source_result(r, output_dir)
        latest = f"{r.history[-1].date}={r.history[-1].value}" if r.history else "n/a"
        print(f"[materials] {r.item_id:20s} via {r.source_name:14s} status={r.status:6s} pts={len(r.history):4d} latest={latest} -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
