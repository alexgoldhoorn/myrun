"""Plotly figure builders. Pure: data in, figure out."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def load_bars(weekly: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(x=weekly["week_start"], y=weekly["effort"],
                           hovertemplate="week of %{x|%d %b}<br>effort %{y:.0f}<extra></extra>"))
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis_title="Relative effort", xaxis_title=None)
    return fig


def sparkline(values: pd.Series) -> go.Figure:
    fig = go.Figure(go.Scatter(y=list(values), mode="lines", hoverinfo="skip"))
    fig.update_layout(height=60, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
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
        return go.Figure()
    fig = make_subplots(rows=len(metrics), cols=1, shared_xaxes=True, vertical_spacing=0.04)
    for series, name, dash in ((streams_df, "this activity", None), (overlay, "compared", "dot")):
        if series is None or not len(series):
            continue
        xs = _x(series, x)
        for row, (column, _) in enumerate(metrics, start=1):
            ys = pd.to_numeric(series[column], errors="coerce")
            if column == "pace_min_km":
                ys = ys.rolling(PACE_SMOOTHING_SAMPLES, min_periods=1, center=True).median()
            fig.add_trace(go.Scatter(x=list(xs), y=list(ys), mode="lines", name=name,
                                     legendgroup=name, showlegend=row == 1,
                                     line=dict(dash=dash)), row=row, col=1)
    for row, (column, label) in enumerate(metrics, start=1):
        fig.update_yaxes(title_text=label, row=row, col=1,
                         autorange="reversed" if column == "pace_min_km" else None)
    fig.update_xaxes(title_text="Distance (km)" if x == "distance" else "Time (min)",
                     row=len(metrics), col=1)
    fig.update_layout(height=200 * len(metrics) + 60, margin=dict(l=10, r=10, t=10, b=10),
                      hovermode="x unified")
    return fig


def zone_bar(zones: pd.DataFrame) -> go.Figure:
    labels = [f"Z{z}" for z in zones["zone"]]
    fig = go.Figure(go.Bar(x=list(zones["seconds"] / 60), y=labels, orientation="h",
                           text=[f"{p:.0f}%" for p in zones["pct"]],
                           hovertemplate="%{y}: %{x:.0f} min<extra></extra>"))
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Minutes")
    return fig
