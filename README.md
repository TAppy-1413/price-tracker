# IKS 価格高騰トラッカー

原材料・人件費・運賃の長期推移を毎日自動更新するダッシュボード。
契約見直し・機械チャージ改定の根拠資料として、社員の物価実感共有用として使用。

**公開URL (セットアップ後):** `https://ryusei-iks.github.io/price-tracker/`

---

## 何ができるか

- **金属価格**: アルミ・銅・ニッケル・鉄鉱石・鉛・錫・亜鉛 の 2000年〜現在の月次推移 (円/kg換算)
- **難削材代理指標**: ニッケル(インコネル系主成分)・錫・亜鉛を合金参考値として表示
- **最低賃金**: 栃木・群馬・茨城・埼玉・東京・愛知・大阪・全国平均 の 2000年〜現在の年次推移
- **運賃指数**: 日銀SPPI 道路貨物輸送 (2000年〜現在の月次)
- **実価格 / 2000年=100 指数** の切替表示
- **期間絞り込み** (全期間 / 10年 / 5年 / 3年 / 1年)
- **サマリーテーブル**: 主要項目の2000年→最新の上昇率一覧
- **毎日 9:00 JST 自動更新** (GitHub Actions)

## データソース (すべて無料・公開データ)

| 項目 | ソース | 更新頻度 |
|---|---|---|
| 金属国際価格 | World Bank Commodity Markets (Pink Sheet) | 月次 |
| USD/JPY 為替 | Yahoo Finance | 日次 |
| 企業向けサービス価格指数 (道路貨物輸送) | 日本銀行 時系列統計データ検索サイト | 月次 |
| 最低賃金 (都道府県別) | 厚生労働省 地域別最低賃金の全国一覧 | 年次 (10月) |

---

## セットアップ手順 (GitHub Web UIのみ、約15分)

### ステップ1: 新しいリポジトリを作成

1. ブラウザで https://github.com/new にアクセス
2. 以下を入力:
   - **Repository name**: `price-tracker`
   - **Description**: `IKS 価格高騰トラッカー`
   - **Public** を選択 (Private でも可だが、Public のほうが GitHub Pages が簡単)
   - **「Add a README file」チェックを外す**
3. 「Create repository」をクリック

### ステップ2: ファイルをアップロード

1. 作成されたリポジトリ画面で **「uploading an existing file」** リンクをクリック
2. 本プロジェクトの **すべてのファイル・フォルダ** (`scripts/`, `data/`, `docs/`, `.github/`, `README.md`, `requirements.txt`, `.gitignore`) をまとめてドラッグ&ドロップ
   - フォルダごとドラッグしても正しくアップロードされます
   - `.github` フォルダも忘れず含めてください (隠しフォルダに見える場合があります)
3. 画面下部の **「Commit changes」** をクリック

### ステップ3: GitHub Pages を有効化

1. リポジトリ上部の **「Settings」** タブをクリック
2. 左サイドバーの **「Pages」** をクリック
3. 「Build and deployment」セクションで:
   - **Source**: `Deploy from a branch`
   - **Branch**: `main` / `/docs` フォルダを選択
4. **「Save」** をクリック
5. 1-2分待つと、ページ上部に公開URLが表示されます:
   ```
   https://ryusei-iks.github.io/price-tracker/
   ```

### ステップ4: GitHub Actions の書き込み権限を付与

毎日の自動更新で `data/` を書き換えてコミットするため、権限設定が必要です。

1. **Settings** → **Actions** → **General** を開く
2. ページ下部の **「Workflow permissions」** で:
   - ✅ **「Read and write permissions」** を選択
3. **「Save」** をクリック

### ステップ5: 動作確認

1. リポジトリ上部の **「Actions」** タブをクリック
2. 左側の **「Daily Price Update」** をクリック
3. 右上の **「Run workflow」** → **「Run workflow」** (手動実行)
4. 緑のチェックマークが出れば成功 (約3-5分)
5. 公開URLをブラウザで開いて動作確認

**初回は Settings → Actions → General の下の方にある「Allow all actions and reusable workflows」にも ✅ を入れておくと確実です。**

---

## 社内限定化 (Cloudflare Access で `@iks-web.co.jp` だけに制限)

GitHub Pages は誰でもアクセスできてしまいます。IKSメールを持つ人だけに制限する手順:

### 前提条件

Cloudflare の無料アカウントが必要 (クレカ登録不要、メール認証のみ)。

### 手順

#### 1. Cloudflare アカウント作成
- https://dash.cloudflare.com/sign-up でメール登録

#### 2. 独自ドメインを追加 (例: `iks-dashboard.com`)
- IKSが独自ドメインを持っているならそれを使う。無ければお名前.comなどで年1,000円程度で取得
- Cloudflareの「Websites」→「Add a site」でドメインを追加
- Cloudflare が指示するネームサーバーに切り替え

**独自ドメインを使いたくない場合**: Cloudflare Pages を使う代替ルートがあります (後述)

#### 3. Cloudflare Pages でデプロイ
- Cloudflare ダッシュボード → **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**
- GitHub連携を承認し、`price-tracker` リポジトリを選択
- Build settings:
  - Build command: (空欄でOK)
  - Build output directory: `docs`
