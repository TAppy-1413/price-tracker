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
