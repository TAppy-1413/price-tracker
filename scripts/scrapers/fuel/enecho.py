"""
資源エネルギー庁 (enecho.meti.go.jp) — 石油製品小売価格調査

The official weekly retail fuel price survey conducted on behalf of METI by
石油情報センター. Published every Wednesday for the prior Monday's survey.

Data is hosted as XLS files linked from:
  https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/results.html

Each weekly Excel file follows the same layout as the historical files on
oil-info.ieej.or.jp, so we reuse the row indices from oil_info.py.

NOTE: As of 2026-04, this host is not reachable from some sandboxed environments
      (DNS-level blocking). In GitHub Actions runners it is accessible.
      When unreachable, this scraper returns status="failed" with a clear error
      so the merger can fall back to other sources.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from typing import Optional

import requests
import xlrd

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

# Reuse oil_info row constants — same XLS schema is used by enecho's Excel.
sys.path.insert(0, str(SCRIPT_DIR))
from oil_info import (  # noqa: E402
    ROW_DATE_HEADER,
    ROW_NATIONAL,
    ROW_KANTO,
    SHEET_DIESEL,
    SHEET_REGULAR,
    _excel_serial_to_date,
)

SOURCE_NAME = "資源エネルギー庁"
RESULTS_PAGE = "https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/results.html"

# meti.go.jp times out aggressively for unfamiliar UAs. Use a browser-like UA.
ENECHO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
ENECHO_TIMEOUT_SEC = 60
ENECHO_MAX_ATTEMPTS = 2

# Item registry: (item_id, sheet, row)
ITEMS = [
    ("regular_gasoline_national", SHEET_REGULAR, ROW_NATIONAL),
    ("diesel_national",           SHEET_DIESEL,  ROW_NATIONAL),
    ("regular_gasoline_kanto",    SHEET_REGULAR, ROW_KANTO),
]


def _fetch_with_retry(url: str, want_bytes: bool = False):
    last_err: Optional[Exception] = None
    for attempt in range(ENECHO_MAX_ATTEMPTS):
        try:
            r = requests.get(url, headers=ENECHO_HEADERS, timeout=ENECHO_TIMEOUT_SEC)
            r.raise_for_status()
            return r.content if want_bytes else r.content.decode(r.encoding or "utf-8", errors="replace")
        except Exception as e:
            last_err = e
            print(f"[enecho] attempt {attempt+1}/{ENECHO_MAX_ATTEMPTS} failed for {url}: {e}", file=sys.stderr)
    raise RuntimeError(f"all {ENECHO_MAX_ATTEMPTS} attempts failed: {last_err}")


def _fetch_text(url: str) -> str:
    return _fetch_with_retry(url, want_bytes=False)


def _fetch_bytes(url: str) -> bytes:
    return _fetch_with_retry(url, want_bytes=True)


def _extract_xls_links(html: str, base_url: str) -> list[str]:
    """Find all .xls/.xlsx links on the results page."""
    links = re.findall(r'href="([^"]+\.xlsx?)"', html, re.IGNORECASE)
    out = []
    for href in links:
        if href.startswith("http"):
            out.append(href)
        elif href.startswith("/"):
            m = re.match(r"^(https?://[^/]+)", base_url)
            if m:
                out.append(m.group(1) + href)
        else:
            out.append(base_url.rsplit("/", 1)[0] + "/" + href)
    return out


def _parse_xls_for_items(xls_bytes: bytes) -> dict[str, list[HistoryPoint]]:
    """Same row structure as oil_info historical XLS."""
    book = xlrd.open_workbook(file_contents=xls_bytes)
    out: dict[str, list[HistoryPoint]] = {item[0]: [] for item in ITEMS}
    for item_id, sheet_name, row in ITEMS:
        if sheet_name not in book.sheet_names():
            continue
        sheet = book.sheet_by_name(sheet_name)
        if row >= sheet.nrows:
            continue
        for c in range(1, sheet.ncols):
            ds = sheet.cell_value(ROW_DATE_HEADER, c)
            if not isinstance(ds, (int, float)) or ds < 30000:
                continue
            date = _excel_serial_to_date(ds).strftime("%Y-%m-%d")
            v = sheet.cell_value(row, c)
            try:
                value = float(v)
            except (TypeError, ValueError):
                continue
            if value <= 0:
                continue
            out[item_id].append(HistoryPoint(date=date, value=value))
    return out


def fetch() -> list[SourceResult]:
    fetched_at = now_utc_iso()
    try:
        html = _fetch_text(RESULTS_PAGE)
    except Exception as e:
        msg = f"unable to reach {RESULTS_PAGE}: {e}"
        return [
            SourceResult(
                item_id=item_id,
                source_name=SOURCE_NAME,
                source_url=RESULTS_PAGE,
                status="failed",
                fetched_at=fetched_at,
                error=msg,
            )
            for item_id, _, _ in ITEMS
        ]
    polite_sleep()

    xls_urls = _extract_xls_links(html, RESULTS_PAGE)
    if not xls_urls:
        msg = "no XLS links found on results page (page structure may have changed)"
        return [
            SourceResult(
                item_id=item_id,
                source_name=SOURCE_NAME,
                source_url=RESULTS_PAGE,
                status="failed",
                fetched_at=fetched_at,
                error=msg,
            )
            for item_id, _, _ in ITEMS
        ]

    # Combine all XLS files (each typically holds one fiscal year)
    combined: dict[str, list[HistoryPoint]] = {item[0]: [] for item in ITEMS}
    last_url = ""
    for url in xls_urls:
        try:
            xls_bytes = _fetch_bytes(url)
            polite_sleep()
        except Exception as e:
            print(f"[enecho] download failed {url}: {e}", file=sys.stderr)
            continue
        try:
            parsed = _parse_xls_for_items(xls_bytes)
        except Exception as e:
            print(f"[enecho] parse failed {url}: {e}", file=sys.stderr)
            continue
        for k, pts in parsed.items():
            combined[k].extend(pts)
        last_url = url

    results: list[SourceResult] = []
    for item_id, _, _ in ITEMS:
        # Dedupe by date
        by_date: dict[str, float] = {hp.date: hp.value for hp in combined[item_id]}
        ordered = sorted(by_date.items())
        history = [HistoryPoint(date=d, value=v) for d, v in ordered]
        if history:
            current = history[-1].value
            status, error = "ok", None
        else:
            current = None
            status, error = "failed", "no usable data extracted from XLS files"
        results.append(SourceResult(
            item_id=item_id,
            source_name=SOURCE_NAME,
            source_url=last_url or RESULTS_PAGE,
            status=status,
            current=current,
            history=history,
            fetched_at=fetched_at,
            error=error,
        ))
    return results


def main(_argv: list[str]) -> int:
    output_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cost-watch" / "_sources"
    print(f"[enecho] start fetched_at={now_utc_iso()}")
    results = fetch()
    for r in results:
        out = write_source_result(r, output_dir)
        if r.status == "ok":
            n = len(r.history)
            latest = f"{r.history[-1].date}={r.history[-1].value}"
            print(f"[enecho] {r.item_id} status=ok current={r.current} points={n} latest={latest} -> {out.name}")
        else:
            print(f"[enecho] {r.item_id} status={r.status} error={r.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
