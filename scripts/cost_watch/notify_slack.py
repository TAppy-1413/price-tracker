"""
Send a weekly cost-watch summary to Slack via Incoming Webhook.

Reads:  data/cost-watch/{category}.json
Sends:  one Slack message per run (covers all categories given on CLI)

Auth:
  Reads webhook URL from env var SLACK_WEBHOOK_URL.
  In GitHub Actions this is supplied via repo Secrets.

Failure behavior:
  Always exits 0 — Slack issues must not break the data pipeline.
  Errors are logged to stderr and surfaced in the GHA Actions Summary.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

WEBHOOK_ENV = "SLACK_WEBHOOK_URL"
DASHBOARD_BASE_URL = "https://tappy-1413.github.io/price-tracker/cost-watch/"

CATEGORY_EMOJI = {
    "fuel": "⛽",
    "materials": "🔩",
    "wages": "👷",
    "logistics": "🚚",
    "electricity": "⚡",
}

FLAG_BADGE = {
    "consistent": "🟢",
    "warning": "🟡",
    "divergent": "🔴",
    "single": "⚪",
}


def _format_pct(v) -> str:
    if v is None:
        return "-"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _format_value_range(item: dict) -> str:
    vr = item.get("value_range") or {}
    vmin = vr.get("min")
    vmax = vr.get("max")
    unit = item.get("unit", "")
    if vmin is None:
        return "データなし"
    if vmin == vmax:
        return f"{vmin} {unit}"
    return f"{vmin}〜{vmax} {unit}"


def _aggregate_comparisons(item: dict) -> dict:
    """Pick comparison values from the first OK source (deterministic ordering)."""
    for src in item.get("sources", []):
        if src.get("status") == "ok":
            cmp = src.get("comparisons") or {}
            return {
                "wow": cmp.get("wow_pct"),
                "mom": cmp.get("mom_pct"),
                "yoy": cmp.get("yoy_pct"),
                "from_source": src.get("name", ""),
            }
    return {"wow": None, "mom": None, "yoy": None, "from_source": ""}


def _build_category_block(cat_data: dict) -> str:
    name_ja = cat_data.get("category_name_ja", cat_data.get("category", ""))
    cat_id = cat_data.get("category", "")
    emoji = CATEGORY_EMOJI.get(cat_id, "📊")
    lines = [f"*{emoji} {name_ja}*"]

    items = cat_data.get("items", [])
    if not items:
        lines.append("  _データなし_")
        return "\n".join(lines)

    for it in items:
        flag = it.get("consistency_flag", "single")
        badge = FLAG_BADGE.get(flag, "⚪")
        n = it.get("sources_count", 0)
        if n == 0:
            flag_text = f"{badge} 取得不能"
        elif flag == "single":
            flag_text = f"{badge} 単一ソース"
        else:
            flag_jp = {
                "consistent": "整合",
                "warning": "要確認",
                "divergent": "ソース間乖離",
            }.get(flag, flag)
            dev = it.get("max_deviation_pct")
            flag_text = f"{badge} {n}ソース{flag_jp}"
            if dev is not None and n > 1:
                flag_text += f" (最大乖離 {dev}%)"

        cmp = _aggregate_comparisons(it)
        cmp_line = (
            f"  WoW {_format_pct(cmp['wow'])} / "
            f"MoM {_format_pct(cmp['mom'])} / "
            f"YoY {_format_pct(cmp['yoy'])}"
        )

        lines.append(f"  • *{it.get('name_ja', it.get('id'))}* — {_format_value_range(it)}")
        lines.append(f"    {flag_text}")
        if cmp["from_source"]:
            lines.append(f"    {cmp_line}  _({cmp['from_source']}基準)_")
        else:
            lines.append(f"    {cmp_line}")
    return "\n".join(lines)


def _build_message(category_jsons: list[dict]) -> str:
    jst = timezone(timedelta(hours=9))
    today_jst = datetime.now(jst).strftime("%Y-%m-%d (%a)")
    header = f"*📈 価格チャート — 週次サマリー  {today_jst}*"

    blocks = [header, ""]
    for cd in category_jsons:
        blocks.append(_build_category_block(cd))
        blocks.append("")

    blocks.append(f"📊 詳細ダッシュボード: {DASHBOARD_BASE_URL}")
    blocks.append("_本通知は GitHub Actions により自動配信。データソース複数並列、社員自身の判断材料用。_")
    return "\n".join(blocks)


def _send(webhook_url: str, text: str) -> bool:
    payload = {"text": text, "mrkdwn": True}
    try:
        r = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    except Exception as e:
        print(f"[notify_slack] HTTP exception: {e}", file=sys.stderr)
        return False
    if r.status_code >= 200 and r.status_code < 300:
        print(f"[notify_slack] sent ({r.status_code})")
        return True
    print(
        f"[notify_slack] webhook returned {r.status_code}: {r.text[:300]}",
        file=sys.stderr,
    )
    return False


def main(argv: list[str]) -> int:
    if "--dry-run" in argv:
        argv = [a for a in argv if a != "--dry-run"]
        dry_run = True
    else:
        dry_run = False

    cats = argv if argv else ["fuel"]
    repo_root = Path(__file__).resolve().parent.parent.parent
    category_jsons: list[dict] = []
    for c in cats:
        p = repo_root / "data" / "cost-watch" / f"{c}.json"
        if not p.exists():
            print(f"[notify_slack] skip {c}: {p} not found", file=sys.stderr)
            continue
        try:
            with open(p, encoding="utf-8") as f:
                category_jsons.append(json.load(f))
        except Exception as e:
            print(f"[notify_slack] skip {c}: {e}", file=sys.stderr)

    if not category_jsons:
        print("[notify_slack] no categories loaded — nothing to send", file=sys.stderr)
        return 0

    message = _build_message(category_jsons)

    if dry_run:
        print("=== DRY RUN — message that would be sent ===")
        print(message)
        print("=== END DRY RUN ===")
        return 0

    webhook = os.environ.get(WEBHOOK_ENV, "").strip()
    if not webhook:
        print(
            f"[notify_slack] env var {WEBHOOK_ENV} is empty — printing message only",
            file=sys.stderr,
        )
        print(message)
        return 0

    ok = _send(webhook, message)
    if not ok:
        print("[notify_slack] send failed (continuing — pipeline must not break)", file=sys.stderr)
    # Always 0: never break the pipeline due to a notification failure.
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
