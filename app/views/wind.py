"""風の地図と風配図。

- 風の地図: 選んだ時刻の全地点の風を矢印で描く。矢印は風が吹いていく向き、大きさと色が風速。
- 風配図: 1 地点について、期間中にどの向きから・どれくらいの強さの風が吹いたかを 16 方位で積み上げる。
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import WIND_DIRECTIONS, ensure_db, fmt_ts, japan_geo, observed_hours, query

ensure_db()
st.title("風の地図と風配図")

hours = observed_hours()
if hours.empty:
    st.info("観測値がありません。")
    st.stop()

# ---------------------------------------------------------------- 風の地図
st.subheader("風の地図")
st.caption("矢印は風が吹いていく向き。大きさと色が風速(濃いほど強い)。静穏(風向なし)は小さな点。")

ts = st.select_slider("時刻", options=list(hours), value=hours.iloc[-1], format_func=fmt_ts)

wind = query(
    """
    select station_name, pref_name, latitude, longitude, wind_speed_ms, wind_direction_code
    from marts.fct_observations_hourly
    where observed_at = ? and wind_speed_ms is not null and wind_direction_code is not null
    """,
    (pd.Timestamp(ts).to_pydatetime(),),
)

if wind.empty:
    st.info("この時刻の風の観測値がありません。")
else:
    calm = wind["wind_direction_code"] == 0
    # 16 方位コードは 1=北北東 … 16=北。風向は「吹いてくる向き」なので矢印は 180° 反転させる。
    heading = (wind["wind_direction_code"] * 22.5 + 180.0) % 360.0
    speed_cap = max(float(wind["wind_speed_ms"].quantile(0.99)), 1.0)
    size = 5.0 + 13.0 * np.sqrt(np.clip(wind["wind_speed_ms"] / speed_cap, 0, 1.2))
    dir_label = wind["wind_direction_code"].map(
        lambda c: "静穏" if c == 0 else WIND_DIRECTIONS[int(c) - 1]
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scattergeo(
            lat=wind.loc[~calm, "latitude"],
            lon=wind.loc[~calm, "longitude"],
            mode="markers",
            marker={
                "symbol": "arrow",
                "angle": heading[~calm],
                "angleref": "up",
                "size": size[~calm],
                "color": wind.loc[~calm, "wind_speed_ms"],
                "colorscale": "Teal",
                "cmin": 0,
                "cmax": speed_cap,
                "colorbar": {"title": "m/s", "thickness": 12, "len": 0.6, "x": 0.98},
                "opacity": 0.85,
                "line": {"width": 0},
            },
            customdata=np.stack(
                [
                    wind.loc[~calm, "station_name"],
                    wind.loc[~calm, "pref_name"],
                    wind.loc[~calm, "wind_speed_ms"],
                    dir_label[~calm],
                ],
                axis=1,
            ),
            hovertemplate="<b>%{customdata[0]}</b>(%{customdata[1]})<br>"
            "%{customdata[3]}の風 %{customdata[2]:.1f} m/s<extra></extra>",
            name="風",
        )
    )
    fig.add_trace(
        go.Scattergeo(
            lat=wind.loc[calm, "latitude"],
            lon=wind.loc[calm, "longitude"],
            mode="markers",
            marker={"size": 4, "color": "#b5b2a8", "opacity": 0.7},
            customdata=np.stack([wind.loc[calm, "station_name"], wind.loc[calm, "pref_name"]], axis=1),
            hovertemplate="<b>%{customdata[0]}</b>(%{customdata[1]})<br>静穏<extra></extra>",
            name="静穏",
        )
    )
    fig.update_geos(**japan_geo())
    fig.update_layout(height=700, margin={"l": 0, "r": 0, "t": 10, "b": 0}, showlegend=False)
    st.plotly_chart(fig, width="stretch", config={"scrollZoom": False, "displayModeBar": False})

    strongest = wind.sort_values("wind_speed_ms", ascending=False).head(5)
    c1, c2, c3 = st.columns(3)
    c1.metric("観測地点数", len(wind))
    c2.metric("静穏の地点", int(calm.sum()))
    top = strongest.iloc[0]
    c3.metric("最大風速", f"{top['wind_speed_ms']:.1f} m/s", help=f"{top['station_name']}({top['pref_name']})")

    with st.expander("風の強い地点(上位 5)"):
        st.dataframe(
            strongest.assign(風向=dir_label[strongest.index])[
                ["station_name", "pref_name", "風向", "wind_speed_ms"]
            ].rename(columns={"station_name": "地点", "pref_name": "府県", "wind_speed_ms": "風速 (m/s)"}),
            hide_index=True,
            width="stretch",
        )

st.divider()

# ---------------------------------------------------------------- 風配図
st.subheader("風配図(期間中の風向別の出現回数)")
st.caption("外側に長いほどその向きからの風が多い。色の濃さは風速の階級。")

stations = query(
    """
    select station_id, station_name, pref_name, count(wind_direction_code) as n
    from marts.fct_observations_hourly
    where wind_direction_code is not null
    group by all
    having count(wind_direction_code) >= 12
    order by pref_name, station_name
    """
)
if stations.empty:
    st.info("風配図を描ける地点がありません。")
    st.stop()

stations["label"] = stations["station_name"] + "(" + stations["pref_name"] + ")"
default_idx = int(stations.index[stations["station_name"] == "東京"][0]) if (stations["station_name"] == "東京").any() else 0
picked = st.selectbox("地点", stations["label"], index=default_idx)
station_id = stations.loc[stations["label"] == picked, "station_id"].iloc[0]

obs = query(
    """
    select wind_speed_ms, wind_direction_code
    from marts.fct_observations_hourly
    where station_id = ? and wind_direction_code is not null and wind_speed_ms is not null
    """,
    (station_id,),
)

calm_n = int((obs["wind_direction_code"] == 0).sum())
obs = obs[obs["wind_direction_code"] > 0].copy()

# 風速階級(m/s)。同じ色相(Teal)の濃淡で強さの順序を表す。
classes = [(0, 2, "0〜2", "#b2dfdb"), (2, 4, "2〜4", "#4db6ac"), (4, 6, "4〜6", "#00897b"), (6, 99, "6 以上", "#004d40")]
# 北(コード 16)を先頭にして時計回りに並べる
code_order = [16] + list(range(1, 16))
theta = [WIND_DIRECTIONS[c - 1] for c in code_order]

rose = go.Figure()
for lo, hi, name, color in classes:
    sub = obs[(obs["wind_speed_ms"] >= lo) & (obs["wind_speed_ms"] < hi)]
    counts = sub.groupby("wind_direction_code").size().reindex(code_order, fill_value=0)
    rose.add_trace(
        go.Barpolar(
            r=counts.values,
            theta=theta,
            name=f"{name} m/s",
            marker={"color": color, "line": {"color": "#ffffff", "width": 1}},
            hovertemplate="%{theta} %{r} 回<extra>" + name + " m/s</extra>",
        )
    )
rose.update_layout(
    height=520,
    margin={"l": 40, "r": 40, "t": 30, "b": 30},
    legend={"orientation": "h", "y": -0.05, "x": 0.5, "xanchor": "center", "title": "風速"},
    polar={
        "barmode": "stack",
        "bargap": 0.08,
        "angularaxis": {
            "direction": "clockwise",
            "rotation": 90,  # 先頭の「北」を真上に
            "categoryorder": "array",
            "categoryarray": theta,
            "gridcolor": "#e4e2dc",
        },
        "radialaxis": {
            "showticklabels": True,
            "gridcolor": "#e4e2dc",
            "ticksuffix": " 回",
            "angle": 90,
            "tickfont": {"size": 10, "color": "#6f6d66"},
        },
        "bgcolor": "rgba(0,0,0,0)",
    },
)

c1, c2 = st.columns([3, 2])
with c1:
    st.plotly_chart(rose, width="stretch", config={"displayModeBar": False})
with c2:
    total = len(obs) + calm_n
    if len(obs):
        mode_code = int(obs["wind_direction_code"].mode().iloc[0])
        st.metric("最多風向", WIND_DIRECTIONS[mode_code - 1])
        st.metric("平均風速", f"{obs['wind_speed_ms'].mean():.1f} m/s")
        st.metric("最大風速", f"{obs['wind_speed_ms'].max():.1f} m/s")
    st.metric("静穏の割合", f"{calm_n / total * 100:.0f} %" if total else "-")
    st.caption(f"観測時間数 {total}(うち静穏 {calm_n})")

    tbl = (
        obs.assign(風向=obs["wind_direction_code"].map(lambda c: WIND_DIRECTIONS[int(c) - 1]))
        .groupby("風向")
        .agg(回数=("wind_speed_ms", "size"), 平均風速=("wind_speed_ms", "mean"))
        .reindex(WIND_DIRECTIONS)
        .dropna()
        .round(1)
        .sort_values("回数", ascending=False)
    )
    with st.expander("数値で見る"):
        st.dataframe(tbl, width="stretch")
