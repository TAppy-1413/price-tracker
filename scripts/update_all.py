"""
全データソース更新の統括スクリプト
GitHub Actions から毎日実行される
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

SCRIPTS = [
    'fetch_metals.py',
    'fetch_sppi.py',
    'fetch_diesel.py',
    'fetch_minwage.py',
    'fetch_electricity.py',
]

SCRIPT_DIR = Path(__file__).parent


def run_one(name: str) -> int:
    path = SCRIPT_DIR / name
    print(f"\n{'='*60}\n[update_all] Running {name}\n{'='*60}")
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=False,
    )
    return result.returncode


def build_manifest():
    """
    data/ 以下のCSVから最新値と更新日時を集計し、
    docs/data/manifest.json に書き出す。
    フロントエンドがこれを読んで「最終更新日」を表示。
    """
    import json
    import pandas as pd
    from datetime import datetime, timezone, timedelta

    DATA = SCRIPT_DIR.parent / "data"
    DOCS_DATA = SCRIPT_DIR.parent / "docs" / "data"
    DOCS_DATA.mkdir(parents=True, exist_ok=True)

    manifest = {
        'generated_at': datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M JST'),
        'sources': {},
    }

    for csv in sorted(DATA.glob('*.csv')):
        try:
            df = pd.read_csv(csv)
            if 'date' in df.columns and len(df) > 0:
                latest = str(df['date'].iloc[-1])
            elif 'year' in df.columns and len(df) > 0:
                latest = str(df['year'].iloc[-1])
            else:
                latest = 'n/a'
            manifest['sources'][csv.stem] = {
                'rows': len(df),
                'latest': latest,
            }
            # Also copy to docs/data for frontend access
            df.to_csv(DOCS_DATA / csv.name, index=False)
        except Exception as e:
            print(f"[manifest] skip {csv.name}: {e}")

    with open(DOCS_DATA / 'manifest.json', 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n[manifest] wrote {DOCS_DATA/'manifest.json'}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def main():
    print(f"[update_all] Started at {datetime.now().isoformat()}")
    for s in SCRIPTS:
        run_one(s)
    build_manifest()
    print("\n[update_all] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
