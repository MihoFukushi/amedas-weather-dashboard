# 設計メモ: dbt の使いどころ

このプロジェクトの変換層で使っている dbt の機能と、その対応ファイルの一覧。

| パス | 何をしているか | dbt の機能 |
|---|---|---|
| `models/sources.yml` | gzip JSONL を DB にロードせず直接ソースとして定義 | source、dbt-duckdb の `external_location` |
| `models/staging/stg_amedas__*.sql` | 型変換・改名・品質フラグによる null 化 | staging 層、Jinja の for ループ |
| `models/marts/fct_observations_hourly.sql` | 地点属性を結合した時別ファクト。2 回目以降は直近 1 日だけ再計算 | incremental、`is_incremental()`、delete+insert |
| `models/marts/daily_*.sql` | 地点 × 日、地方 × 日の集計 | `ref()` による依存関係(lineage) |
| `models/marts/rankings_latest_day.sql` | 4 種類のランキングを Jinja で生成して union | Jinja による SQL 生成 |
| `seeds/jma_pref_codes.csv` | 府県番号 → 地方名のマスタ | seed |
| `models/**/schema.yml` | not_null / unique / relationships / accepted_range | generic test、dbt_utils |
| `tests/assert_no_future_observations.sql` | 未来時刻が混入していないか | singular test |
| `macros/generate_schema_name.sql` | スキーマ名を `main_marts` ではなく `marts` にする | 組み込みマクロの上書き |

## 要点

| テーマ | 一文で |
|---|---|
| 設定 | dbt は ELT の T だけを担当し、materialization はフォルダ単位で既定値を与える |
| モデル | select 文だけを書き、create は materialization に任せる |
| Jinja | SQL を知らない文字列生成なので、`dbt compile` で展開結果を必ず確認する |
| lineage | `ref()` を書くだけで依存グラフができ、実行順序は dbt が決める |
| incremental | `is_incremental()` で 1 ファイルを初回用と差分用の 2 通りに展開する |
| テスト | 「失敗行を探す select」で、1 行でも返れば失敗 |
| マクロ | `source()` も `ref()` もマクロで、同名マクロを置けば組み込みを上書きできる |
| 運用 | 外部に見せるのは marts だけ、変更は lineage を見てから、`dbt build` で止める |

## よく使うコマンド

```powershell
dbt compile --select <model>                 # Jinja の展開結果だけ見る(target/compiled)
dbt run --select <model>+                    # モデルとその下流を作り直す
dbt run --select +<model>                    # 上流を含めて作り直す
dbt run --select <model> --full-refresh      # incremental を全件作り直す
dbt test --select <model>                    # 1 モデルのテストだけ
dbt build                                    # seed → model → test を依存順に
dbt show --limit 5 --inline "select ... from {{ ref('x') }}"   # 結果をプレビュー
dbt docs generate; dbt docs serve            # lineage とカタログ
```
