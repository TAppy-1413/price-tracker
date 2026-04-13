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


def fetch_yf_supplement(last_date: pd.Timestamp, fx: pd.DataFrame) -> pd.DataFrame:
    """
    World Bank Pink Sheet にまだ掲載されていない直近月を
    Yahoo Finance の商品先物で補完する。
    LME 直結ではないが、COMEX/市場価格は十分な相関がある。
    """
    import yfinance as yf
    from datetime import datetime

    # 補完が必要な期間
    start = (last_date + pd.DateOffset(months=1)).strftime('%Y-%m-%d')
    end = datetime.now().strftime('%Y-%m-%d')
    if start >= end:
        print("[metals] No gap to fill — data is up to date.")
        return pd.DataFrame()

    print(f"[metals] Filling gap {start} → {end} from Yahoo Finance...")

    # Yahoo Finance 商品ティッカー (USD/トン換算係数付き)
    tickers = {
        'ALI=F':  ('aluminum', 1.0),        # CME Aluminum USD/mt
        'HG=F':   ('copper',   2204.62),     # COMEX Copper USD/lb → USD/mt
        '^NICK':  ('nickel',   1.0),         # LME Nickel (Yahoo)
    }

    rows = []
    for ticker, (metal, mult) in tickers.items():
        try:
            df = yf.download(ticker, start=start, end=end,
                             interval='1mo', progress=False, auto_adjust=False)
            if df.empty:
                continue
            df = df[['Close']].reset_index()
            df.columns = ['date', metal]
            df['date'] = pd.to_datetime(df['date']).dt.to_period('M').dt.to_timestamp()
            df[metal] = df[metal] * mult
            rows.append(df)
        except Exception as e:
            print(f"[metals]   {ticker} failed: {e}")

    if not rows:
        print("[metals]   No supplement data available.")
        return pd.DataFrame()

    # Merge all tickers
    result = rows[0]
    for r in rows[1:]:
        result = result.merge(r, on='date', how='outer')
    result = result.sort_values('date').reset_index(drop=True)

    # Fill missing metals with NaN (will be forward-filled later)
    for col in ['aluminum', 'copper', 'nickel', 'lead', 'tin', 'zinc', 'iron_ore']:
        if col not in result.columns:
            result[col] = float('nan')

    print(f"[metals]   Supplement: {len(result)} months added")
    return result


def main():
    try:
        metals = fetch_pink_sheet()
        fx = fetch_usd_jpy()

        # Supplement with Yahoo Finance for recent months
        last_wb_date = metals['date'].max()
        supplement = fetch_yf_supplement(last_wb_date, fx)
        if not supplement.empty:
            metals = pd.concat([metals, supplement], ignore_index=True)
            metals = metals.drop_duplicates(subset='date', keep='first')
            metals = metals.sort_values('date').reset_index(drop=True)
            # Forward-fill missing metals from last known values
            for c in METAL_COLS.values():
                metals[c] = metals[c].ffill()

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
