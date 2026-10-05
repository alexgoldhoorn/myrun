"""Plotly figure builders. Pure: data in, figure out."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


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
