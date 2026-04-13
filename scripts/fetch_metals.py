"""
金属国際価格取得スクリプト
ソース: World Bank Commodity Markets (Pink Sheet) - 月次更新
対象: アルミ、銅、ニッケル、鉄鉱石、鉛、錫、亜鉛
為替: Yahoo Finance USD/JPY
出力: data/metals.csv (JPY/kg換算済み)
"""
import pandas as pd
import requests
import io
from pathlib import Path
import sys

DATA_DIR = Path(__file__).parent.parent / "data"
METALS_CSV = DATA_DIR / "metals.csv"

PINK_SHEET_URL = "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx"

METAL_COLS = {
    'Aluminum': 'aluminum',
    'Copper': 'copper',
    'Nickel': 'nickel',
    'Lead': 'lead',
    'Tin': 'tin',
    'Zinc': 'zinc',
    'Iron ore, cfr spot': 'iron_ore',
}


def fetch_pink_sheet() -> pd.DataFrame:
    """World Bank Pink Sheet から金属月次価格を取得"""
    print("[metals] Fetching World Bank Pink Sheet...")
    r = requests.get(PINK_SHEET_URL, timeout=120)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content), sheet_name='Monthly Prices', skiprows=4)
    df = df.rename(columns={'Unnamed: 0': 'date'})
    df = df[df['date'].astype(str).str.contains('M', na=False)]
    df = df[df['date'].astype(str) >= '2000M01'].copy()
    df['date'] = pd.to_datetime(
        df['date'].astype(str).str.replace('M', '-') + '-01'
    )
    cols = ['date'] + list(METAL_COLS.keys())
    df = df[cols].rename(columns=METAL_COLS)
    for c in METAL_COLS.values():
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def fetch_usd_jpy() -> pd.DataFrame:
    """Yahoo Finance から USD/JPY 月次レートを取得"""
    print("[metals] Fetching USD/JPY from Yahoo Finance...")
    import yfinance as yf
    df = yf.download(
        "JPY=X", start='2000-01-01', interval='1mo',
        progress=False, auto_adjust=False
    )
    df = df[['Close']].reset_index()
    df.columns = ['date', 'usd_jpy']
    df['date'] = pd.to_datetime(df['date']).dt.to_period('M').dt.to_timestamp()
    return df


def convert_to_jpy_per_kg(metals: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    """USD/トン → 円/kg 換算"""
    m = metals.merge(fx, on='date', how='left')
    m['usd_jpy'] = m['usd_jpy'].ffill().bfill()
    # Aluminum/Copper/Nickel/Lead/Tin/Zinc are in USD/mt -> JPY/kg
    for c in ['aluminum', 'copper', 'nickel', 'lead', 'tin', 'zinc']:
        m[c] = (m[c] * m['usd_jpy'] / 1000).round(2)
    # Iron ore stays in USD/dmtu (spot reference)
    m['iron_ore'] = m['iron_ore'].round(2)
    return m[[
        'date', 'usd_jpy', 'aluminum', 'copper', 'nickel',
        'lead', 'tin', 'zinc', 'iron_ore'
    ]]


def main():
    try:
        metals = fetch_pink_sheet()
        fx = fetch_usd_jpy()
        out = convert_to_jpy_per_kg(metals, fx)
        out['date'] = out['date'].dt.strftime('%Y-%m-%d')
        out.to_csv(METALS_CSV, index=False)
        print(f"[metals] OK: {len(out)} rows -> {METALS_CSV}")
        return 0
    except Exception as e:
        print(f"[metals] ERROR: {e}", file=sys.stderr)
        # Don't fail the whole pipeline if one source is down
        return 0


if __name__ == "__main__":
    sys.exit(main())
