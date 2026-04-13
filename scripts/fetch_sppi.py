"""
日銀 企業向けサービス価格指数 (SPPI) 取得スクリプト
ソース: 日本銀行 時系列統計データ検索サイト
対象: 総平均、道路貨物輸送、外航貨物、国際航空貨物、内航貨物
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

LINK_URL = "https://www.stat-search.boj.or.jp/info/sppilink.csv"
CURRENT_ZIP_URL = "https://www.stat-search.boj.or.jp/info/sppi_m_jp.zip"

# 取得対象の系列 (名前検索キーワード → 列名)
SERIES = {
    '総平均':         'sppi_total',
    '道路貨物輸送':    'road_freight',
    '外航貨物輸送':    'ocean_freight',
    '国際航空貨物輸送': 'air_freight',
    '内航貨物輸送':    'coastal_freight',
}


def _extract_rows(df, series_map):
    """DataFrameから対象系列の行を抽出"""
    name_col = df.columns[2]
    code_col = df.columns[0]
    base_mask = df[code_col].astype(str).str.startswith('PRCS20_52')
    rows = {}
    for keyword, col_name in series_map.items():
        mask = df[name_col].astype(str).str.contains(keyword, na=False)
        matches = df[mask & base_mask]
        if len(matches) == 0:
            # Fallback: try without base_mask
            matches = df[mask]
        if len(matches) > 0:
            rows[col_name] = matches.iloc[0]
    return rows


def _to_long(date_cols, series_rows):
    """Wide → long format"""
    data = {'date': [f"{str(c)[:4]}-{str(c)[4:]}-01" for c in date_cols]}
    for col_name, row in series_rows.items():
        data[col_name] = [pd.to_numeric(row.get(c), errors='coerce') for c in date_cols]
    out = pd.DataFrame(data)
    out['date'] = pd.to_datetime(out['date'])
    return out


def fetch_linked_series():
    r = requests.get(LINK_URL, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), encoding='shift_jis')
    rows = _extract_rows(df, SERIES)
    date_cols = [c for c in df.columns[3:] if str(c).isdigit() and str(c) >= '200001']
    return _to_long(date_cols, rows)


def fetch_current_series():
    r = requests.get(CURRENT_ZIP_URL, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.endswith('.csv')][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, encoding='shift_jis')
    rows = _extract_rows(df, SERIES)
    date_cols = [c for c in df.columns[3:] if str(c).isdigit()]
    return _to_long(date_cols, rows)


def main():
    try:
        print("[sppi] Fetching linked series (2000-2019)...")
        linked = fetch_linked_series()
        print(f"[sppi]   linked: {len(linked)} rows, cols: {list(linked.columns)}")

        print("[sppi] Fetching current 2020-base series...")
        current = fetch_current_series()
        print(f"[sppi]   current: {len(current)} rows, cols: {list(current.columns)}")

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
