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

# name: (light, dark)
COLOURS = {
    "surface": ("#ffffff", "#212529"), "border": ("#dee2e6", "#373b3e"),
    "muted": ("#6c757d", "#9aa4b1"), "text": ("#212529", "#e9ecef"),
    "line": ("#2a78d6", "#3987e5"), "good": ("#16a34a", "#22c55e"),
    "warn": ("#b45309", "#fbbf24"), "bad": ("#dc2626", "#f87171"),
    "neutral": ("#6c757d", "#9aa4b1"),
}


def _colours() -> str:
    """The card colours as CSS variables that follow the theme Streamlit is showing.

    Streamlit sets `color-scheme` on .stApp for the theme chosen in its menu, and
    light-dark() reads that. The first two rules serve a browser without light-dark():
    there the cards follow the browser's own setting."""
    light = " ".join(f"--mr-{name}: {pair[0]};" for name, pair in COLOURS.items())
    dark = " ".join(f"--mr-{name}: {pair[1]};" for name, pair in COLOURS.items())
    both = " ".join(f"--mr-{name}: light-dark({pair[0]}, {pair[1]});"
                    for name, pair in COLOURS.items())
    return (f":root {{ {light} }}\n@media (prefers-color-scheme: dark) {{ :root {{ {dark} }} }}\n"
            f"@supports (color: light-dark(#000, #fff)) {{ .stApp {{ {both} }} }}")


_RULES = """
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
.mr-cal { display: grid; grid-template-rows: repeat(7, 14px); grid-auto-flow: column;
          grid-auto-columns: 14px; gap: 3px; margin: 0.25rem 0 1rem 0; }
.mr-cal-labels { display: grid; gap: 3px; font-size: .65rem; color: var(--mr-muted);
                 margin-top: 0.25rem; white-space: nowrap; }
.mr-cal-wrap .mr-cal { margin-top: 3px; }
.mr-day { border-radius: 3px; background: var(--mr-border); }
.mr-day-today { outline: 2px solid var(--mr-line); outline-offset: 1px; }
.mr-day-1 { background: var(--mr-line); opacity: 0.35; }
.mr-day-2 { background: var(--mr-line); opacity: 0.65; }
.mr-day-3 { background: var(--mr-line); }
.mr-day-future { background: transparent; border: 1px dashed var(--mr-border); }
.mr-compact { min-height: 0; padding-bottom: 0.75rem; }
.mr-compact .mr-value { font-size: 1.35rem; white-space: nowrap; }
.mr-links { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0 0 0.75rem 0; }
.mr-link { border: 1px solid var(--mr-border); border-radius: 0.5rem; padding: 0.35rem 0.8rem;
           background: var(--mr-surface); color: var(--mr-text) !important; font-size: 0.9rem;
           text-decoration: none !important; white-space: nowrap; }
.mr-link:hover { border-color: var(--mr-line); color: var(--mr-line) !important; }
[data-testid="stMetric"] { background: var(--mr-surface); border: 1px solid var(--mr-border);
                           border-radius: 0.5rem; padding: 0.7rem 1rem; }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
@media (min-width: 900px) {
  .mr-row { grid-template-columns: repeat(3, 1fr); }
  .mr-row.mr-row-2 { grid-template-columns: repeat(2, 1fr); }
}
@media (min-width: 481px) and (max-width: 899.98px) {
  .mr-row { grid-template-columns: repeat(2, 1fr); }
}
.mr-row-compact { grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }
@media (max-width: 480px) {
  .mr-row { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.5rem; }
  .mr-card { min-height: 0; padding: 0.7rem 0.8rem 0.5rem; }
  .mr-value { font-size: 1.4rem; }
}
.st-key-mr-phone-nav { display: none; }
@media (max-width: 767.98px) {
  .st-key-mr-phone-nav { display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: .5rem; }
}
h1 { font-weight: 650; letter-spacing: -0.01em; }
h3 { font-size: 1.05rem; font-weight: 600; margin-top: 0.5rem; }
"""


CSS = _colours() + _RULES


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
