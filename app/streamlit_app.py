"""dbt が作った DuckDB の marts を眺める簡易ダッシュボード。

    streamlit run app/streamlit_app.py
"""

from pathlib import Path

import duckdb
import pandas as pd
import pydeck as pdk
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "amedas.duckdb"

st.set_page_config(page_title="AMeDAS ELT", layout="wide")
st.title("AMeDAS オープンデータ ELT ダッシュボード")

if not DB_PATH.exists():
    st.error("data/amedas.duckdb がありません。先に `dbt build` を実行してください。")
    st.stop()


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(sql).df()


rankings = query("select * from marts.rankings_latest_day order by ranking_type, ranking")
latest_date = rankings["observation_date"].max() if not rankings.empty else None
st.caption(f"直近観測日: {latest_date}")

labels = {
    "hottest": "最高気温 (℃)",
    "coldest": "最低気温 (℃)",
    "wettest": "日降水量 (mm)",
    "windiest": "最大風速 (m/s)",
}
cols = st.columns(4)
for col, (key, label) in zip(cols, labels.items()):
    with col:
        st.subheader(label)
        df = rankings[rankings["ranking_type"] == key][
            ["ranking", "station_name", "pref_name", "metric_value"]
        ]
        st.dataframe(df, hide_index=True, use_container_width=True)

st.divider()
st.subheader("地方別の気温推移")

prefs = query("select distinct pref_code, pref_name from marts.daily_pref_weather order by pref_code")
selected = st.multiselect(
    "地方を選択", prefs["pref_name"].tolist(), default=["東京都", "大阪府", "石狩地方", "沖縄本島地方"]
)
if selected:
    in_list = ", ".join(f"'{p}'" for p in selected)
    df = query(
        f"""
        select observation_date, pref_name, temp_max_c, temp_min_c, temp_avg_c, precipitation_avg_mm
        from marts.daily_pref_weather
        where pref_name in ({in_list})
        order by observation_date
        """
    )
    st.line_chart(df.pivot(index="observation_date", columns="pref_name", values="temp_max_c"))
    st.dataframe(df, hide_index=True, use_container_width=True)

st.divider()
st.subheader("地点マップ(直近日の最高気温)")
st.caption("点の色が気温(青=低い、赤=高い)。点にカーソルを当てると地点名と気温が出る。")
points = query(
    """
    select latitude, longitude, station_name, pref_name, temp_max_c, is_complete_day
    from marts.daily_station_weather
    where observation_date = (select max(observation_date) from marts.daily_station_weather)
      and temp_max_c is not null
    """
)

if points.empty:
    st.info("表示できる地点がありません。")
else:
    # 気温を 0〜1 に正規化して青(低)→赤(高)のグラデーションにする
    t_min, t_max = points["temp_max_c"].min(), points["temp_max_c"].max()
    span = (t_max - t_min) or 1.0
    ratio = (points["temp_max_c"] - t_min) / span
    points["r"] = (ratio * 255).astype(int)
    points["g"] = 60
    points["b"] = ((1 - ratio) * 255).astype(int)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position="[longitude, latitude]",
        get_fill_color="[r, g, b, 200]",
        get_radius=8000,
        radius_min_pixels=3,
        radius_max_pixels=12,
        pickable=True,
    )
    view = pdk.ViewState(latitude=36.5, longitude=137.5, zoom=4.3)
    tooltip = {"text": "{station_name}({pref_name})\n最高気温 {temp_max_c} ℃"}
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip=tooltip, map_style=None))

    c1, c2, c3 = st.columns(3)
    c1.metric("地点数", len(points))
    c2.metric("全国最高", f"{t_max:.1f} ℃")
    c3.metric("全国最低(の最高気温)", f"{t_min:.1f} ℃")
    if not points["is_complete_day"].all():
        st.caption("直近日はまだ 24 時間分そろっていないため、途中までの最高気温です。")
