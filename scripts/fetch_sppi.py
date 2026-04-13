"""
日銀 企業向けサービス価格指数 (SPPI) 取得スクリプト
ソース: 日本銀行 時系列統計データ検索サイト (一括ダウンロード)
対象: SPPI総平均、道路貨物輸送
出力: data/sppi.csv
"""
import pandas as pd
import requests
import io
import zipfile
from pathlib import Path
import sys

DATA_DIR = Path(__file__).parent.parent / "data"
SPPI_CSV = DATA_DIR / "sppi.csv"

# 接続系列 (1985-2019)
LINK_URL = "https://www.stat-search.boj.or.jp/info/sppilink.csv"
# 2020年基準現行系列 (2015-現在)
CURRENT_ZIP_URL = "https://www.stat-search.boj.or.jp/info/sppi_m_jp.zip"


def fetch_linked_series() -> pd.DataFrame:
    """接続系列 CSV から総平均と道路貨物輸送を抽出"""
    r = requests.get(LINK_URL, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), encoding='shift_jis')
    # 列順: コード, 系列名, 項目名, 200001, 200002, ...
    # 道路貨物輸送 と 総平均 を名前で特定
    name_col = df.columns[2]
    total_mask = df[name_col].astype(str).str.contains(r'総平均', na=False)
    road_mask = df[name_col].astype(str).str.contains(r'道路貨物輸送', na=False)
    # 消費税込みの基本分類 (PRCS20_52... コード) を優先
    code_col = df.columns[0]
    base_mask = df[code_col].astype(str).str.startswith('PRCS20_52')
    total_row = df[total_mask & base_mask].iloc[0]
    road_row = df[road_mask & base_mask].iloc[0]

    date_cols = [c for c in df.columns[3:] if str(c).isdigit() and str(c) >= '200001']
    return _to_long(date_cols, total_row, road_row)


def fetch_current_series() -> pd.DataFrame:
    """現行系列 (2020年基準) を zip から取得"""
    r = requests.get(CURRENT_ZIP_URL, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.endswith('.csv')][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, encoding='shift_jis')

    name_col = df.columns[2]
    code_col = df.columns[0]
    base_mask = df[code_col].astype(str).str.startswith('PRCS20_52')
    total_mask = df[name_col].astype(str).str.contains(r'総平均', na=False)
    road_mask = df[name_col].astype(str).str.contains(r'道路貨物輸送', na=False)
    total_row = df[total_mask & base_mask].iloc[0]
    road_row = df[road_mask & base_mask].iloc[0]

    date_cols = [c for c in df.columns[3:] if str(c).isdigit()]
    return _to_long(date_cols, total_row, road_row)


def _to_long(date_cols, total_row, road_row) -> pd.DataFrame:
    out = pd.DataFrame({
        'date': [f"{str(c)[:4]}-{str(c)[4:]}-01" for c in date_cols],
        'sppi_total': [pd.to_numeric(total_row[c], errors='coerce') for c in date_cols],
        'road_freight': [pd.to_numeric(road_row[c], errors='coerce') for c in date_cols],
    })
    out['date'] = pd.to_datetime(out['date'])
    return out


def main():
    try:
        print("[sppi] Fetching linked series (2000-2019)...")
        linked = fetch_linked_series()
        print(f"[sppi]   linked: {len(linked)} rows")

        print("[sppi] Fetching current 2020-base series...")
        current = fetch_current_series()
        print(f"[sppi]   current: {len(current)} rows")

        # 結合: 接続系列は2019年までが基本。2020年以降は現行系列を優先。
        combined = pd.concat([
            linked[linked['date'] < '2020-01-01'],
            current
        ], ignore_index=True).drop_duplicates(subset='date', keep='last')
        combined = combined.sort_values('date').reset_index(drop=True)
        combined['date'] = combined['date'].dt.strftime('%Y-%m-%d')
        combined.to_csv(SPPI_CSV, index=False)
        print(f"[sppi] OK: {len(combined)} rows -> {SPPI_CSV}")
        return 0
    except Exception as e:
        print(f"[sppi] ERROR: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
