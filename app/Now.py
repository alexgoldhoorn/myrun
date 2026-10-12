"""Now: how am I doing right now?"""

import datetime as dt

import pandas as pd
import streamlit as st

from myrun import links, optional
from myrun.load import load_status, weekly_load
from myrun.planmatch import plan_vs_actual
from myrun.ui import charts, common

cfg = common.setup("Now")
acts = common.load_activities(cfg)
states = optional.input_states(cfg)
today = pd.Timestamp(dt.date.today())

common.banner(states)
st.title("Now")
if acts.empty:
    st.info("No activities in the database yet.")
    common.footer(acts, states)
    st.stop()

# ---- next race ------------------------------------------------------------
plan, plan_state = optional.read_plan(cfg)
if plan_state.status != "off":
    st.subheader("Next race")
    upcoming = plan[(plan["type"] == "race") & (plan["date"] >= today)] if plan is not None else None
    if upcoming is not None and len(upcoming):
        race = upcoming.iloc[0]
        days = (race["date"] - today).days
        st.markdown(f"**{race['session']}** on {race['date']:%a %d %b %Y}, in {days} days")
    elif plan is not None:
        st.caption("No race in the plan from today onwards.")

# ---- load -----------------------------------------------------------------
st.subheader("Load")
status = load_status(activities=acts, cfg=cfg)
left, right = st.columns([1, 3])
with left:
    ratio = "n/a" if status["ratio"] is None else f"{status['ratio']:.2f}"
    st.metric("Last 7 days vs. 4-week average", ratio, status["label"], delta_color="off")
    st.caption(f"Relative effort: {status['last7']:.0f} in the last 7 days, "
               f"{status['avg_week_28']:.0f} per week over 28 days.")
    if status["n_missing"]:
        st.caption(f"{status['n_missing']} activities in the last 28 days have no relative "
                   "effort and are not counted.")
with right:
    st.plotly_chart(charts.load_bars(weekly_load(12, activities=acts, cfg=cfg)))

# ---- this week ------------------------------------------------------------
st.subheader("This week")
week = plan_vs_actual(activities=acts, cfg=cfg)
table = pd.DataFrame({"Day": week["date"].dt.strftime("%a %d %b"), "Done": week["actual"]})
if plan is not None:
    table.insert(1, "Planned", week["planned"])
st.dataframe(table, hide_index=True)
run_km = week["actual_run_km"].sum()
if plan is not None and week["planned_km"].notna().any():
    st.caption(f"Running: {run_km:.1f} km done of {week['planned_km'].sum():.1f} km planned.")
else:
    st.caption(f"Running: {run_km:.1f} km so far this week.")

# ---- recovery -------------------------------------------------------------
wellness, wellness_state = optional.read_wellness(cfg)
if wellness_state.status != "off":
    st.subheader("Recovery")
    if common.notice(wellness_state):
        latest = wellness.iloc[-1]
        if latest["date"] < today - pd.Timedelta(days=1):
            st.warning(f"**wellness**: the newest row is from {latest['date']:%a %d %b}; "
                       "nothing for today or yesterday.")
        else:
            baseline = wellness[wellness["date"] > today - pd.Timedelta(days=28)]
            labels = {"readiness": "Readiness", "sleep_hours": "Sleep (h)", "hrv_ms": "HRV (ms)",
                      "resting_hr": "Resting HR"}
            present = [c for c in labels if c in wellness.columns]
            for column, slot in zip(present, st.columns(max(len(present), 1))):
                with slot:
                    value, mean = latest[column], baseline[column].mean()
                    st.metric(labels[column], "n/a" if pd.isna(value) else f"{value:.1f}",
                              None if pd.isna(value) or pd.isna(mean)
                              else f"{value - mean:+.1f} vs 4-week average", delta_color="off")
                    st.plotly_chart(charts.sparkline(wellness[column].tail(14)),
                                    key=f"spark-{column}")
            st.caption(f"Values for {latest['date']:%a %d %b}.")

# ---- last 7 days ----------------------------------------------------------
st.subheader("Last 7 days")
recent = acts[acts["date"] > today - pd.Timedelta(days=7)].sort_values("start", ascending=False)
if recent.empty:
    st.caption("No activities in the last 7 days.")
else:
    listing = pd.DataFrame({
        "When": recent["start"].dt.strftime("%a %d %b %H:%M"),
        "Sport": recent["sport"],
        "km": recent["distance_km"].round(1),
        "min": recent["duration_min"].round(0),
        "Avg HR": recent["avg_hr"],
        "Effort": recent["relative_effort"],
        "Strava": recent["activity_id"].map(links.strava_url),
        "Garmin": recent["garmin_activity_id"].map(links.garmin_url)
        if "garmin_activity_id" in recent else None,
        "Stats": recent["activity_id"].map(lambda a: links.sfs_url(cfg.sfs_url, a)),
    })
    if cfg.sfs_url is None:
        listing = listing.drop(columns="Stats")
    if listing["Garmin"].isna().all():
        listing = listing.drop(columns="Garmin")
    link = st.column_config.LinkColumn(display_text="open")
    picked = st.dataframe(listing, hide_index=True, on_select="rerun", selection_mode="single-row",
                          column_config={"Strava": link, "Stats": link, "Garmin": link}, key="recent")
    if picked.selection.rows:
        st.session_state["activity_id"] = recent["activity_id"].iloc[picked.selection.rows[0]]
        st.switch_page("pages/2_Activity.py")
    st.caption("Select a row to open it on the Activity page.")

common.footer(acts, states)
