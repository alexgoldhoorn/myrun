"""Activity: what happened in that run?"""

import pandas as pd
import streamlit as st

from myrun import dynamics, fmt, links, streams
from myrun.config import RUN_SPORTS
from myrun.ui import cards, charts, common

cfg = common.setup("Activity")
acts = common.load_activities(cfg)
states = common.cached("input_states", cfg)

common.banner(states)
st.title("Activity")
if acts.empty:
    st.info("No activities in the database yet.")
    common.footer(acts, states)
    st.stop()

candidates = acts[acts["has_streams"]].sort_values("start", ascending=False)
if candidates.empty:
    st.info("No activities with imported streams.")
    common.footer(acts, states)
    st.stop()

labels = {r.activity_id: f"{r.start:%Y-%m-%d %H:%M} · {r.sport} · {r.distance_km:.1f} km"
          for r in candidates.itertuples()}
by_label = {label: activity_id for activity_id, label in labels.items()}
options = list(by_label)
wanted = labels.get(st.session_state.get("activity_id"))
choice = st.selectbox("Activity", options, index=options.index(wanted) if wanted in options else 0)
activity_id = by_label[choice]
row = candidates.set_index("activity_id").loc[activity_id]


def _fmt(value, pattern):
    return "n/a" if pd.isna(value) else pattern.format(value)


st.markdown(cards.summary_html([
    ("Distance", _fmt(row["distance_km"], "{:.2f} km")),
    ("Time", _fmt(row["duration_min"], "{:.0f} min")),
    ("Pace", "n/a" if pd.isna(row["pace_min_km"]) else f"{fmt.pace(row['pace_min_km'])} /km"),
    ("Avg HR", _fmt(row["avg_hr"], "{:.0f} bpm")),
    ("Climb", _fmt(row["elevation_m"], "{:.0f} m")),
]), unsafe_allow_html=True)

st.markdown(cards.links_html([
    ("Strava", links.strava_url(activity_id)),
    ("statistics-for-strava", links.sfs_url(cfg.sfs_url, activity_id)),
    ("Garmin Connect", links.garmin_url(row.get("garmin_activity_id"))),
]), unsafe_allow_html=True)

session = row.get("session_name")
if isinstance(session, str) and session:
    st.markdown(cards.note_html(f"Garmin session: {session}"), unsafe_allow_html=True)

runs_only = acts[acts["sport"].isin(RUN_SPORTS)]
dynamic_cards = dynamics.activity_dynamics(row, runs_only)
if dynamic_cards:
    st.subheader("Running dynamics")
    cards.card_row(dynamic_cards)

data = common.cached("streams", cfg, activity_id)
if data.empty:
    st.info("This activity has no stream data.")
    common.footer(acts, states)
    st.stop()

left, right = st.columns([1, 3])
axis = left.radio("X axis", ["time", "distance"], horizontal=True)
others = ["(none)"] + [label for label in options if label != choice]
compare = right.selectbox("Compare with", others)
overlay = None if compare == "(none)" else common.cached("streams", cfg, by_label[compare])
st.plotly_chart(common.figure("streams", cfg,
                              lambda: charts.stream_figure(data, x=axis, overlay=overlay),
                              activity_id, axis, None if overlay is None else by_label[compare]))

left, right = st.columns(2)
with left:
    st.subheader("Time in HR zones")
    heart = common.cached("hr_settings", cfg)
    if heart.zone_upper_bounds is None:
        st.caption(f"Zones {heart.source}.")
    else:
        st.plotly_chart(common.figure(
            "zones", cfg,
            lambda: charts.zone_bar(streams.zone_seconds(data, heart.zone_upper_bounds)),
            activity_id))
        edges = ", ".join(str(b) for b in heart.zone_upper_bounds)
        st.caption(f"Zones end at {edges} bpm; {heart.source}.")
with right:
    st.subheader("HR drift")
    drift = streams.drift_pct(data)
    if drift is None:
        st.caption("Needs at least 30 minutes with heart rate and speed.")
    else:
        st.metric("First half vs. second half", f"{drift:+.1f} %")
        st.caption("How much more heart rate the same speed cost in the second half. "
                   "A few percent is normal; much more points to heat, fatigue or pacing.")

st.subheader("Laps")
laps = common.cached("laps", cfg, activity_id)
if laps.empty:
    st.caption("No laps recorded.")
else:
    shown = laps.round({"distance_km": 2})
    shown["pace"] = shown.pop("pace_min_km").map(fmt.pace)
    shown["time"] = shown.pop("duration_s").map(fmt.duration)
    st.dataframe(shown[["lap", "name", "distance_km", "time", "pace", "avg_hr", "elev_diff_m"]],
                 hide_index=True)

common.footer(acts, states)
