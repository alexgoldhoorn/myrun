"""Dashboard: how am I doing right now?"""

import datetime as dt

import pandas as pd
import streamlit as st

from myrun import links
from myrun.ui import cards, charts, common

cfg = common.setup("Dashboard")
acts = common.load_activities(cfg)
states = common.cached("input_states", cfg)
today = pd.Timestamp(dt.date.today())

common.banner(states)
st.title("Dashboard")
if acts.empty:
    st.info("No activities in the database yet.")
    common.footer(acts, states)
    st.stop()

# ---- header strip ---------------------------------------------------------
plan, plan_state = common.cached("plan", cfg)
strip = []
if plan is not None:
    upcoming = plan[(plan["type"] == "race") & (plan["date"] >= today)]
    if len(upcoming):
        race = upcoming.iloc[0]
        days = (race["date"] - today).days
        when = "today" if days == 0 else f"in {days} day" + ("" if days == 1 else "s")
        strip.append(("Next race", f"{race['session']}, {race['date']:%a %d %b}, {when}"))
    else:
        strip.append(("Next race", "none in the plan"))
strip.append(("Newest activity", f"{acts['start'].max():%a %d %b %H:%M}"))
st.markdown(cards.strip_html(strip), unsafe_allow_html=True)
build_up = cards.readiness_html(common.cached("race_readiness", cfg))
if build_up:
    st.markdown(build_up, unsafe_allow_html=True)

# ---- cards ----------------------------------------------------------------
numbers = common.cached("headline", cfg)
st.subheader("Volume")
cards.card_row(numbers["volume"])
st.subheader("Consistency")
cards.card_row(numbers["consistency"])
st.caption("Training days, last 12 weeks: one column per week, Monday on top; darker is longer.")
st.markdown(cards.calendar_html(common.cached("training_days", cfg, 12)), unsafe_allow_html=True)
st.subheader("Load and fitness")
cards.card_row(numbers["fitness"])

wellness, wellness_state = common.cached("wellness", cfg)
if wellness_state.status != "off":
    st.subheader("Recovery")
    usable = common.notice(wellness_state)
    cards.card_row(numbers["recovery"])
    if usable and any(card.value is not None for card in numbers["recovery"]):
        st.caption(f"Values for {wellness['date'].iloc[-1]:%a %d %b}.")

# ---- charts ---------------------------------------------------------------
left, middle, right = st.columns(3)
with left:
    st.subheader("Weekly load")
    st.plotly_chart(common.figure("weekly_load", cfg,
                                  lambda: charts.load_bars(common.cached("weekly_load", cfg, 12))))
with right:
    st.subheader("Easy pace, 12 weeks")
    st.plotly_chart(common.figure(
        "easy_pace", cfg, lambda: charts.easy_pace_line(common.cached("weekly_runs", cfg, 12))))
with middle:
    st.subheader("Weekly running km")
    st.plotly_chart(common.figure(
        "weekly_km", cfg, lambda: charts.weekly_km_bars(common.cached("weekly_runs", cfg, 12))))

# ---- this week ------------------------------------------------------------
st.subheader("This week")
week = common.cached("plan_vs_actual", cfg)
table = pd.DataFrame({"Day": week["date"].dt.strftime("%a %d %b"), "Done": week["actual"]})
if plan is not None:
    table.insert(1, "Planned", week["planned"])
st.dataframe(table, hide_index=True)
run_km = week["actual_run_km"].sum()
if plan is not None and week["planned_km"].notna().any():
    st.caption(f"Running: {run_km:.1f} km done of {week['planned_km'].sum():.1f} km planned.")
else:
    st.caption(f"Running: {run_km:.1f} km so far this week.")

# ---- recent runs ----------------------------------------------------------
st.subheader("Recent runs")
recent = acts[acts["date"] > today - pd.Timedelta(days=7)].sort_values("start", ascending=False)
if recent.empty:
    st.caption("No activities in the last 7 days.")
else:
    listing = pd.DataFrame({
        "When": recent["start"].dt.strftime("%a %d %b %H:%M"),
        "Sport": recent["sport"],
        "Session": recent["session_name"] if "session_name" in recent else None,
        "km": recent["distance_km"].round(1),
        "min": recent["duration_min"].round(0),
        "Avg HR": recent["avg_hr"],
        "Effort": recent["relative_effort"],
        "Strava": recent["activity_id"].map(links.strava_url),
        "Garmin": recent["garmin_activity_id"].map(links.garmin_url)
        if "garmin_activity_id" in recent else None,
        "Stats": recent["activity_id"].map(lambda a: links.sfs_url(cfg.sfs_url, a)),
    })
    listing = listing.drop(columns=[c for c in ("Session", "Garmin", "Stats")
                                    if listing[c].isna().all()])
    link = st.column_config.LinkColumn(display_text="open")
    picked = st.dataframe(listing, hide_index=True, on_select="rerun", selection_mode="single-row",
                          column_config={"Strava": link, "Garmin": link, "Stats": link},
                          key="recent")
    if picked.selection.rows:
        st.session_state["activity_id"] = recent["activity_id"].iloc[picked.selection.rows[0]]
        st.switch_page("pages/2_Activity.py")
    st.caption("Select a row to open it on the Activity page.")

common.footer(acts, states)
