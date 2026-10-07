# amedas-elt

気象庁 AMeDAS のオープンデータを題材にした、**dbt を学ぶための ELT パイプライン**。
全部無料(dbt Core + DuckDB + GitHub Actions)で動く。

```
気象庁 AMeDAS API ──▶ scripts/extract_amedas.py ──▶ data/raw/amedas/*.jsonl.gz
                                                          │
                                   dbt-duckdb が外部ファイルとして直接読む
                                                          ▼
                     staging(view) ──▶ marts(table / incremental) ──▶ tests / docs
                                                          │
                                                          ▼
                                            app/streamlit_app.py で可視化
```

## データソース

| 内容 | URL | 備考 |
|---|---|---|
| 観測地点マスタ | `https://www.jma.go.jp/bosai/amedas/const/amedastable.json` | 約1,300地点 |
| 時別観測値(全地点) | `https://www.jma.go.jp/bosai/amedas/data/map/YYYYMMDDHH0000.json` | 過去10日ほど取得可能 |

API キー不要。気象庁の公式 API ではなくサイト用の JSON なので、個人利用の範囲で間隔を空けて取得する。

## セットアップ

```powershell
cd C:\Users\fukus\dev\amedas-elt
python -m venv .venv
& .\.venv\Scripts\Activate.ps1     # ターミナルを開くたびに実行する
pip install -r requirements.txt
dbt deps
```

プロジェクトは Google Drive の外(ローカル)に置く。仮想環境(.venv)は数万ファイルになるので、
Drive 同期フォルダの中に作ると同期が重くなりロックエラーの原因になる。

## 実行

```powershell
# 1. 抽出(直近3日分。保存済みの時刻はスキップするので何度実行してもOK)
python scripts/extract_amedas.py --days 3

# 2. 変換 + テスト(seed → run → test を依存順に実行)
dbt build

# 3. 可視化
streamlit run app/streamlit_app.py

# ドキュメント(lineage グラフが見られる)
dbt docs generate
dbt docs serve
```

`profiles.yml` をプロジェクト直下に置いているので、`~/.dbt/profiles.yml` は不要。

## プロジェクト構成と dbt の学びどころ

| パス | 何をしているか | dbt の機能 |
|---|---|---|
| `models/sources.yml` | gzip JSONL を DB にロードせず直接ソースとして定義 | source, dbt-duckdb の `external_location` |
| `models/staging/stg_amedas__*.sql` | 型変換・改名・品質フラグによる null 化 | staging 層、Jinja の for ループ |
| `models/marts/fct_observations_hourly.sql` | 地点属性を結合した時別ファクト。2回目以降は直近1日だけ再計算 | incremental, `is_incremental()`, `delete+insert` |
| `models/marts/daily_*.sql` | 地点 × 日、地方 × 日の集計 | ref による依存関係(lineage) |
| `models/marts/rankings_latest_day.sql` | 4種類のランキングを Jinja で生成して union | Jinja マクロ的な書き方 |
| `seeds/jma_pref_codes.csv` | 府県番号 → 地方名のマスタ | seed |
| `models/**/schema.yml` | not_null / unique / relationships / accepted_range | generic test, dbt_utils |
| `tests/assert_no_future_observations.sql` | 未来時刻が混入していないか | singular test |
| `macros/generate_schema_name.sql` | スキーマ名を `main_marts` ではなく `marts` にする | マクロのオーバーライド |

## marts の中身

- `marts.fct_observations_hourly`: 地点 × 時刻。気温・湿度・降水量・風速・気圧・日照・積雪
- `marts.daily_station_weather`: 地点 × 日。最高/最低/平均気温、日降水量、最大風速、日照時間
- `marts.daily_pref_weather`: 地方 × 日。地方内の最高気温地点名つき
- `marts.rankings_latest_day`: 直近日の全国ランキング(最高気温・最低気温・降水量・最大風速)上位10

## 毎日自動で動かす(GitHub Actions)

`.github/workflows/daily_elt.yml` が毎日 12:00 JST に

1. 直近2日分を抽出して `data/raw` の差分を git にコミット(無料のデータ蓄積先として git を使う)
2. `dbt build` でテストまで実行
3. DuckDB ファイルを Artifact として保存(7日)
4. `dbt docs` を GitHub Pages に公開

Pages を使う場合はリポジトリの Settings → Pages → Source を **GitHub Actions** にする。
不要なら `deploy-docs` ジョブと Pages 関連の step を削除すればよい。

## 次のステップ案

- `dbt snapshot` で地点マスタの変更履歴(SCD Type 2)を取る
- `exposures` を定義して Streamlit アプリを lineage に載せる
- 気象庁の予報 JSON(`bosai/forecast`)を追加ソースにして「予報 vs 実況」のモデルを作る
- DuckDB → MotherDuck(無料枠)に切り替えてクラウド DWH を体験する
