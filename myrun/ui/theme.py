"""The app's look: one stylesheet for cards, and one place for chart layout.

Fonts, radius, colours and the chart palette live in .streamlit/config.toml, which
Streamlit applies to its own widgets and to Plotly charts. This module only adds what
the config cannot express. Chart builders must not set trace colours: the palette
comes from the theme, in light and in dark.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

MARGIN = {"l": 10, "r": 10, "t": 10, "b": 10}
TONE_CLASS = {"neutral": "mr-neutral", "good": "mr-good", "warn": "mr-warn", "bad": "mr-bad"}

CSS = """
:root {
  --mr-surface: #ffffff; --mr-border: #dee2e6; --mr-muted: #6c757d; --mr-text: #212529;
  --mr-line: #2a78d6; --mr-good: #16a34a; --mr-warn: #b45309; --mr-bad: #dc2626;
  --mr-neutral: #6c757d;
}
@media (prefers-color-scheme: dark) {
  :root {
    --mr-surface: #212529; --mr-border: #373b3e; --mr-muted: #9aa4b1; --mr-text: #e9ecef;
    --mr-line: #3987e5; --mr-good: #22c55e; --mr-warn: #fbbf24; --mr-bad: #f87171;
    --mr-neutral: #9aa4b1;
  }
}
.block-container { padding-top: 2.5rem; max-width: 1400px; }
.mr-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
          gap: 0.75rem; margin: 0 0 1rem 0; }
.mr-card { background: var(--mr-surface); border: 1px solid var(--mr-border);
           border-radius: 0.5rem; padding: 0.85rem 1rem 0.6rem 1rem; min-height: 8.2rem;
           display: flex; flex-direction: column; }
.mr-label { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em;
            text-transform: uppercase; color: var(--mr-muted); }
.mr-value { font-size: 1.65rem; font-weight: 650; line-height: 1.25; color: var(--mr-text);
            font-variant-numeric: tabular-nums; }
.mr-detail { font-size: 0.8rem; font-weight: 500; margin-left: 0.4rem; }
.mr-change { font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.mr-note { font-size: 0.72rem; color: var(--mr-muted); }
.mr-spark { margin-top: auto; padding-top: 0.35rem; width: 100%; height: 28px; }
.mr-spark polyline { fill: none; stroke: var(--mr-line); stroke-width: 1.5;
                     stroke-linejoin: round; stroke-linecap: round; }
.mr-neutral { color: var(--mr-neutral); } .mr-good { color: var(--mr-good); }
.mr-warn { color: var(--mr-warn); } .mr-bad { color: var(--mr-bad); }
.mr-strip { background: var(--mr-surface); border: 1px solid var(--mr-border);
            border-radius: 0.5rem; padding: 0.7rem 1rem; margin-bottom: 1rem;
            display: flex; flex-wrap: wrap; gap: 0.4rem 1.5rem; align-items: baseline; }
.mr-strip strong { color: var(--mr-text); }
[data-testid="stMetric"] { background: var(--mr-surface); border: 1px solid var(--mr-border);
                           border-radius: 0.5rem; padding: 0.7rem 1rem; }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
h1 { font-weight: 650; letter-spacing: -0.01em; }
h3 { font-size: 1.05rem; font-weight: 600; margin-top: 0.5rem; }
"""


def apply() -> None:
    """Inject the stylesheet. Called once per page run, from common.setup()."""
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def style(fig: go.Figure, height: int | None = None) -> go.Figure:
    """The shared chart layout. Colours and fonts are left to the Streamlit theme."""
    fig.update_layout(margin=MARGIN, hoverlabel={"namelength": -1},
                      legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0})
    if height is not None:
        fig.update_layout(height=height)
    return fig
