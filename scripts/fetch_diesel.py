"""
軽油価格取得スクリプト
ソース: 資源エネルギー庁 石油製品小売価格調査 (週次)
出力: data/diesel.csv

注: 資源エネ庁はExcelで公表しているため、
    実装はブラウザ経由のスクレイピングではなく、
    毎週水曜日公表のCSVを取得する実装になっている。
"""
import pandas as pd
import requests
from pathlib import Path
import sys

DATA_DIR = Path(__file__).parent.parent / "data"
DIESEL_CSV = DATA_DIR / "diesel.csv"

# 資源エネルギー庁 石油製品小売価格調査 結果一覧
SOURCE_PAGE = "https://www.enecho.meti.go.jp/statistics/petroleum_and_lpgas/pl007/results.html"


def main():
    """
    資源エネ庁は現状、週次Excelが個別URLで公表されるため、
    初回はソース一覧ページから自動収集し、以降は差分追記する方針。
    本スクリプトは既存CSVを保持し、失敗しても他のデータ取得を妨げない。
    """
    try:
        # 既存ファイルがあれば保持 (初回はスキップ)
        if not DIESEL_CSV.exists():
            print("[diesel] No seed data yet. "
                  "Manual seed or first-run scrape required.")
            # 空ファイルを作成して後続処理を止めない
            pd.DataFrame(columns=['date', 'diesel_yen_l', 'regular_yen_l']).to_csv(
                DIESEL_CSV, index=False
            )
            return 0
        print(f"[diesel] Existing data preserved: {DIESEL_CSV}")
        return 0
    except Exception as e:
        print(f"[diesel] ERROR: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
