# cost-watch JSON schema

Multi-source price tracking schema. One JSON file per category.

## Top level

```jsonc
{
  "category": "fuel",
  "category_name_ja": "燃料",
  "last_updated": "2026-04-29T09:00:00Z",   // ISO-8601 UTC, null if never run
  "items": [ /* see below */ ]
}
```

## Item

Each item is a single tracked indicator (e.g. "regular gasoline national avg").

```jsonc
{
  "id": "regular_gasoline_national",
  "name_ja": "レギュラーガソリン（全国平均）",
  "unit": "円/L",
  "display_mode": "range",                  // "range" | "single"
  "value_range": { "min": 174.8, "max": 175.6 },
  "sources_count": 3,
  "consistency_flag": "consistent",         // consistent|warning|divergent|single
  "max_deviation_pct": 0.46,                // (max-min)/mean*100, 2dp
  "sources": [ /* see below */ ]
}
```

## Source

```jsonc
{
  "name": "資源エネルギー庁",
  "current": 175.4,
  "url": "https://www.enecho.meti.go.jp/...",
  "fetched_at": "2026-04-29T09:00:00Z",
  "status": "ok",                           // ok | failed | stale
  "history": [
    { "date": "2010-01-04", "value": 130.6 },
    { "date": "2010-01-11", "value": 130.8 },
    /* ... */
    { "date": "2026-04-29", "value": 175.4 }
  ],
  "comparisons": {
    "wow_pct": 0.34,
    "mom_pct": 1.20,
    "yoy_pct": 5.62
  }
}
```

## Status semantics

- `ok`     : fetched successfully on `last_updated` run
- `failed` : current run failed; `current`/`history` retain previous values
- `stale`  : data is older than expected cadence (e.g. weekly source >14 days old)

## Consistency flag thresholds

Computed from current values across all `status="ok"` sources:

| flag       | condition                                 | UI          |
|------------|-------------------------------------------|-------------|
| consistent | deviation < 2%                            | 🟢 整合     |
| warning    | 2% ≤ deviation < 5%                       | 🟡 要確認   |
| divergent  | deviation ≥ 5%                            | 🔴 ソース間乖離 |
| single     | only 1 source available                   | ⚠️ 単一ソース |

deviation = (max - min) / mean × 100
