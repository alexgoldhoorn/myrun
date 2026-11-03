"""Explore: any metric against any other, grouped by conditions."""

import streamlit as st

from myrun import explore, fmt
from myrun.config import RUN_SPORTS
from myrun.ui import charts, common

cfg = common.setup("Explore")
acts = common.load_activities(cfg)
states = common.cached("input_states", cfg)

common.banner(states)
st.title("Explore")
if acts.empty:
    st.info("No activities in the database yet.")
    common.footer(acts, states)
    st.stop()

level = st.radio("Level of detail", ["per run", "per km"], horizontal=True)
df = acts if level == "per run" else common.load_splits(cfg)
if df.empty:
    st.info("No per-km splits available.")
    common.footer(acts, states)
    st.stop()

# ---- filters --------------------------------------------------------------
with st.expander("Filters", expanded=True):
    left, middle, right = st.columns(3)
    first, last = df["date"].min().date(), df["date"].max().date()
    period = left.date_input("Dates", (first, last), min_value=first, max_value=last)
    sports = sorted(df["sport"].dropna().unique())
    chosen_sports = middle.multiselect("Sport", sports,
                                       default=[s for s in sports if s in RUN_SPORTS] or sports)
    session_types = sorted(df["session_type"].dropna().unique())
    chosen_types = right.multiselect("Session type", session_types) if session_types else []

if len(period) == 2:
    df = df[(df["date"].dt.date >= period[0]) & (df["date"].dt.date <= period[1])]
if chosen_sports:
    df = df[df["sport"].isin(chosen_sports)]
if chosen_types:
    df = df[df["session_type"].isin(chosen_types)]

# ---- axes and grouping ----------------------------------------------------
numeric = explore.numeric_columns(df)
groups = explore.available_groups(df)
if len(numeric) < 2:
    st.info("Not enough data left after filtering.")
    common.footer(acts, states)
    st.stop()

categories = [g for g in groups if g != "(none)"]
left, middle, right = st.columns(3)
x_choice = left.selectbox("X", numeric + [f"category: {g}" for g in categories],
                          format_func=lambda c: c if c.startswith("category: ") else fmt.label(c),
                          index=numeric.index("temp_c") if "temp_c" in numeric else 0)
y_default = "pace_min_km" if "pace_min_km" in numeric else numeric[-1]
y_choice = middle.selectbox("Y", numeric, format_func=fmt.label, index=numeric.index(y_default))
group_choice = right.selectbox("Group by", groups)

with st.expander("Block sizes"):
    a, b, c, d = st.columns(4)
    blocks = {
        "hour_block": a.number_input("Hour of day (h)", 1, 12, 3),
        "temp_block": b.number_input("Temperature (°C)", 1, 20, 5),
        "distance_band": c.number_input("Distance (km)", 1, 50, 5),
        "hilliness_band": d.number_input("Hilliness (m/km)", 1, 100, 10),
    }

def _chart():
    """The figure and how many rows it shows; built once per set of choices."""
    plot = df.copy()
    if x_choice.startswith("category: "):
        plot["_x"] = explore.group_series(plot, x_choice.removeprefix("category: "), **blocks)
        x_column = "_x"
    else:
        x_column = x_choice
    group = explore.group_series(plot, group_choice, **blocks)
    figure = charts.explore_figure(plot, x_column, y_choice, group)
    figure.update_layout(xaxis_title=fmt.label(x_choice.removeprefix("category: ")),
                         legend_title_text=None if group_choice == "(none)" else group_choice)
    if x_column == "_x":
        figure.update_xaxes(categoryorder="array", categoryarray=explore.ordered(plot["_x"]))
    return figure, len(plot[[x_column, y_choice]].dropna()), len(plot)


figure, shown, total = common.figure(
    "explore", cfg, _chart, level, tuple(str(day) for day in period), tuple(chosen_sports),
    tuple(chosen_types), x_choice, y_choice, group_choice, tuple(sorted(blocks.items())))
st.plotly_chart(figure)

st.caption(f"{shown} of {total} rows have both values. "
           + ("One point per kilometre." if level == "per km" else "One point per activity."))
if level == "per run" and not session_types:
    st.caption("No session types are available, so easy runs and hard sessions are mixed. "
               "Filter by distance or surface to compare like with like.")

common.footer(acts, states)