- **Save and Deploy**

#### 4. Cloudflare Access でメール制限
- **Zero Trust** ダッシュボード → **Access** → **Applications** → **Add an application** → **Self-hosted**
- 設定:
  - Application name: `IKS Price Tracker`
  - Session Duration: `24 hours`
  - Application domain: Pages のドメイン (例: `price-tracker.pages.dev`)
- **Next** → **Add a policy**:
  - Policy name: `IKS employees`
  - Action: `Allow`
  - **Configure rules**:
    - Selector: `Emails ending in`
    - Value: `@iks-web.co.jp`
- **Next** → **Add application**

これで `@iks-web.co.jp` のメールアドレスを持つ人だけが、メール認証ワンタイムコード経由でアクセスできるようになります。**Cloudflare Access の無料枠は50ユーザーまで**なので IKS 全社員 (約100名) でもほぼ無料で運用可能 (超過分のみ有料)。

> **無料枠内に収めたい場合**: アクセスを管理職・経営企画部のみ (50名未満) に絞るか、ユーザー追加課金 ($3/user/月) を許容する選択となります。

---

## ファイル構成

```
price-tracker/
├── .github/workflows/
│   └── daily-update.yml        # 毎日 9:00 JST 自動実行
├── scripts/
│   ├── fetch_metals.py         # World Bank + Yahoo Finance
│   ├── fetch_sppi.py           # 日銀 SPPI
│   ├── fetch_diesel.py         # 資源エネ庁 (スケルトン)
│   ├── fetch_minwage.py        # 厚労省 (年1回チェック)
│   └── update_all.py           # 全スクリプト統括 + manifest生成
├── data/                       # 生データCSV (git履歴で全変更追跡)
│   ├── metals.csv              # 2000年〜現在, 月次, 円/kg換算済み
│   ├── sppi.csv                # 2000年〜現在, 月次, 指数
│   ├── min_wage.csv            # 2000年〜現在, 年次, 円/時
│   └── diesel.csv              # 初回空
├── docs/                       # GitHub Pages公開フォルダ
│   ├── index.html              # ダッシュボード
│   ├── style.css
│   ├── app.js                  # Chart.js ロジック
│   └── data/                   # フロントエンドから読む複製CSV
├── requirements.txt
├── .gitignore
└── README.md
```

---

## データの信頼性

- **World Bank Pink Sheet**: 世界銀行が月次で公表する公式コモディティ価格。LME・COMEXなどの公開価格を基に算出。1960年から連続データ。
- **日銀 SPPI**: 日本銀行が毎月公表する公的統計。2000年=100ではなく2020年=100だが、本ダッシュボードは基準年を意識せず相対変動を見るため問題なし。
- **厚労省 最低賃金**: 毎年10月に改定。本リポジトリの seed データは厚労省公式の「地域別最低賃金の全国一覧」から手動で記録した値。

すべて一次ソース (aggregators を経由しない政府・国際機関の直接データ) です。社内外の資料として引用可能です。

---

## 契約見直し資料としての使い方

1. **特定契約の締結月の価格を確認**: サマリータブか金属タブを開き、契約月を含む年にマウスオーバー
2. **現在値との差分を計算**: サマリータブの「上昇率」列が自動計算
3. **スクリーンショット or CSV出力**: CSVは `https://ryusei-iks.github.io/price-tracker/data/metals.csv` などから直接ダウンロード可能
4. **機械チャージ改定根拠**: 電気代 + 最低賃金上昇 + 運賃指数の3点セットで「インフラコスト+13%」などの説明ロジックを組める

---

## トラブルシューティング

### GitHub Actions が失敗する
- 「Settings → Actions → General → Workflow permissions」が **Read and write** になっているか確認
- ログを Actions タブで確認。一時的なネットワーク障害なら翌日には復旧

### グラフが表示されない
- ブラウザの開発者ツール (F12) の Console を確認
- 初回セットアップ直後は `docs/data/` にファイルが無い可能性 → Actions を手動実行してから再アクセス

### World Bank Pink Sheet のURL が変わった
- 世界銀行は年1回程度 URL を変更します。`scripts/fetch_metals.py` の `PINK_SHEET_URL` を最新版に更新してください
- 最新URLの探し方: https://www.worldbank.org/en/research/commodity-markets → "Monthly prices" の Excel リンク

---

## 今後の拡張候補

- 電気代 (高圧業務用) - 経産省エネ庁 電力調査統計から取得
- 軽油価格 (資源エネ庁 週次) の本格実装
- 毎月勤労統計 (e-Stat API 要APIキー登録)
- USGS から チタン・モリブデン・コバルト (難削材強化)
- 銘柄別鋼材価格 (日本鉄鋼連盟 月次報)
- Slack/Teams への週次サマリー自動投稿
- 契約履歴CSVを読み込んで「契約時→現在」の影響を計算

---

## ライセンス

本リポジトリのコードはIKS社内利用を想定。データソースはそれぞれの利用規約に従います。

---

**管理**: IKS 経営企画部 / Ryusei Ishii
