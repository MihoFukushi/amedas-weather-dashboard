"""気温の断面図: 日本列島を「緯度」「標高」「地点」の 3 つの軸で切って見る。

1. 緯度帯 × 時刻: 南北 20 度の列島を 1 度刻みで切り、昼夜の波と南北の勾配を 1 枚に重ねる
2. 標高 × 気温: 同じ時刻の全地点を標高で並べると、気温が標高とともに下がる「気温減率」が直線として現れる
3. 地点 × 時刻: 1 つの府県の全地点を標高順に並べ、海沿いと山地の日変化の差を見る
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import METRICS, color_range, ensure_db, fmt_ts, observed_hours, query

ensure_db()
st.title("気温の断面図")

hours = observed_hours()
if hours.empty:
    st.info("観測値がありません。")
    st.stop()

TEMP_SCALE = "RdBu_r"

# ---------------------------------------------------------------- 1. 緯度帯 × 時刻
st.subheader("緯度帯 × 時刻")
st.caption(
    "縦が緯度(上が北)、横が時刻。1 度刻みの緯度帯ごとに全地点を平均した。"
    "昼の暖まりが縦の帯として、南北の差が横の勾配として同時に見える。"
)

band_metrics = ["temperature_c", "humidity_pct", "precipitation_1h_mm", "wind_speed_ms"]
band_key = st.selectbox(
    "指標", band_metrics, format_func=lambda k: f"{METRICS[k]['label']} ({METRICS[k]['unit']})", key="band_metric"
)
band_meta = METRICS[band_key]

bands = query(
    f"""
    select floor(latitude) as lat_band, observed_at,
           round(avg({band_key}), 2) as value, count({band_key}) as n
    from marts.fct_observations_hourly
    where {band_key} is not null
    group by all
    having count({band_key}) >= 3
    order by lat_band, observed_at
    """
)
if bands.empty:
    st.info("表示できるデータがありません。")
else:
    grid = bands.pivot(index="lat_band", columns="observed_at", values="value").sort_index(ascending=True)
    counts = bands.pivot(index="lat_band", columns="observed_at", values="n").reindex_like(grid)
    lo, hi, mid = color_range(bands["value"], band_meta["diverging"])
    heat = go.Figure(
        go.Heatmap(
            z=grid.values,
            x=grid.columns,
            y=[f"{int(b)}°N" for b in grid.index],
            customdata=counts.values,
            colorscale=band_meta["scale"],
            zmin=lo,
            zmax=hi,
            **({"zmid": mid} if mid is not None else {}),
            xgap=1,
            ygap=1,
            colorbar={"title": band_meta["unit"], "thickness": 12, "len": 0.8},
            hovertemplate=(
                "%{y} 帯 %{x|%m/%d %H時}<br>" + band_meta["label"] + " %{z:.1f} " + band_meta["unit"]
                + "(%{customdata} 地点平均)<extra></extra>"
            ),
        )
    )
    heat.update_layout(
        height=520,
        margin={"l": 60, "r": 10, "t": 10, "b": 50},
        xaxis={"tickformat": "%m/%d %H時", "showgrid": False},
        yaxis={"showgrid": False, "title": "緯度帯"},
    )
    st.plotly_chart(heat, width="stretch", config={"displayModeBar": False})
    with st.expander("数値で見る"):
        shown = grid.copy()
        shown.columns = [fmt_ts(c) for c in shown.columns]
        shown.index = [f"{int(b)}°N" for b in shown.index]
        st.dataframe(shown.iloc[::-1], width="stretch")

st.divider()

# ---------------------------------------------------------------- 2. 標高 × 気温(気温減率)
st.subheader("標高 × 気温(気温減率)")
st.caption(
    "選んだ時刻の全地点を、横軸に標高、縦軸に気温で並べた。"
    "点の並びを直線で近似した傾きが気温減率。自由大気では 1 km あたり約 6.5 ℃ 下がるのが目安で、"
    "よく晴れた夜は地表が冷えて傾きが緩く(ときに逆転)、日中は急になる。"
)

ts = st.select_slider("時刻", options=list(hours), value=hours.iloc[-1], format_func=fmt_ts, key="lapse_ts")

pts = query(
    """
    select station_name, pref_name, region, altitude_m, latitude, temperature_c
    from marts.fct_observations_hourly
    where observed_at = ? and temperature_c is not null and altitude_m is not null
    """,
    (pd.Timestamp(ts).to_pydatetime(),),
)


def lapse_fit(alt: pd.Series, temp: pd.Series) -> tuple[float, float, float]:
    """気温 = a + b*標高 を最小二乗で当て、(切片, 傾き[℃/km], 決定係数) を返す。"""
    x = alt.to_numpy(dtype=float)
    y = temp.to_numpy(dtype=float)
    if len(x) < 3 or np.ptp(x) == 0:
        return (float("nan"), float("nan"), float("nan"))
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1.0
    return (float(a), float(b * 1000.0), 1.0 - ss_res / ss_tot)


if pts.empty:
    st.info("この時刻の気温がありません。")
else:
    # 南北差の影響を減らすため、緯度の中央値 ±4 度の地点だけで傾きを推定するオプション
    narrow = st.toggle("緯度を絞って推定する(中央値 ±4°)", value=True, help="緯度による差を減らし、標高の効果だけを見やすくする")
    if narrow:
        med_lat = float(pts["latitude"].median())
        fit_pts = pts[(pts["latitude"] - med_lat).abs() <= 4.0]
    else:
        fit_pts = pts
    a, slope_km, r2 = lapse_fit(fit_pts["altitude_m"], fit_pts["temperature_c"])

    scat = go.Figure()
    scat.add_trace(
        go.Scattergl(
            x=pts["altitude_m"],
            y=pts["temperature_c"],
            mode="markers",
            marker={
                "size": 7,
                "color": pts["latitude"],
                "colorscale": "Purp",
                "reversescale": False,
                "opacity": 0.75,
                "colorbar": {"title": "緯度", "thickness": 12, "len": 0.7},
                "line": {"width": 0},
            },
            customdata=np.stack([pts["station_name"], pts["pref_name"], pts["altitude_m"], pts["latitude"]], axis=1),
            hovertemplate=(
                "<b>%{customdata[0]}</b>(%{customdata[1]})<br>"
                "標高 %{customdata[2]} m・北緯 %{customdata[3]:.1f}°<br>気温 %{y:.1f} ℃<extra></extra>"
            ),
            name="地点",
        )
    )
    if not np.isnan(slope_km):
        xs = np.array([0.0, float(pts["altitude_m"].max())])
        scat.add_trace(
            go.Scatter(
                x=xs,
                y=a + slope_km / 1000.0 * xs,
                mode="lines",
                line={"color": "#eb6834", "width": 2},
                name=f"近似直線 {slope_km:.1f} ℃/km",
                hoverinfo="skip",
            )
        )
    scat.update_layout(
        height=520,
        margin={"l": 60, "r": 10, "t": 10, "b": 50},
        xaxis={"title": "標高 (m)", "gridcolor": "#eceae4", "zeroline": False},
        yaxis={"title": "気温 (℃)", "gridcolor": "#eceae4", "zeroline": False},
        legend={"orientation": "h", "y": 1.02, "x": 0, "yanchor": "bottom"},
        plot_bgcolor="rgba(0,0,0,0)",
    )

    c1, c2 = st.columns([3, 1])
    with c1:
        st.plotly_chart(scat, width="stretch", config={"displayModeBar": False})
    with c2:
        st.metric("推定気温減率", "-" if np.isnan(slope_km) else f"{slope_km:.2f} ℃/km")
        st.metric("決定係数 R²", "-" if np.isnan(r2) else f"{r2:.2f}")
        st.metric("使用地点数", len(fit_pts))
        hi_pt = pts.sort_values("altitude_m").iloc[-1]
        st.caption(f"最高地点: {hi_pt['station_name']}({hi_pt['altitude_m']} m){hi_pt['temperature_c']:.1f} ℃")

    # 期間中の全時刻で傾きを計算し、昼夜で変わる様子を折れ線にする
    series = query(
        """
        select observed_at, altitude_m, latitude, temperature_c
        from marts.fct_observations_hourly
        where temperature_c is not null and altitude_m is not null
        """
    )
    if narrow:
        series = series[(series["latitude"] - series["latitude"].median()).abs() <= 4.0]
    rows = []
    for t, g in series.groupby("observed_at", sort=True):
        _, s_km, _ = lapse_fit(g["altitude_m"], g["temperature_c"])
        rows.append({"observed_at": t, "lapse": s_km})
    lapse_ts = pd.DataFrame(rows)

    st.markdown("**気温減率の推移**(全時刻で同じ推定をした結果。負の値ほど標高で気温が下がりやすい)")
    line = go.Figure()
    line.add_trace(
        go.Scatter(
            x=lapse_ts["observed_at"],
            y=lapse_ts["lapse"],
            mode="lines+markers",
            line={"color": "#2a78d6", "width": 2},
            marker={"size": 5},
            hovertemplate="%{x|%m/%d %H時}<br>%{y:.2f} ℃/km<extra></extra>",
            name="気温減率",
        )
    )
    line.add_hline(y=-6.5, line={"color": "#9c9a92", "width": 1, "dash": "dot"}, annotation_text="目安 -6.5 ℃/km", annotation_position="bottom right")
    line.add_vline(x=pd.Timestamp(ts), line={"color": "#eb6834", "width": 1})
    line.update_layout(
        height=260,
        margin={"l": 60, "r": 10, "t": 10, "b": 50},
        xaxis={"tickformat": "%m/%d %H時", "gridcolor": "#eceae4"},
        yaxis={"title": "℃/km", "gridcolor": "#eceae4", "zeroline": False},
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(line, width="stretch", config={"displayModeBar": False})

st.divider()

# ---------------------------------------------------------------- 3. 地点 × 時刻
st.subheader("地点 × 時刻(府県内の全地点)")
st.caption("縦に府県内の地点を標高順(上が高い)、横に時刻。山地と平地・海沿いで日変化の形が違うのが分かる。")

prefs = query("select distinct pref_code, pref_name from marts.fct_observations_hourly order by pref_code")
default_pref = int(prefs.index[prefs["pref_name"] == "長野県"][0]) if (prefs["pref_name"] == "長野県").any() else 0
pref_name = st.selectbox("府県", prefs["pref_name"], index=default_pref)

st_rows = query(
    """
    select station_name, altitude_m, observed_at, temperature_c
    from marts.fct_observations_hourly
    where pref_name = ? and temperature_c is not null
    order by altitude_m, station_name, observed_at
    """,
    (pref_name,),
)
if st_rows.empty:
    st.info("この府県には気温の観測値がありません。")
else:
    st_rows["label"] = st_rows["station_name"] + "(" + st_rows["altitude_m"].astype(int).astype(str) + " m)"
    order = (
        st_rows.drop_duplicates("label").sort_values(["altitude_m", "station_name"])["label"].tolist()
    )
    grid = st_rows.pivot_table(index="label", columns="observed_at", values="temperature_c").reindex(order)
    lo, hi, mid = color_range(st_rows["temperature_c"], True)
    h = go.Figure(
        go.Heatmap(
            z=grid.values,
            x=grid.columns,
            y=grid.index,
            colorscale=TEMP_SCALE,
            zmin=lo,
            zmax=hi,
            zmid=mid,
            xgap=1,
            ygap=1,
            colorbar={"title": "℃", "thickness": 12, "len": 0.8},
            hovertemplate="%{y}<br>%{x|%m/%d %H時} 気温 %{z:.1f} ℃<extra></extra>",
        )
    )
    h.update_layout(
        height=max(320, 22 * len(order) + 80),
        margin={"l": 150, "r": 10, "t": 10, "b": 50},
        xaxis={"tickformat": "%m/%d %H時", "showgrid": False},
        yaxis={"showgrid": False, "tickfont": {"size": 11}},
    )
    st.plotly_chart(h, width="stretch", config={"displayModeBar": False})

    rng = grid.max(axis=1) - grid.min(axis=1)
    c1, c2 = st.columns(2)
    c1.metric("日較差が最も大きい地点", rng.idxmax(), f"{rng.max():.1f} ℃")
    c2.metric("日較差が最も小さい地点", rng.idxmin(), f"{rng.min():.1f} ℃", delta_color="off")
    with st.expander("数値で見る"):
        shown = grid.copy()
        shown.columns = [fmt_ts(c) for c in shown.columns]
        st.dataframe(shown, width="stretch")
