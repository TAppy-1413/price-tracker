"""
材料価格 取得スクリプト (日本国内データ)
ソース: 日本銀行 企業物価指数 (CGPI) 2020年基準
対象: SS400相当, アルミ鋳物, 鉄鋳物, SUS303相当, A5052相当
出力: data/materials.csv

CGPI は指数 (2020年=100) で公表される。
各材料の 2020年基準価格 (円/kg) を定義し、指数×基準価格で推定実価格に換算。
"""
import pandas as pd
import requests
import io
import zipfile
from pathlib import Path
import sys

DATA_DIR = Path(__file__).parent.parent / "data"
MATERIALS_CSV = DATA_DIR / "materials.csv"

# 日銀 CGPI 2020年基準 (国内企業物価指数, 月次)
CGPI_ZIP_URL = "https://www.stat-search.boj.or.jp/info/cgpi_m_jp.zip"
# 接続系列 (2015年基準以前 → 2000年〜2019年)
CGPI_LINK_URL = "https://www.stat-search.boj.or.jp/info/cgpilink.csv"

# CGPI コード → 材料名マッピング (国内品 PRCG20_2...)
CGPI_CODES = {
    'PRCG20_2200950022': 'iron_casting',       # 機械用銑鉄鋳物
    'PRCG20_2201050015': 'aluminum_casting',   # アルミニウム合金ダイカスト
    'PRCG20_2201050013': 'a5052',              # アルミ圧延製品
    'PRCG20_2200950016': 'sus303',             # ステンレス冷延鋼板
    'PRCG20_2200950003': 'ss400',              # 小形棒鋼 (SS400相当)
    'PRCG20_2200650001': 'regular',             # レギュラーガソリン
    'PRCG20_2200650005': 'diesel',             # 軽油
}

# 2020年基準価格 — 業界相場から設定
BASE_PRICES_2020 = {
    'ss400':            75,    # 円/kg 普通鋼構造材
    'aluminum_casting': 350,   # 円/kg アルミダイカスト
    'iron_casting':     85,    # 円/kg 銑鉄鋳物
    'sus303':           420,   # 円/kg ステンレス冷延
    'a5052':            320,   # 円/kg アルミ圧延板
    'regular':          135,   # 円/L レギュラーガソリン
    'diesel':           115,   # 円/L 軽油
}


def fetch_cgpi_current() -> pd.DataFrame:
    """CGPI 2020年基準 現行系列を取得"""
    print("[materials] Fetching BOJ CGPI (2020-base)...")
    r = requests.get(CGPI_ZIP_URL, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = [n for n in z.namelist() if n.endswith('.csv')][0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, encoding='shift_jis')
    return _extract_series(df)


def fetch_cgpi_linked() -> pd.DataFrame:
    """CGPI 接続系列 (2000年〜2019年)"""
    print("[materials] Fetching BOJ CGPI linked series...")
    try:
        r = requests.get(CGPI_LINK_URL, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content), encoding='shift_jis')
        return _extract_series(df)
    except Exception as e:
        print(f"[materials]   Linked series failed: {e}")
        return pd.DataFrame()


def _extract_series(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrameからCGPIコードに該当する行を抽出し、縦持ちに変換"""
    code_col = df.columns[0]

    # 日付列を特定 (数字6桁: 202001, 202002, ...)
    date_cols = [c for c in df.columns[3:] if str(c).isdigit()]

    rows = []
    for cgpi_code, material in CGPI_CODES.items():
        mask = df[code_col].astype(str) == cgpi_code
        if mask.sum() == 0:
            continue
        series_row = df[mask].iloc[0]

        for dc in date_cols:
            val = pd.to_numeric(series_row.get(dc), errors='coerce')
            if pd.isna(val):
                continue
            date_str = str(dc)
            if len(date_str) == 6:
                date = f"{date_str[:4]}-{date_str[4:]}-01"
            else:
                continue
            rows.append({
                'date': date,
                'material': material,
                'index': val,
            })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    out['date'] = pd.to_datetime(out['date'])
    # ピボット: 行=date, 列=material
    pivot = out.pivot_table(index='date', columns='material',
                            values='index', aggfunc='first')
    pivot = pivot.reset_index().sort_values('date')
    return pivot


def index_to_price(df: pd.DataFrame) -> pd.DataFrame:
    """指数 (2020=100) → 円/kg に換算"""
    for mat, base_price in BASE_PRICES_2020.items():
        if mat in df.columns:
            df[mat] = (df[mat] * base_price / 100).round(1)
    return df


def main():
    try:
        # 現行系列 (2020年〜)
        current = fetch_cgpi_current()
        print(f"[materials]   Current: {len(current)} months")

        # 接続系列 (2000年〜2019年)
        linked = fetch_cgpi_linked()
        if not linked.empty:
            print(f"[materials]   Linked: {len(linked)} months")
            combined = pd.concat([
                linked[linked['date'] < '2020-01-01'],
                current
            ], ignore_index=True)
            combined = combined.drop_duplicates(subset='date', keep='last')
        else:
            combined = current

        combined = combined.sort_values('date').reset_index(drop=True)

        # 指数 → 円/kg
        combined = index_to_price(combined)
        combined['date'] = combined['date'].dt.strftime('%Y-%m-%d')

        # 列順を揃える
        # ハイオク = レギュラーと同じ指数変動 + 基準価格差
        if 'regular' in combined.columns:
            combined['highoctane'] = (combined['regular'] / BASE_PRICES_2020['regular'] * 146).round(1)

        cols = ['date', 'ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052',
                'regular', 'highoctane', 'diesel']
        cols = [c for c in cols if c in combined.columns]
        combined = combined[cols]

        combined.to_csv(MATERIALS_CSV, index=False)
        print(f"[materials] OK: {len(combined)} rows -> {MATERIALS_CSV}")
        print(f"[materials]   Latest: {combined['date'].iloc[-1]}")
        return 0
    except Exception as e:
        print(f"[materials] ERROR: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
