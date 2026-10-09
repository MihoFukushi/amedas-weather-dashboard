"""コマ送りマップ: 全国約 1,300 地点の時別観測値を 1 時間ごとのフレームで再生する。

夜明けとともに気温が南から・東から上がっていく様子や、雨雲の帯が移動する様子が見える。
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import METRICS, color_range, ensure_db, fmt_ts, japan_geo, query

ensure_db()
st.title("コマ送りマップ")
st.caption("▶ を押すと 1 時間ずつ進む。スライダーで任意の時刻に飛べる。点にカーソルを当てると地点名と値が出る。")

c1, c2 = st.columns([2, 2])
metric_key = c1.selectbox(
    "指標", list(METRICS), format_func=lambda k: f"{METRICS[k]['label']} ({METRICS[k]['unit']})"
)
dates = query("select distinct observation_date from marts.fct_observations_hourly order by 1")["observation_date"]
date_options = ["全期間"] + [str(d) for d in dates]
date_pick = c2.selectbox("期間", date_options, index=0, help="全期間はフレーム数が多いので読み込みに数秒かかる")

meta = METRICS[metric_key]
where_date = "" if date_pick == "全期間" else "and observation_date = ?"
params = () if date_pick == "全期間" else (date_pick,)

df = query(
    f"""
    select observed_at, station_name, pref_name, latitude, longitude,
           {metric_key} as value
    from marts.fct_observations_hourly
    where {metric_key} is not null {where_date}
    order by observed_at, station_name
    """,
    params,
)

if df.empty:
    st.info("表示できる観測値がありません。")
    st.stop()

lo, hi, mid = color_range(df["value"], meta["diverging"])

# 降水・風速・日照は「量」なので点の大きさにも載せる。0 の地点は小さく薄く描いて背景にする。
size_encoded = metric_key in ("precipitation_1h_mm", "wind_speed_ms", "sunshine_1h_h")


def marker_size(v: pd.Series) -> np.ndarray:
    if not size_encoded:
        return np.full(len(v), 7.0)
    scaled = np.sqrt(np.clip(v.to_numpy(dtype=float), 0, None) / max(hi, 1e-9))
    return 3.5 + 13.0 * np.clip(scaled, 0, 1.15)


def marker_opacity(v: pd.Series) -> np.ndarray:
    return np.full(len(v), 0.85 if not size_encoded else 0.9)


def trace_for(g: pd.DataFrame) -> go.Scattergeo:
    return go.Scattergeo(
        lat=g["latitude"],
        lon=g["longitude"],
        mode="markers",
        marker={
            "color": g["value"],
            "coloraxis": "coloraxis",
            "size": marker_size(g["value"]),
            "opacity": marker_opacity(g["value"]),
            "line": {"width": 0},
        },
        customdata=np.stack([g["station_name"], g["pref_name"], g["value"]], axis=1),
        hovertemplate=(
            "<b>%{customdata[0]}</b>(%{customdata[1]})<br>"
            + meta["label"]
            + " %{customdata[2]:.1f} "
            + meta["unit"]
            + "<extra></extra>"
        ),
    )


# 観測網の形が常に見えるよう、全地点を薄い灰色で下敷きにする(フレームで差し替えるのは値トレースだけ)
stations = df.drop_duplicates(["latitude", "longitude"])
background = go.Scattergeo(
    lat=stations["latitude"],
    lon=stations["longitude"],
    mode="markers",
    marker={"size": 3.5, "color": "#d9d6cc", "opacity": 0.8, "line": {"width": 0}},
    customdata=np.stack([stations["station_name"], stations["pref_name"]], axis=1),
    hovertemplate="<b>%{customdata[0]}</b>(%{customdata[1]})<br>観測なし / 0<extra></extra>",
    name="観測地点",
)

groups = [(ts, g) for ts, g in df.groupby("observed_at", sort=True)]
if size_encoded:
    # 0 の地点は背景の灰点に任せ、描くのは値のある地点だけにする(フレームも軽くなる)
    groups = [(ts, g[g["value"] > 0]) for ts, g in groups]
frames = [go.Frame(name=fmt_ts(ts), data=[trace_for(g)], traces=[1]) for ts, g in groups]

fig = go.Figure(data=[background, frames[0].data[0]], frames=frames)

slider_steps = [
    {
        "args": [[f.name], {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"}],
        "label": f.name,
        "method": "animate",
    }
    for f in frames
]
fig.update_layout(
    height=720,
    margin={"l": 0, "r": 0, "t": 10, "b": 0},
    showlegend=False,
    coloraxis={
        "colorscale": meta["scale"],
        "cmin": lo,
        "cmax": hi,
        "colorbar": {"title": meta["unit"], "thickness": 12, "len": 0.6, "x": 0.98},
        **({"cmid": mid} if mid is not None else {}),
    },
    updatemenus=[
        {
            "type": "buttons",
            "direction": "left",
            "x": 0.02,
            "y": 0.05,
            "xanchor": "left",
            "yanchor": "bottom",
            "showactive": False,
            "buttons": [
                {
                    "label": "▶ 再生",
                    "method": "animate",
                    "args": [
                        None,
                        {
                            "frame": {"duration": 450, "redraw": True},
                            "fromcurrent": True,
                            "transition": {"duration": 0},
                        },
                    ],
                },
                {
                    "label": "❚❚ 停止",
                    "method": "animate",
                    "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
                },
            ],
        }
    ],
    sliders=[
        {
            "active": 0,
            "x": 0.02,
            "y": 0.0,
            "len": 0.96,
            "pad": {"t": 30},
            "currentvalue": {"prefix": "", "font": {"size": 18}, "xanchor": "left"},
            "steps": slider_steps,
        }
    ],
)
fig.update_geos(**japan_geo())

st.plotly_chart(fig, width="stretch", config={"scrollZoom": False, "displayModeBar": False})

n_frames = len(frames)
n_stations = df["station_name"].nunique()
st.caption(
    f"{n_frames} フレーム(1 フレーム = 1 時間)、{n_stations} 地点。"
    f"色の範囲は期間内の 1〜99 パーセンタイル({lo:.1f}〜{hi:.1f} {meta['unit']})に固定しているので、"
    "フレーム間で色の意味は変わらない。"
)

with st.expander("数値で見る(選択フレームの表)"):
    pick = st.select_slider("時刻", options=[f.name for f in frames], value=frames[-1].name)
    idx = [f.name for f in frames].index(pick)
    table = groups[idx][1][["station_name", "pref_name", "value"]].rename(
        columns={"station_name": "地点", "pref_name": "府県", "value": f"{meta['label']} ({meta['unit']})"}
    )
    st.dataframe(table.sort_values(table.columns[-1], ascending=False), hide_index=True, width="stretch")
