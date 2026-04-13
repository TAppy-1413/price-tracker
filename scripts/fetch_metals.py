"""
金属・材料原価 取得スクリプト

データ戦略:
  歴史 (2000〜約2年前): World Bank Pink Sheet (月次, 1-3ヶ月遅延)
  直近 (約1年〜今週):  Yahoo Finance 商品先物 (週次, ほぼリアルタイム)

両方を取得し、World Bankが未公表の期間をYFで埋める。
直近1年は週次 (金曜終値) で解像度を上げる。

出力: data/metals.csv  (JPY/kg 換算済み)
"""
import pandas as pd
import requests
import io
from pathlib import Path
from datetime import datetime, timedelta
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

# Yahoo Finance ティッカー → (列名, USD/mt 換算乗数)
YF_TICKERS = {
    'ALI=F':  ('aluminum', 1.0),       # CME Aluminum USD/mt
    'HG=F':   ('copper',   2204.62),   # COMEX Copper USD/lb → USD/mt
    # Nickel: no free YF ticker available; forward-filled from World Bank
    'ZNC=F':  ('zinc',     1.0),       # Zinc USD/mt
    'TIO=F':  ('iron_ore', 1.0),       # SGX Iron Ore USD/mt
}


# ------------------------------------------------------------------
# 1. World Bank (歴史データ, 月次)
# ------------------------------------------------------------------
def fetch_pink_sheet() -> pd.DataFrame:
    print("[metals] 1/3 World Bank Pink Sheet (月次)...")
    r = requests.get(PINK_SHEET_URL, timeout=120)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content),
                       sheet_name='Monthly Prices', skiprows=4)
    df = df.rename(columns={'Unnamed: 0': 'date'})
    df = df[df['date'].astype(str).str.contains('M', na=False)]
    df = df[df['date'].astype(str) >= '2000M01'].copy()
    df['date'] = pd.to_datetime(
        df['date'].astype(str).str.replace('M', '-') + '-01')
    cols = ['date'] + list(METAL_COLS.keys())
    df = df[cols].rename(columns=METAL_COLS)
    for c in METAL_COLS.values():
        df[c] = pd.to_numeric(df[c], errors='coerce')
    print(f"[metals]   World Bank: {len(df)} months, latest {df['date'].max().date()}")
    return df


# ------------------------------------------------------------------
# 2. Yahoo Finance (直近データ, 日次→週次集約)
# ------------------------------------------------------------------
def fetch_yf_weekly(start: str) -> pd.DataFrame:
    """Yahoo Financeから日次データを取得し、金曜終値で週次に集約"""
    import yfinance as yf

    end = datetime.now().strftime('%Y-%m-%d')
    print(f"[metals] 2/3 Yahoo Finance 週次 ({start} → {end})...")

    frames = []
    for ticker, (metal, mult) in YF_TICKERS.items():
        try:
            df = yf.download(ticker, start=start, end=end,
                             interval='1wk', progress=False, auto_adjust=False)
            if df.empty:
                print(f"[metals]   {ticker} ({metal}): empty")
                continue
            df = df[['Close']].reset_index()
            df.columns = ['date', metal]
            df['date'] = pd.to_datetime(df['date'])
            df[metal] = (df[metal] * mult).round(2)
            frames.append(df)
            print(f"[metals]   {ticker} ({metal}): {len(df)} weeks")
        except Exception as e:
            print(f"[metals]   {ticker} ({metal}): FAILED {e}")

    if not frames:
        return pd.DataFrame()

    result = frames[0]
    for f in frames[1:]:
        result = result.merge(f, on='date', how='outer')
    result = result.sort_values('date').reset_index(drop=True)

    # 欠損列は NaN のまま (後で ffill)
    for col in METAL_COLS.values():
        if col not in result.columns:
            result[col] = float('nan')
    return result


# ------------------------------------------------------------------
# 3. USD/JPY (Yahoo Finance, 月次+週次)
# ------------------------------------------------------------------
def fetch_usd_jpy_monthly() -> pd.DataFrame:
    import yfinance as yf
    print("[metals] 3/3 USD/JPY (月次+週次)...")
    df = yf.download("JPY=X", start='2000-01-01',
                     interval='1mo', progress=False, auto_adjust=False)
    df = df[['Close']].reset_index()
    df.columns = ['date', 'usd_jpy']
    df['date'] = pd.to_datetime(df['date']).dt.to_period('M').dt.to_timestamp()
    return df


def fetch_usd_jpy_weekly(start: str) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download("JPY=X", start=start,
                     interval='1wk', progress=False, auto_adjust=False)
    if df.empty:
        return pd.DataFrame()
    df = df[['Close']].reset_index()
    df.columns = ['date', 'usd_jpy']
    df['date'] = pd.to_datetime(df['date'])
    return df


# ------------------------------------------------------------------
# 4. 結合・変換
# ------------------------------------------------------------------
def convert_to_jpy(df: pd.DataFrame) -> pd.DataFrame:
    """USD/mt → JPY/kg に変換 (usd_jpy 列が必要)"""
    df['usd_jpy'] = df['usd_jpy'].ffill().bfill()
    for c in ['aluminum', 'copper', 'nickel', 'lead', 'tin', 'zinc']:
        if c in df.columns:
            df[c] = (df[c] * df['usd_jpy'] / 1000).round(2)
    if 'iron_ore' in df.columns:
        df['iron_ore'] = df['iron_ore'].round(2)
    return df


def main():
    try:
        # --- 歴史データ (World Bank 月次) ---
        wb = fetch_pink_sheet()
        fx_monthly = fetch_usd_jpy_monthly()

        wb_merged = wb.merge(fx_monthly, on='date', how='left')
        wb_merged = convert_to_jpy(wb_merged)

        # --- 直近データ (Yahoo Finance 週次, 過去1年) ---
        one_year_ago = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
        yf_weekly = fetch_yf_weekly(one_year_ago)

        if not yf_weekly.empty:
            fx_weekly = fetch_usd_jpy_weekly(one_year_ago)
            if not fx_weekly.empty:
                yf_weekly = yf_weekly.merge(fx_weekly, on='date', how='left')
            else:
                yf_weekly['usd_jpy'] = float('nan')

            # Forward-fill missing metals & FX from last WB values
            last_wb = wb_merged.iloc[-1]
            for c in list(METAL_COLS.values()) + ['usd_jpy']:
                if c in yf_weekly.columns:
                    yf_weekly[c] = yf_weekly[c].fillna(last_wb.get(c))
                else:
                    yf_weekly[c] = last_wb.get(c)

            yf_weekly = convert_to_jpy(yf_weekly)

            # WB の最終日付以降の YF データだけ追加 (重複回避)
            wb_last = wb_merged['date'].max()
            yf_new = yf_weekly[yf_weekly['date'] > wb_last].copy()
            print(f"[metals]   YF new rows after {wb_last.date()}: {len(yf_new)}")

            out = pd.concat([wb_merged, yf_new], ignore_index=True)
        else:
            out = wb_merged

        out = out.sort_values('date').reset_index(drop=True)
        out['date'] = out['date'].dt.strftime('%Y-%m-%d')

        cols = ['date', 'usd_jpy', 'aluminum', 'copper', 'nickel',
                'lead', 'tin', 'zinc', 'iron_ore']
        out = out[[c for c in cols if c in out.columns]]
        out.to_csv(METALS_CSV, index=False)
        print(f"[metals] OK: {len(out)} rows -> {METALS_CSV}")
        print(f"[metals]   Latest: {out['date'].iloc[-1]}")
        return 0
    except Exception as e:
        print(f"[metals] ERROR: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
