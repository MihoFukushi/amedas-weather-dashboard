"""ダッシュボード各ページで共有する DuckDB 接続・指標定義・地図設定。

DuckDB ファイルの入手先は 2 通り:
- ローカル開発: `dbt build` が data/amedas.duckdb を作る。この場合は何もしない。
- 公開環境(Streamlit Community Cloud など): ファイルが無いので、GitHub Actions が
  Release(タグ data-latest)に上書き公開している amedas.duckdb をダウンロードする。
  ダウンロードしたものには印(.stamp)を付け、6 時間経ったら取り直す。
"""

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "amedas.duckdb"
STAMP_PATH = DB_PATH.with_suffix(".duckdb.stamp")  # ダウンロード由来であることと取得時刻の記録

GITHUB_REPO = "MihoFukushi/amedas-weather-dashboard"
RELEASE_TAG = "data-latest"
ASSET_NAME = "amedas.duckdb"
REFRESH_HOURS = 6


def _secret(name: str, default: str = "") -> str:
    """Streamlit の secrets → 環境変数 の順に設定値を探す。secrets.toml が無くても落とさない。"""
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
        if value:
            return str(value)
    except Exception:  # noqa: BLE001 - secrets 未設定なら環境変数にフォールバック
        pass
    return os.environ.get(name, default)


def _resolve_asset_url(headers: dict[str, str]) -> str:
    """ダウンロード URL を決める。トークンがあれば API 経由(非公開リポジトリ向け)、無ければ公開 URL。"""
    repo = _secret("AMEDAS_GITHUB_REPO", GITHUB_REPO)
    tag = _secret("AMEDAS_RELEASE_TAG", RELEASE_TAG)
    token = _secret("GITHUB_TOKEN")

    if token:
        headers["Authorization"] = f"Bearer {token}"
        api = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        req = urllib.request.Request(api, headers={**headers, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            release = json.load(resp)
        assets = [a for a in release.get("assets", []) if a.get("name") == ASSET_NAME]
        if not assets:
            raise FileNotFoundError(f"Release {tag} に {ASSET_NAME} がありません")
        headers["Accept"] = "application/octet-stream"
        return assets[0]["url"]
    return f"https://github.com/{repo}/releases/download/{tag}/{ASSET_NAME}"


def _download_release_asset(dest: Path) -> None:
    """Release のアセットを一時ファイルに落としてから dest に差し替える。"""
    headers = {"User-Agent": "amedas-dashboard"}
    url = _resolve_asset_url(headers)
    tmp = dest.with_suffix(".duckdb.part")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, dest)
    STAMP_PATH.write_text(json.dumps({"downloaded_at": time.time(), "source": url}))


@st.cache_resource
def _download_lock() -> threading.Lock:
    return threading.Lock()


def _needs_download() -> bool:
    if not DB_PATH.exists():
        return True
    if not STAMP_PATH.exists():
        return False  # dbt build で作ったローカルの DB は触らない
    try:
        downloaded_at = float(json.loads(STAMP_PATH.read_text()).get("downloaded_at", 0))
    except (ValueError, OSError):
        return True
    return time.time() - downloaded_at > REFRESH_HOURS * 3600


def ensure_db() -> None:
    """DuckDB ファイルを用意する。ローカルに無ければ Release から取得し、失敗したらページを止める。"""
    if not _needs_download():
        return
    with _download_lock():
        if not _needs_download():  # 待っている間に別セッションが取得済み
            return
        try:
            with st.spinner("最新の観測データを取得しています…"):
                _download_release_asset(DB_PATH)
            query.clear()
        except Exception as e:  # noqa: BLE001
            if DB_PATH.exists():
                # 古いファイルは残っているので、そのまま表示を続ける
                st.warning(f"データの更新に失敗したため、前回取得分を表示しています({e})")
                return
            st.error(
                "data/amedas.duckdb がありません。ローカルでは先に `dbt build` を実行してください。"
                f"公開環境では GitHub Release({RELEASE_TAG})からの取得に失敗しました: {e}"
            )
            st.stop()


@st.cache_data(ttl=300)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(sql, list(params)).df()


# 時別観測値の指標。色は「大きさ」を表すので単一色相のランプ、気温だけは寒暖の両極を持つ
# 発散型(青 ← 灰 → 赤)を使う。
METRICS: dict[str, dict] = {
    "temperature_c": {"label": "気温", "unit": "℃", "scale": "RdBu_r", "diverging": True},
    "precipitation_1h_mm": {"label": "1時間降水量", "unit": "mm", "scale": "Blues", "diverging": False},
    "wind_speed_ms": {"label": "風速", "unit": "m/s", "scale": "Teal", "diverging": False},
    "humidity_pct": {"label": "湿度", "unit": "%", "scale": "Greens", "diverging": False},
    "pressure_hpa": {"label": "気圧", "unit": "hPa", "scale": "Purp", "diverging": False},
    "sunshine_1h_h": {"label": "日照時間", "unit": "h", "scale": "Oranges", "diverging": False},
}

# 気象庁の 16 方位コード。0 は静穏、16 が北。
WIND_DIRECTIONS = [
    "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南",
    "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西", "北",
]


def japan_geo() -> dict:
    """日本全体が収まる Plotly の geo レイアウト。タイルサーバー不要で動く。"""
    return {
        "scope": "asia",
        "resolution": 50,
        "projection_type": "mercator",
        "lataxis_range": [23.5, 46.5],
        "lonaxis_range": [122.0, 150.0],
        "showland": True,
        "landcolor": "#efede8",
        "showocean": True,
        "oceancolor": "#f9f9f8",
        "showcountries": False,
        "showcoastlines": True,
        "coastlinecolor": "#c9c6bd",
        "coastlinewidth": 0.6,
        "showlakes": False,
        "bgcolor": "rgba(0,0,0,0)",
    }


def observed_hours() -> pd.Series:
    """観測時刻の一覧(昇順)。"""
    df = query("select distinct observed_at from marts.fct_observations_hourly order by 1")
    return df["observed_at"]


def fmt_ts(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{ts.month}/{ts.day} {ts.hour:02d}時"


def color_range(values: pd.Series, diverging: bool) -> tuple[float, float, float | None]:
    """外れ値で色が潰れないよう 1〜99 パーセンタイルで色の範囲を決める。

    発散型は中央値を中心に左右対称の範囲にする(灰色=その期間の典型値)。
    """
    v = values.dropna()
    if v.empty:
        return (0.0, 1.0, None)
    lo, hi = float(v.quantile(0.01)), float(v.quantile(0.99))
    if diverging:
        mid = float(v.median())
        half = max(hi - mid, mid - lo, 0.5)
        return (mid - half, mid + half, mid)
    if hi <= lo:
        hi = lo + 1.0
    return (lo, hi, None)
