"""
Base utilities for cost-watch source scrapers.

Each scraper produces a SourceResult that the merger consumes.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

USER_AGENT = "IKS-PriceTracker-Bot/1.0 (+https://github.com/tappy-1413/price-tracker)"
REQUEST_TIMEOUT_SEC = 30
INTER_REQUEST_SLEEP_SEC = 2.0


@dataclass
class HistoryPoint:
    date: str   # YYYY-MM-DD
    value: float


@dataclass
class SourceResult:
    """One source × one item."""
    item_id: str             # e.g. "regular_gasoline_national"
    source_name: str         # e.g. "資源エネルギー庁"
    source_url: str
    status: str              # "ok" | "failed" | "stale"
    current: Optional[float] = None
    history: list[HistoryPoint] = field(default_factory=list)
    fetched_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["history"] = [asdict(h) for h in self.history]
        return d


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_source_result(result: SourceResult, output_dir: Path) -> Path:
    """Persist a SourceResult to its own JSON file under data/cost-watch/_sources/."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = f"{result.item_id}__{result.source_name}".replace("/", "_")
    path = output_dir / f"{safe}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def polite_sleep():
    time.sleep(INTER_REQUEST_SLEEP_SEC)


# ---------------------------------------------------------------------
# CSV adapter — wrap an existing CSV column as a SourceResult.
#
# Used to lift the existing single-source CSVs (japia_*, metals, sppi,
# min_wage) into the cost-watch multi-source schema as "Source 1" of
# each indicator.
# ---------------------------------------------------------------------

import csv as _csv  # noqa: E402


def fetch_from_csv(
    *,
    item_id: str,
    csv_path: Path,
    date_col: str,
    value_col: str,
    source_name: str,
    source_url: str,
    stale_days: int = 60,
    value_scale: float = 1.0,
) -> SourceResult:
    """
    Read a single column of an existing CSV file as a SourceResult.

    date_col may be "date" (YYYY-MM-DD) or "year" (YYYY → mid-year date).
    Empty/missing values are skipped (typical for partial future months).
    stale_days controls when the latest value is flagged status="stale".
    value_scale multiplies all values (e.g. 0.001 to convert /t to /kg).
    """
    fetched_at = now_utc_iso()

    if not csv_path.exists():
        return SourceResult(
            item_id=item_id,
            source_name=source_name,
            source_url=source_url,
            status="failed",
            fetched_at=fetched_at,
            error=f"csv not found: {csv_path}",
        )

    history: list[HistoryPoint] = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                raw_date = (row.get(date_col) or "").strip()
                raw_val = (row.get(value_col) or "").strip()
                if not raw_date or not raw_val:
                    continue
                # Date normalization
                if date_col == "year":
                    try:
                        y = int(raw_date)
                        date = f"{y:04d}-07-01"  # mid-year representative
                    except ValueError:
                        continue
                else:
                    date = raw_date[:10]
                try:
                    value = float(raw_val) * value_scale
                except ValueError:
                    continue
                if value <= 0:
                    continue
                history.append(HistoryPoint(date=date, value=value))
    except Exception as e:
        return SourceResult(
            item_id=item_id,
            source_name=source_name,
            source_url=source_url,
            status="failed",
            fetched_at=fetched_at,
            error=f"csv read error: {e}",
        )

    if not history:
        return SourceResult(
            item_id=item_id,
            source_name=source_name,
            source_url=source_url,
            status="failed",
            fetched_at=fetched_at,
            error=f"no usable rows in column '{value_col}'",
        )

    history.sort(key=lambda h: h.date)
    current = history[-1].value
    latest_dt = datetime.strptime(history[-1].date, "%Y-%m-%d")
    age = (datetime.now() - latest_dt).days
    if age > stale_days:
        status = "stale"
        error = f"latest {history[-1].date} is {age} days old (>{stale_days})"
    else:
        status = "ok"
        error = None

    return SourceResult(
        item_id=item_id,
        source_name=source_name,
        source_url=source_url,
        status=status,
        current=current,
        history=history,
        fetched_at=fetched_at,
        error=error,
    )
