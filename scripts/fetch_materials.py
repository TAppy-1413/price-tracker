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
    'PRCG20_2200650005': 'diesel',              # 軽油
    'PRCG20_2600550010': 'crude_oil',           # 原油
}

# 2020年基準価格 — 業界相場から設定
# 材料: 指数×基準価格/100 でそのまま換算 (B2B卸売価格)
BASE_PRICES_2020 = {
    'ss400':            75,    # 円/kg 普通鋼構造材
    'aluminum_casting': 350,   # 円/kg アルミダイカスト
    'iron_casting':     85,    # 円/kg 銑鉄鋳物
    'sus303':           420,   # 円/kg ステンレス冷延
    'a5052':            320,   # 円/kg アルミ圧延板
    'crude_oil':        35,    # 円/L 原油 (2020年基準)
}

# 燃料小売: CGPI は卸売指数なので、税金+マージン(固定)と卸売(変動)を分離
# 小売価格 = 卸売成分 × CGPI指数/100 + 固定成分(税金+マージン)
# 参考: ガソリン税53.8円, 石油石炭税2.8円, 軽油引取税32.1円, 消費税10%
FUEL_RETAIL_MODEL = {
    'regular': {
        'variable_2020': 55,    # 卸売成分 (2020年, 税前)
        'fixed': 78,            # ガソリン税53.8 + 石油石炭税2.8 + マージン21.4
        # 小売 = (55×index/100 + 78) = 133 when index=100
    },
    'diesel': {
        'variable_2020': 48,    # 卸売成分
        'fixed': 64,            # 軽油引取税32.1 + 石油石炭税2.8 + マージン29.1
        # 小売 = (48×index/100 + 64) = 112 when index=100
    },
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
    """指数 (2020=100) → 実価格に換算"""
    # 材料・原油: 単純換算
    for mat, base_price in BASE_PRICES_2020.items():
        if mat in df.columns:
            df[mat] = (df[mat] * base_price / 100).round(1)
    # 燃料小売: 税金分離モデル (卸売×指数 + 固定税金)
    for fuel, model in FUEL_RETAIL_MODEL.items():
        if fuel in df.columns:
            df[fuel] = (
                model['variable_2020'] * df[fuel] / 100 + model['fixed']
            ).round(1)
    return df


def build_pre2020_from_metals():
    """
    CGPI接続系列が取得できない場合のフォールバック:
    metals.csv (World Bank + Yahoo Finance) から
    2000〜2019年の材料価格を推定して接続する。
    2020年1月のCGPI価格と一致するように補正。
    """
    import os
    metals_csv = DATA_DIR / "metals.csv"
    if not metals_csv.exists():
        return pd.DataFrame()

    print("[materials] Building pre-2020 data from World Bank metals...")
    df = pd.read_csv(metals_csv)
    df['date'] = pd.to_datetime(df['date'])
    pre = df[df['date'] < '2020-01-01'].copy()
    if pre.empty:
        return pd.DataFrame()

    usd_jpy = pre['usd_jpy'].fillna(110)
    iron_jpy = pre['iron_ore'] * usd_jpy / 1000

    # World Bank ベースの推定価格 (2020年1月時点でCGPIと一致するように係数調整)
    pre['ss400'] = (iron_jpy * 4.8 + 31).round(1)
    pre['aluminum_casting'] = (pre['aluminum'] * 1.3).round(1)
    pre['iron_casting'] = (iron_jpy * 5.5 + 25).round(1)
    pre['sus303'] = (pre['nickel'] * 0.10 + iron_jpy * 0.72 + 250).round(1)
    pre['a5052'] = (pre['aluminum'] * 1.15).round(1)

    # 燃料: 税金分離モデルで推定 (CGPIがないのでアルミの変動率を石油代理として使用しない)
    # ガソリン・軽油はCGPIしか持っていないので、2000-2019はNaNのまま
    pre['regular'] = float('nan')
    pre['highoctane'] = float('nan')
    pre['diesel'] = float('nan')
    pre['crude_oil'] = (pre['iron_ore'] * usd_jpy / 1000 * 0.35).round(1)  # rough proxy

    cols = ['date', 'ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052',
            'regular', 'highoctane', 'diesel', 'crude_oil']
    result = pre[cols].copy()

    print(f"[materials]   Pre-2020: {len(result)} months from World Bank")
    return result


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
        # ハイオク = レギュラー + 約11円/L (ハイオクプレミアム)
        if 'regular' in combined.columns:
            combined['highoctane'] = (combined['regular'] + 11).round(1)

        cols = ['date', 'ss400', 'aluminum_casting', 'iron_casting', 'sus303', 'a5052',
                'regular', 'highoctane', 'diesel', 'crude_oil']
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
