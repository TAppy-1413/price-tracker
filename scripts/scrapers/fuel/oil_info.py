"""
石油情報センター (oil-info.ieej.or.jp) — 給油所ガソリン・軽油・灯油 週次調査

This source publishes the official weekly fuel survey on behalf of 資源エネルギー庁.
Historical data is hosted as XLS (Excel 97-2003 binary) files:

  SekiyuWeekly1990082720040607.xls   (1990-08-27 〜 2004-06-07)
  SekiyuWeekly2004061420090518.xls   (2004-06-14 〜 2009-05-18)
  SekiyuWeekly2009052520110328.xls   (2009-05-25 〜 2011-03-28)
  SekiyuWeekly.xls                   (2011-04-04 〜 2012-03-26)
  (2012-04-04 〜 current)            redirected to 資源エネ庁 — see enecho.py

This scraper handles only files hosted on oil-info.ieej.or.jp. For data from
2012-04-04 onward (i.e. current weekly), enecho.py must be used in addition.

Sheet structure (per fiscal-year XLS):
  Sheet 'レギュラー': row 0=title, row 1=Excel-serial dates, rows 2..56 = regions/prefectures,
                       row 57='全国' (national avg), rows 59..61 = tax info
  Same layout for sheets ハイオク, 軽油, 灯油店頭, 灯油配達.

  Region row of interest:
    row 11: 栃 木   (Tochigi — IKS HQ)
    row 21: 関東局  (Kanto regional aggregate)
    row 57: 全国    (National)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import requests
import xlrd

# Make package import work whether invoked as a script or as a module.
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

# Weekly survey -> mark stale if latest point is older than this.
STALE_DAYS_THRESHOLD = 14

SOURCE_NAME = "石油情報センター"
BASE_URL = "https://oil-info.ieej.or.jp/price/"

# Each entry: (path, label, range)
HISTORICAL_FILES = [
    ("data/SekiyuWeekly1990082720040607.xls", "1990-2004"),
    ("data/SekiyuWeekly2004061420090518.xls", "2004-2009"),
    ("data/SekiyuWeekly2009052520110328.xls", "2009-2011"),
    ("data/SekiyuWeekly.xls",                 "2011-2012"),
]

SHEET_REGULAR = "レギュラー"
SHEET_DIESEL = "軽油"

# Row indices within each sheet
ROW_NATIONAL = 57
ROW_KANTO = 21
ROW_TOCHIGI = 11
ROW_DATE_HEADER = 1
COL_FIRST_DATA = 1


def _excel_serial_to_date(serial: float) -> datetime:
    """Convert an Excel date serial (1900 system) to a datetime."""
    return datetime(1899, 12, 30) + timedelta(days=int(round(serial)))


def _download_xls(path: str, dest: Path) -> bool:
    url = BASE_URL + path
    try:
        r = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"[oil_info] download failed {url}: {e}", file=sys.stderr)
        return False


def _extract_row_history(xls_path: Path, sheet_name: str, target_row: int) -> list[HistoryPoint]:
    """Pull (date, value) pairs across all date columns for one row of one sheet."""
    book = xlrd.open_workbook(str(xls_path))
    if sheet_name not in book.sheet_names():
        return []
    sheet = book.sheet_by_name(sheet_name)
    if target_row >= sheet.nrows:
        return []

    points: list[HistoryPoint] = []
    for c in range(COL_FIRST_DATA, sheet.ncols):
        date_serial = sheet.cell_value(ROW_DATE_HEADER, c)
        if not isinstance(date_serial, (int, float)) or date_serial < 30000:
            continue
        date = _excel_serial_to_date(date_serial).strftime("%Y-%m-%d")

        v = sheet.cell_value(target_row, c)
        if v == "" or v is None:
            continue
        try:
            value = float(v)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        points.append(HistoryPoint(date=date, value=value))
    return points


# Item registry: (item_id, sheet_name, row_index, source_url_path)
ITEMS = [
    ("regular_gasoline_national", SHEET_REGULAR, ROW_NATIONAL, "price.html"),
    ("diesel_national",           SHEET_DIESEL,  ROW_NATIONAL, "price.html"),
    ("regular_gasoline_kanto",    SHEET_REGULAR, ROW_KANTO,    "price.html"),
]


def fetch(work_dir: Path, fetch_history: bool = False) -> list[SourceResult]:
    """
    Fetch the latest fiscal-year XLS (SekiyuWeekly.xls) from oil_info and extract
    rows for the configured items.

    fetch_history=True downloads all 4 historical files and concatenates their
    series (used by backfill).
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    files_to_use = HISTORICAL_FILES if fetch_history else [HISTORICAL_FILES[-1]]

    # Map: item_id -> list[HistoryPoint], plus URL of last file
    series: dict[str, list[HistoryPoint]] = {item[0]: [] for item in ITEMS}
    last_url = ""

    for relpath, label in files_to_use:
        local = work_dir / Path(relpath).name
        ok = _download_xls(relpath, local)
        polite_sleep()
        if not ok:
            continue
        last_url = BASE_URL + relpath
        for item_id, sheet, row, _ in ITEMS:
            try:
                pts = _extract_row_history(local, sheet, row)
            except Exception as e:
                print(f"[oil_info] {item_id}/{label}: parse failed {e}", file=sys.stderr)
                continue
            series[item_id].extend(pts)

    results: list[SourceResult] = []
    fetched_at = now_utc_iso()
    today = datetime.now()
    for item_id, sheet, row, page_path in ITEMS:
        # Deduplicate by date (later files override earlier)
        by_date: dict[str, float] = {}
        for hp in series[item_id]:
            by_date[hp.date] = hp.value
        ordered = sorted(by_date.items())
        history = [HistoryPoint(date=d, value=v) for d, v in ordered]
        if history:
            current = history[-1].value
            latest_dt = datetime.strptime(history[-1].date, "%Y-%m-%d")
            age_days = (today - latest_dt).days
            if age_days > STALE_DAYS_THRESHOLD:
                status = "stale"
                error = f"latest data point {history[-1].date} is {age_days} days old (>{STALE_DAYS_THRESHOLD})"
            else:
                status = "ok"
                error = None
        else:
            current = None
            status = "failed"
            error = "no data extracted"
        results.append(SourceResult(
            item_id=item_id,
            source_name=SOURCE_NAME,
            source_url=last_url or BASE_URL + page_path,
            status=status,
            current=current,
            history=history,
            fetched_at=fetched_at,
            error=error,
        ))
    return results


def main(argv: list[str]) -> int:
    fetch_history = "--backfill" in argv
    work_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cost-watch" / "_cache"
    output_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cost-watch" / "_sources"
    print(f"[oil_info] mode={'backfill' if fetch_history else 'current'} cache={work_dir}")
    results = fetch(work_dir, fetch_history=fetch_history)
    for r in results:
        out = write_source_result(r, output_dir)
        n = len(r.history)
        latest = f"{r.history[-1].date}={r.history[-1].value}" if r.history else "n/a"
        print(f"[oil_info] {r.item_id} status={r.status} points={n} latest={latest} -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
