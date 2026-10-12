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
    fig.update_layout(yaxis_title="Relative effort", xaxis_title=None)
    return fig


_STREAM_METRICS = [("hr", "Heart rate (bpm)"), ("pace_min_km", "Pace (min/km)"),
                   ("altitude_m", "Elevation (m)"), ("cadence_spm", "Cadence (spm)")]
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
    fig.update_xaxes(title_text="Distance (km)" if x == "distance" else "Time (min)",
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
    fig.update_layout(xaxis_title="Minutes")
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
    fig.update_layout(xaxis_title=x, yaxis_title=y, showlegend=group is not None)
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
    fig.update_layout(yaxis_title="Running km", xaxis_title=None)
    return fig


def intensity_bars(weekly: pd.DataFrame) -> go.Figure:
    """Running minutes per week, stacked by session intensity."""
    fig = go.Figure()
    for kind in ("easy", "steady", "hard"):
        fig.add_trace(go.Bar(x=weekly["week_start"], y=weekly[f"{kind}_min"], name=kind,
                             hovertemplate="week of %{x|%d %b}<br>%{y:.0f} min " + kind
                                           + "<extra></extra>"))
    theme.style(fig, height=300)
    fig.update_layout(barmode="stack", yaxis_title="Running minutes", xaxis_title=None)
    return fig
