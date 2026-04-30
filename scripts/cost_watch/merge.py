"""
Merge per-source SourceResult JSON files into a single category JSON.

Reads:  data/cost-watch/_sources/*.json  (per-source-per-item)
Writes: data/cost-watch/{category}.json  (multi-source consolidated)

Schema: see data/cost-watch/_SCHEMA.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# Local imports (works whether script is run from anywhere)
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from consistency import calc_comparisons, evaluate_consistency  # noqa: E402


# Item registry (ordering controls UI display)
CATEGORY_ITEMS = {
    "fuel": [
        {
            "id": "regular_gasoline_national",
            "name_ja": "レギュラーガソリン（全国平均）",
            "unit": "円/L",
        },
        {
            "id": "diesel_national",
            "name_ja": "軽油（全国平均）",
            "unit": "円/L",
        },
        {
            "id": "regular_gasoline_kanto",
            "name_ja": "レギュラーガソリン（関東平均）",
            "unit": "円/L",
        },
    ],
}

CATEGORY_NAME_JA = {
    "fuel": "燃料",
    "materials": "材料費",
    "wages": "人件費",
    "logistics": "物流費",
    "electricity": "電気代",
}


def _load_sources(sources_dir: Path) -> list[dict]:
    if not sources_dir.exists():
        return []
    out: list[dict] = []
    for p in sorted(sources_dir.glob("*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception as e:
            print(f"[merge] skip unreadable {p}: {e}", file=sys.stderr)
    return out


def _build_item(
    item_meta: dict,
    sources_for_item: list[dict],
) -> dict:
    """Combine all sources for one item into the schema-compliant item dict."""
    item_sources_out: list[dict] = []
    ok_currents: list[float] = []

    for src in sources_for_item:
        history = src.get("history") or []
        comparisons = calc_comparisons(history)
        node = {
            "name": src.get("source_name", ""),
            "current": src.get("current"),
            "url": src.get("source_url", ""),
            "fetched_at": src.get("fetched_at", ""),
            "status": src.get("status", "failed"),
            "history": history,
            "comparisons": comparisons,
        }
        if src.get("error"):
            node["error"] = src["error"]
        item_sources_out.append(node)
        if node["status"] == "ok" and node["current"] is not None:
            ok_currents.append(float(node["current"]))

    cr = evaluate_consistency(ok_currents)
    return {
        "id": item_meta["id"],
        "name_ja": item_meta["name_ja"],
        "unit": item_meta["unit"],
        "display_mode": "range" if cr.sources_count >= 2 else "single",
        "value_range": (
            {"min": cr.value_min, "max": cr.value_max}
            if cr.value_min is not None
            else None
        ),
        "sources_count": cr.sources_count,
        "consistency_flag": cr.flag,
        "max_deviation_pct": cr.max_deviation_pct,
        "sources": item_sources_out,
    }


def merge_category(
    category: str,
    sources_dir: Path,
    output_path: Path,
) -> dict:
    items_meta = CATEGORY_ITEMS.get(category)
    if not items_meta:
        raise ValueError(f"unknown category: {category}")

    all_sources = _load_sources(sources_dir)

    items_out: list[dict] = []
    for meta in items_meta:
        relevant = [s for s in all_sources if s.get("item_id") == meta["id"]]
        items_out.append(_build_item(meta, relevant))

    # last_updated = max of fetched_at across all ok sources
    fetched_times = [
        s.get("fetched_at")
        for s in all_sources
        if s.get("status") == "ok" and s.get("fetched_at")
    ]
    last_updated = max(fetched_times) if fetched_times else None

    out = {
        "category": category,
        "category_name_ja": CATEGORY_NAME_JA.get(category, category),
        "last_updated": last_updated,
        "items": items_out,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Mirror to docs/data/cost-watch/ for GitHub Pages frontend consumption.
    docs_path = (
        SCRIPT_DIR.parent.parent
        / "docs"
        / "data"
        / "cost-watch"
        / output_path.name
    )
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(docs_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return out


def main(argv: list[str]) -> int:
    cats = argv if argv else ["fuel"]
    repo_root = SCRIPT_DIR.parent.parent
    sources_dir = repo_root / "data" / "cost-watch" / "_sources"
    for c in cats:
        out_path = repo_root / "data" / "cost-watch" / f"{c}.json"
        try:
            out = merge_category(c, sources_dir, out_path)
        except Exception as e:
            print(f"[merge] {c}: failed {e}", file=sys.stderr)
            continue
        print(f"[merge] {c}: wrote {out_path.name} (last_updated={out['last_updated']})")
        for it in out["items"]:
            r = it["value_range"] or {"min": "n/a", "max": "n/a"}
            print(
                f"  - {it['id']}: {it['sources_count']}src "
                f"flag={it['consistency_flag']} "
                f"range=[{r.get('min')}..{r.get('max')}] "
                f"dev={it['max_deviation_pct']}%"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
