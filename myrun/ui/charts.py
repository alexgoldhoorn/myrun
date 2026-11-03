"""Plotly figure builders. Pure: data in, figure out."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from myrun import explore, fmt
from myrun.ui import theme


def load_bars(weekly: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(x=weekly["week_start"], y=weekly["effort"],
                           hovertemplate="week of %{x|%d %b}<br>effort %{y:.0f}<extra></extra>"))
    theme.style(fig, height=260)
    fig.update_layout(yaxis_title=fmt.label("relative_effort"), xaxis_title=None)
    return fig


_STREAM_METRICS = [(c, fmt.label(c)) for c in ("hr", "pace_min_km", "altitude_m", "cadence_spm")]
PACE_SMOOTHING_SAMPLES = 15


def _x(streams_df: pd.DataFrame, x: str) -> pd.Series:
    if x == "distance":
        return pd.to_numeric(streams_df["distance_m"], errors="coerce") / 1000
    return pd.to_numeric(streams_df["time_s"], errors="coerce") / 60


def stream_figure(streams_df: pd.DataFrame, x: str = "time",
                  overlay: pd.DataFrame | None = None) -> go.Figure:
    """Stacked charts on a shared x axis, one row per metric that has data."""
    metrics = [(c, label) for c, label in _STREAM_METRICS
               if len(streams_df) and pd.to_numeric(streams_df[c], errors="coerce").notna().any()]
    if not metrics:
        return theme.style(go.Figure())
    fig = make_subplots(rows=len(metrics), cols=1, shared_xaxes=True, vertical_spacing=0.04)
    for series, name, dash in ((streams_df, "this activity", None), (overlay, "compared", "dot")):
        if series is None or not len(series):
            continue
        xs = _x(series, x)
        for row, (column, _) in enumerate(metrics, start=1):
            ys = pd.to_numeric(series[column], errors="coerce")
            extra = {}
            if column == "pace_min_km":
                ys = ys.rolling(PACE_SMOOTHING_SAMPLES, min_periods=1, center=True).median()
                extra = dict(text=[fmt.pace(v) for v in ys],
                             hovertemplate="%{text} /km<extra>" + name + "</extra>")
            fig.add_trace(go.Scatter(x=list(xs), y=list(ys), mode="lines", name=name,
                                     legendgroup=name, showlegend=row == 1,
                                     line=dict(dash=dash), **extra), row=row, col=1)
    for row, (column, label) in enumerate(metrics, start=1):
        fig.update_yaxes(title_text=label, row=row, col=1,
                         autorange="reversed" if column == "pace_min_km" else None)
        if column == "pace_min_km":
            shown = pd.to_numeric(streams_df[column], errors="coerce").rolling(
                PACE_SMOOTHING_SAMPLES, min_periods=1, center=True).median()
            vals, text = fmt.pace_ticks(shown)
            if vals:
                fig.update_yaxes(tickmode="array", tickvals=vals, ticktext=text, row=row, col=1)
    fig.update_xaxes(title_text=fmt.label("distance_km") if x == "distance" else fmt.label("time_min"),
                     row=len(metrics), col=1)
    theme.style(fig, height=200 * len(metrics) + 60)
    fig.update_layout(hovermode="x unified")
    return fig


def zone_bar(zones: pd.DataFrame) -> go.Figure:
    labels = [f"Z{z}" for z in zones["zone"]]
    fig = go.Figure(go.Bar(x=list(zones["seconds"] / 60), y=labels, orientation="h",
                           text=[f"{p:.0f}%" for p in zones["pct"]],
                           hovertemplate="%{y}: %{x:.0f} min<extra></extra>"))
    theme.style(fig, height=220)
    fig.update_layout(xaxis_title=fmt.label("minutes"))
    return fig


MIN_TREND_POINTS = 3


def explore_figure(df: pd.DataFrame, x: str, y: str, group: pd.Series | None = None) -> go.Figure:
    """Scatter with a straight fitted line per group, or box plots when x is a category."""
    data = pd.DataFrame({"x": df[x], "y": pd.to_numeric(df[y], errors="coerce")})
    data["group"] = "all" if group is None else group.reindex(df.index)
    data = data.dropna(subset=["x", "y", "group"])
    fig = go.Figure()
    names = explore.ordered(data["group"])
    if not pd.api.types.is_numeric_dtype(df[x]):
        for name in names:
            part = data[data["group"] == name]
            fig.add_trace(go.Box(x=list(part["x"].astype(str)), y=list(part["y"]), name=name))
        fig.update_layout(boxmode="group")
    else:
        for name in names:
            part = data[data["group"] == name]
            xs, ys = part["x"].astype(float), part["y"]
            fig.add_trace(go.Scatter(x=list(xs), y=list(ys), mode="markers", name=name,
                                     legendgroup=name, opacity=0.7))
            if len(part) >= MIN_TREND_POINTS and xs.nunique() > 1:
                slope, intercept = np.polyfit(xs, ys, 1)
                ends = np.array([xs.min(), xs.max()])
                fig.add_trace(go.Scatter(x=list(ends), y=list(slope * ends + intercept),
                                         mode="lines", legendgroup=name, showlegend=False,
                                         hoverinfo="skip"))
    theme.style(fig, height=520)
    fig.update_layout(xaxis_title=fmt.label(x), yaxis_title=fmt.label(y),
                      showlegend=group is not None)
    for column, update in ((x, fig.update_xaxes), (y, fig.update_yaxes)):
        if column in fmt.PACE_COLUMNS:
            vals, text = fmt.pace_ticks(df[column])
            if vals:
                update(tickmode="array", tickvals=vals, ticktext=text)
    return fig


def trend_line(df: pd.DataFrame, x: str, y: str, y_title: str) -> go.Figure:
    fig = go.Figure(go.Scatter(x=list(df[x]), y=list(df[y]), mode="lines+markers",
                               hovertemplate="%{x|%b %Y}<br>%{y:.1f}<extra></extra>"))
    theme.style(fig, height=300)
    fig.update_layout(yaxis_title=y_title, xaxis_title=None)
    return fig


def weekly_km_bars(weekly: pd.DataFrame) -> go.Figure:
    """Running km per week, with the planned km as markers where a plan covers the week."""
    fig = go.Figure(go.Bar(x=weekly["week_start"], y=weekly["run_km"], name="done",
                           hovertemplate="week of %{x|%d %b}<br>%{y:.1f} km<extra></extra>"))
    if "planned_km" in weekly and weekly["planned_km"].notna().any():
        fig.add_trace(go.Scatter(x=weekly["week_start"], y=weekly["planned_km"], name="planned",
                                 mode="markers", marker={"symbol": "line-ew-open", "size": 22,
                                                         "line": {"width": 2}},
                                 hovertemplate="planned %{y:.1f} km<extra></extra>"))
    theme.style(fig, height=260)
    fig.update_layout(yaxis_title=fmt.label("run_km"), xaxis_title=None)
    return fig


def intensity_bars(weekly: pd.DataFrame) -> go.Figure:
    """Running minutes per week, stacked by session intensity."""
    fig = go.Figure()
    for kind in ("easy", "steady", "hard"):
        fig.add_trace(go.Bar(x=weekly["week_start"], y=weekly[f"{kind}_min"], name=kind,
                             hovertemplate="week of %{x|%d %b}<br>%{y:.0f} min " + kind
                                           + "<extra></extra>"))
    theme.style(fig, height=300)
    fig.update_layout(barmode="stack", yaxis_title=fmt.label("run_minutes"), xaxis_title=None)
    return fig


def easy_pace_line(weekly: pd.DataFrame) -> go.Figure:
    """Median easy pace per week; weeks without an easy run are left out, faster is up."""
    shown = weekly.dropna(subset=["easy_pace_min_km"])
    fig = go.Figure(go.Scatter(x=list(shown["week_start"]), y=list(shown["easy_pace_min_km"]),
                               mode="lines+markers",
                               text=[fmt.pace(v) for v in shown["easy_pace_min_km"]],
                               hovertemplate="week of %{x|%d %b}<br>%{text} /km<extra></extra>"))
    theme.style(fig, height=260)
    vals, text = fmt.pace_ticks(shown["easy_pace_min_km"])
    fig.update_layout(yaxis_title=fmt.label("easy_pace"), xaxis_title=None)
    fig.update_yaxes(autorange="reversed",
                     **(dict(tickmode="array", tickvals=vals, ticktext=text) if vals else {}))
    return fig


def efficiency_year_bars(yearly: pd.DataFrame) -> go.Figure:
    """Aerobic efficiency per year; the run count is in the hover."""
    fig = go.Figure(go.Bar(x=[str(y) for y in yearly["year"]], y=list(yearly["efficiency"]),
                           customdata=list(zip(yearly["n_runs"], yearly["n_months"])),
                           hovertemplate="%{x}<br>%{y:.3f} m/beat<br>%{customdata[0]} runs in "
                                         "%{customdata[1]} months<extra></extra>"))
    theme.style(fig, height=280)
    low = float(yearly["efficiency"].min()) if len(yearly) else 0.0
    fig.update_layout(yaxis_title=fmt.label("m_per_beat"), xaxis_title=None)
    fig.update_yaxes(range=[low * 0.9, None])
    return fig


def band_hr_lines(table: pd.DataFrame, bands_order) -> go.Figure:
    """Mean heart rate per pace band, one line per year; noisy cells are open markers."""
    fig = go.Figure()
    for year, rows in table.groupby("period"):
        rows = rows.set_index("band").reindex([b for b in bands_order if b in set(rows["band"])])
        fig.add_trace(go.Scatter(
            x=list(rows.index), y=list(rows["mean_hr"]), name=str(year), mode="lines+markers",
            marker_symbol=["circle-open" if n else "circle" for n in rows["noisy"]],
            customdata=list(zip(rows["n_runs"], rows["hr_pct_max"], rows["temp_c"])),
            hovertemplate=f"{year} · %{{x}}/km<br>HR %{{y:.0f}} (%{{customdata[1]:.0f}} % max)"
                          "<br>%{customdata[0]} runs, %{customdata[2]:.0f} °C<extra></extra>"))
    theme.style(fig, height=320)
    fig.update_layout(yaxis_title=fmt.label("mean_hr"),
                      xaxis_title=fmt.label("gap_min_km"))
    fig.update_xaxes(categoryorder="array", categoryarray=list(bands_order))
    return fig


def intensity_share_bars(yearly: pd.DataFrame) -> go.Figure:
    """Share of running minutes per year by session intensity, stacked to 100 %."""
    fig = go.Figure()
    for kind in ("easy", "steady", "hard"):
        fig.add_trace(go.Bar(x=[str(y) for y in yearly["year"]], y=list(yearly[f"{kind}_pct"]),
                             name=kind,
                             hovertemplate="%{x}<br>%{y:.0f} % " + kind + "<extra></extra>"))
    theme.style(fig, height=280)
    fig.update_layout(barmode="stack", yaxis_title=fmt.label("share_minutes"), xaxis_title=None)
    return fig
