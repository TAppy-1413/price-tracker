"""
JAPIA (日本自動車部品工業会) 指標価格推移 取得スクリプト
ソース: https://www.japia.or.jp/files/user/japia/gyoumu/shihyoukakakusuii.xlsm

提供データ (月次):
  - 鉄鋼: 熱延鋼板・冷延鋼板 (千円/t) 1974年〜
  - アルミ: 新地金・再生塊 (円/kg) 2011年〜
  - 銅・黄銅: 銅建値・亜鉛建値・黄銅1/2/3種 (円/kg) 2002年〜
  - 電気: 10電力会社別 平均販売単価 (円/kWh) 2014年〜
  - 国内トラック便: 軽油価格+サーチャージ 地域別 1990年〜
  - 海外輸出/輸入便: 主要港間 US$/20ft, 40ft 2010年〜

出力: data/japia_*.csv
"""
import pandas as pd
import requests
import io
from xlsx2csv import Xlsx2csv
from pathlib import Path
import sys
import re

DATA_DIR = Path(__file__).parent.parent / "data"
JAPIA_URL = "https://www.japia.or.jp/files/user/japia/gyoumu/shihyoukakakusuii.xlsm"
CACHE_FILE = Path("/tmp/japia.xlsm")


def download_japia():
    print("[japia] Downloading JAPIA Excel...")
    r = requests.get(JAPIA_URL, timeout=120)
    r.raise_for_status()
    CACHE_FILE.write_bytes(r.content)
    print(f"[japia]   Downloaded {len(r.content)} bytes")


def read_sheet(sheet_id):
    """JAPIA Excel から指定シートを CSV 文字列として読み込み"""
    output = io.StringIO()
    x = Xlsx2csv(str(CACHE_FILE), outputencoding='utf-8')
    x.convert(output, sheetid=sheet_id)
    return output.getvalue()


def parse_date(s):
    """JAPIAの日付形式 '1974/01' を 'YYYY-MM-01' に正規化"""
    s = str(s).strip()
    m = re.match(r'(\d{4})/(\d{1,2})', s)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-01"
    # 日付シリアル形式の場合
    m = re.match(r'(\d{2})-(\d{2})-(\d{2})', s)
    if m:
        yy, mm, dd = m.groups()
        year = '20' + yy
        return f"{year}-{mm}-01"
    return None


def fetch_steel():
    """鉄鋼 (sheet 6): 熱延鋼板・冷延鋼板・酸洗コイル 千円/t → 円/kg"""
    csv = read_sheet(6)
    lines = csv.split('\n')
    rows = []
    for line in lines[3:]:  # データは4行目以降
        parts = line.split(',')
        if len(parts) < 4 or not parts[0].strip():
            continue
        d = parse_date(parts[1])
        if not d:
            continue
        try:
            hot_rolled = float(parts[2]) if parts[2].strip() else None
            cold_rolled = float(parts[3]) if parts[3].strip() else None
            # 千円/t = 円/kg (単位変換不要)
            rows.append({'date': d, 'hot_rolled': hot_rolled, 'cold_rolled': cold_rolled})
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows)


def fetch_aluminum():
    """アルミ (sheet 8): 新地金・再生塊 円/kg"""
    csv = read_sheet(8)
    lines = csv.split('\n')
    rows = []
    for line in lines[3:]:
        parts = line.split(',')
        if len(parts) < 3 or not parts[0].strip():
            continue
        d = parse_date(parts[1])
        if not d:
            continue
        try:
            new_ingot = float(parts[2]) if parts[2].strip() else None
            recycled = float(parts[3]) if len(parts) > 3 and parts[3].strip() else None
            rows.append({'date': d, 'al_ingot': new_ingot, 'al_recycled': recycled})
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows)


def fetch_copper_brass():
    """銅・黄銅 (sheet 7): 銅・亜鉛・黄銅1-3種 円/kg"""
    csv = read_sheet(7)
    lines = csv.split('\n')
    rows = []
    for line in lines[3:]:
        parts = line.split(',')
        if len(parts) < 3 or not parts[0].strip():
            continue
        d = parse_date(parts[1])
        if not d:
            continue
        try:
            copper = float(parts[2]) if parts[2].strip() else None
            zinc = float(parts[3]) if len(parts) > 3 and parts[3].strip() else None
            brass1 = float(parts[4]) if len(parts) > 4 and parts[4].strip() else None
            rows.append({'date': d, 'copper': copper, 'zinc': zinc, 'brass': brass1})
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows)


def fetch_electricity_by_company():
    """電気 (sheets 22-31): 10電力会社
    燃料費調整単価+再エネ賦課金 (col 6) + 基本料金(12円) で総額推定
    """
    # 22:北海道 23:東北 24:東京 25:中部 26:北陸 27:関西 28:中国 29:四国 30:九州 31:沖縄
    companies = {
        22: 'hokkaido', 23: 'tohoku', 24: 'tepco', 25: 'chubu',
        26: 'hokuriku', 27: 'kansai', 28: 'chugoku', 29: 'shikoku',
        30: 'kyushu', 31: 'okinawa',
    }
    BASE_PRICE = 12.0  # 2020年頃の基本料金目安 円/kWh
    all_rows = {}
    for sid, col in companies.items():
        try:
            csv = read_sheet(sid)
        except Exception as e:
            print(f"[japia]   electricity sheet {sid} failed: {e}")
            continue
        lines = csv.split('\n')
        for line in lines[2:]:
            parts = line.split(',')
            if len(parts) < 7:
                continue
            d = parse_date(parts[3])
            if not d:
                continue
            try:
                # 平均販売単価 (col 7) 優先、なければ 燃料費調整+再エネ (col 6) + 基本料金
                price = None
                if len(parts) > 7 and parts[7].strip():
                    price = float(parts[7])
                elif parts[6].strip():
                    price = float(parts[6]) + BASE_PRICE
                if d not in all_rows:
                    all_rows[d] = {'date': d}
                if price is not None:
                    all_rows[d][col] = round(price, 2)
            except (ValueError, IndexError):
                continue
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(list(all_rows.values())).sort_values('date').reset_index(drop=True)
    return df


