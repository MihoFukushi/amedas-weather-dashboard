# AMeDAS 気象ダッシュボード

気象庁 AMeDAS の時別観測値を毎日自動で取り込み、全国約 1,300 地点の気温・降水量・風速を
地点別・地方別に集計して可視化するダッシュボードです。

- **コマ送りマップ**: 全地点の時別観測値(気温・降水・風速・湿度・気圧・日照)を 1 時間ごとに再生。
  夜明けとともに気温が上がる波や、雨雲の帯が動く様子が見える
- **風の地図と風配図**: 任意の時刻の風を矢印(向き・強さ)で全国に描く。1 地点の 16 方位 × 風速階級の風配図
- **気温の断面図**: 緯度帯 × 時刻のヒートマップ、標高 × 気温の散布図から推定する気温減率(℃/km)とその時間変化、
  府県内の全地点 × 時刻のヒートマップ

データ取得から集計、品質チェック、公開までを GitHub Actions で毎日自動実行します。
外部サービスの契約や API キーは不要です。

## アーキテクチャ

```
気象庁 AMeDAS(JSON)
      │  scripts/extract_amedas.py(毎日の差分取得)
      ▼
data/raw/amedas/*.jsonl.gz(生データ。git で履歴を保持)
      │  dbt + DuckDB(型変換 → 地点マスタ結合 → 日次集計 → 品質テスト)
      ▼
data/amedas.duckdb(marts スキーマ)
      │
      ▼
app/streamlit_app.py(ダッシュボード。ページは app/views/ に 1 ファイルずつ)
```

| 層 | 役割 |
|---|---|
| 取得 | 気象庁サイトの JSON を時刻ごとに保存。取得済みの時刻はスキップ |
| 変換 | dbt が DuckDB 上で staging(整形)→ marts(集計)を構築 |
| 検証 | 主キーの一意性、値域、参照整合性など 34 件の自動テスト |
| 可視化 | Streamlit + Plotly が marts を読み取って表示 |

## データソース

| 内容 | URL |
|---|---|
| 観測地点マスタ | `https://www.jma.go.jp/bosai/amedas/const/amedastable.json` |
| 時別観測値(全地点) | `https://www.jma.go.jp/bosai/amedas/data/map/YYYYMMDDHH0000.json` |

気象庁サイトの表示用 JSON を利用しています。取得間隔を空け、個人利用の範囲で使用してください。

## セットアップ

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
dbt deps
```

## 実行

```powershell
# 1. データ取得(直近 3 日分)
python scripts/extract_amedas.py --days 3

# 2. 集計とテスト
dbt build

# 3. ダッシュボード起動
streamlit run app/streamlit_app.py
```

データリネージと各テーブルの定義は `dbt docs generate; dbt docs serve` で参照できます。

## 提供テーブル(marts スキーマ)

| テーブル | 粒度 | 主な列 |
|---|---|---|
| `fct_observations_hourly` | 地点 × 時刻 | 気温、湿度、降水量、風速、気圧、日照、積雪 |
| `daily_station_weather` | 地点 × 日 | 最高/最低/平均気温、日降水量、最大風速、日照時間、`is_complete_day` |
| `daily_pref_weather` | 地方 × 日 | 地方内の最高/最低気温、平均降水量、最高気温地点名 |
| `rankings_latest_day` | ランキング種別 × 順位 | 直近日の全国上位 10 地点 |

品質フラグが正常・準正常以外の観測値は null として扱います。
`is_complete_day` が false の日は 24 時間分の観測がそろっていない途中集計です。

## 自動実行(GitHub Actions)

`.github/workflows/daily_elt.yml` が毎日 12:00 JST に次を実行します。

1. 直近 2 日分の観測値を取得し、生データの差分を git にコミット
2. `dbt build` で集計と品質テストを実行
3. DuckDB ファイルを Artifact として 7 日間保存し、Release `data-latest` にも上書き公開
4. データカタログ(dbt docs)を GitHub Pages に公開

利用にはリポジトリ設定で Pages の Source を **GitHub Actions** に、Workflow permissions を
**Read and write** にしてください。Pages を使わない場合は `deploy-docs` ジョブを削除します。

## Web 公開(Streamlit Community Cloud)

[share.streamlit.io](https://share.streamlit.io) でこのリポジトリと `app/streamlit_app.py` を指定するとそのまま公開できます。

公開環境には `dbt build` で作る DuckDB が無いので、アプリは起動時に Release `data-latest` の
`amedas.duckdb` をダウンロードして使います(6 時間経つと取り直し)。Release は上記ワークフローが毎日更新します。
ローカルに `dbt build` で作った DuckDB がある場合はそちらを優先し、ダウンロードはしません。

リポジトリが非公開の場合は、Streamlit の Secrets に `GITHUB_TOKEN`(repo 読み取り権限)を設定してください。
別リポジトリやタグから取得する場合は `AMEDAS_GITHUB_REPO`、`AMEDAS_RELEASE_TAG` で上書きできます。

## ディレクトリ構成

```
models/staging/   生データの型変換・改名・品質フラグ処理(view)
models/marts/     集計テーブル(table / incremental)
seeds/            府県コードと地方名の対応表
tests/            個別の整合性テスト
macros/           スキーマ命名の調整
scripts/          データ取得、DuckDB への問い合わせ補助
app/              ダッシュボード(streamlit_app.py がページを登録、views/ に各ページ、common.py に共通処理)
app/              Streamlit ダッシュボード
docs/             設計メモ
```

## 今後の拡張候補

- 地点マスタの変更履歴の保持(dbt snapshot)
- 気象庁の予報 JSON を追加し、予報と実況の比較テーブルを作成
- DuckDB から MotherDuck への移行によるクラウド共有
