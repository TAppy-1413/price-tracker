"""
業務用電力料金 取得スクリプト
ソース: 資源エネルギー庁 電力調査統計
対象: 高圧 業務用電力 (東電管内/中部/関西/全国平均)
出力: data/electricity.csv (手動シード済み)

電気料金は年次改定が基本のため、このスクリプトは
既存CSVを保持し、新年度データの手動追加を前提とする。
"""
import pandas as pd
from pathlib import Path
import sys

DATA_DIR = Path(__file__).parent.parent / "data"
ELEC_CSV = DATA_DIR / "electricity.csv"


def main():
    try:
        if not ELEC_CSV.exists():
            print(f"[electricity] Seed file missing: {ELEC_CSV}")
            pd.DataFrame(columns=['year', 'tepco', 'chubu', 'kansai', 'national']).to_csv(
                ELEC_CSV, index=False
            )
            return 0

        df = pd.read_csv(ELEC_CSV)
        print(f"[electricity] Current: {len(df)} years, latest={df['year'].max()}")
        return 0
    except Exception as e:
        print(f"[electricity] ERROR: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