def fetch_domestic_truck():
    """国内トラック便 (sheet 16): 軽油価格・サーチャージ 地域別"""
    csv = read_sheet(16)
    lines = csv.split('\n')
    rows = []
    # ヘッダー行以降を処理
    for line in lines:
        parts = line.split(',')
        if len(parts) < 4 or parts[0] != '国内トラック便':
            continue
        d = parse_date(parts[1])
        if not d:
            continue
        try:
            # col 2: 全国軽油価格(円/l), col 3: 全国サーチャージ(円/車)
            diesel = float(parts[2]) if parts[2].strip() else None
            surcharge = float(parts[3]) if parts[3].strip() else None
            rows.append({'date': d, 'diesel_national': diesel, 'truck_surcharge': surcharge})
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows)


def fetch_overseas_freight():
    """海外輸出便 (sheet 17): 横浜発主要港着 US$/20ft, 40ft"""
    csv = read_sheet(17)
    lines = csv.split('\n')
    rows = []
    for line in lines[2:]:
        parts = line.split(',')
        if len(parts) < 6 or parts[0] != '海外輸出便':
            continue
        d = parse_date(parts[1])
        if not d:
            continue
        try:
            usa_20 = float(parts[2]) if parts[2].strip() else None
            usa_40 = float(parts[3]) if parts[3].strip() else None
            eu_20 = float(parts[4]) if parts[4].strip() else None
            hk_20 = float(parts[8]) if len(parts) > 8 and parts[8].strip() else None
            rows.append({
                'date': d,
                'export_usa_20ft': usa_20,
                'export_usa_40ft': usa_40,
                'export_eu_20ft': eu_20,
                'export_asia_20ft': hk_20,
            })
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows)


def fetch_minwage_prefecture():
    """最低賃金 (sheet 21): 47都道府県別 年次データ"""
    csv = read_sheet(21)
    lines = csv.split('\n')
    # ヘッダー行 (行index 1)
    header = lines[1].split(',')
    # col 2以降が都道府県
    pref_map = {
        '全国': 'nationwide', '北海道': 'hokkaido', '東京都': 'tokyo',
        '栃木県': 'tochigi', '群馬県': 'gunma', '茨城県': 'ibaraki',
        '埼玉県': 'saitama', '愛知県': 'aichi', '大阪府': 'osaka',
    }
    rows = []
    for line in lines[2:]:
        parts = line.split(',')
        if len(parts) < 3 or not parts[1].strip():
            continue
        # 年の抽出
        year_match = re.match(r'(\d{4})', parts[1].replace('"', ''))
        if not year_match:
            continue
        year = int(year_match.group(1))
        row = {'year': year}
        for i, col_name in enumerate(header):
            col_clean = col_name.strip()
            if col_clean in pref_map:
                key = pref_map[col_clean]
                try:
                    val = parts[i].strip()
                    if val:
                        row[key] = float(val)
                except (ValueError, IndexError):
                    pass
        if len(row) > 1:
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    try:
        download_japia()

        # 1. 鉄鋼
        print("[japia] Parsing steel...")
        steel = fetch_steel()
        steel.to_csv(DATA_DIR / "japia_steel.csv", index=False)
        print(f"[japia]   steel: {len(steel)} rows, latest {steel['date'].iloc[-1] if len(steel) else 'N/A'}")

        # 2. アルミ
        print("[japia] Parsing aluminum...")
        alu = fetch_aluminum()
        alu.to_csv(DATA_DIR / "japia_aluminum.csv", index=False)
        print(f"[japia]   aluminum: {len(alu)} rows")

        # 3. 銅・黄銅
        print("[japia] Parsing copper/brass...")
        cb = fetch_copper_brass()
        cb.to_csv(DATA_DIR / "japia_copper.csv", index=False)
        print(f"[japia]   copper: {len(cb)} rows")

        # 4. 電力 10社
        print("[japia] Parsing electricity by company...")
        elec = fetch_electricity_by_company()
        elec.to_csv(DATA_DIR / "japia_electricity.csv", index=False)
        print(f"[japia]   electricity: {len(elec)} rows")

        # 5. 国内トラック便
        print("[japia] Parsing domestic truck...")
        truck = fetch_domestic_truck()
        truck.to_csv(DATA_DIR / "japia_truck.csv", index=False)
        print(f"[japia]   truck: {len(truck)} rows")

        # 6. 海外輸出便
        print("[japia] Parsing overseas freight...")
        sea = fetch_overseas_freight()
        sea.to_csv(DATA_DIR / "japia_sea.csv", index=False)
        print(f"[japia]   sea: {len(sea)} rows")

        # 7. 最低賃金 都道府県別
        print("[japia] Parsing minimum wage by prefecture...")
        wage = fetch_minwage_prefecture()
        wage.to_csv(DATA_DIR / "japia_wage.csv", index=False)
        print(f"[japia]   wage: {len(wage)} rows")

        return 0
    except Exception as e:
        print(f"[japia] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
