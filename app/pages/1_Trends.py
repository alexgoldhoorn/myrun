"""Trends: am I getting fitter?"""

import pandas as pd
import plotly.express as px
import streamlit as st

from myrun import fmt, optional, trends
from myrun.config import RUN_SPORTS
from myrun.hr import hr_settings
from myrun.ui import common

cfg = common.setup("Trends")
acts = common.load_activities(cfg)
states = optional.input_states(cfg)

common.banner(states)
st.title("Trends")
if acts.empty:
    st.info("No activities in the database yet.")
    common.footer(acts, states)
    st.stop()
runs = acts[acts["sport"].isin(RUN_SPORTS)]

# ---- aerobic efficiency ---------------------------------------------------
st.subheader("Aerobic efficiency")
heart = hr_settings(cfg, acts)
efficiency = trends.aerobic_efficiency(activities=acts, cfg=cfg)
if heart.easy_band is None:
    st.info(f"Easy heart-rate band {heart.source}.")
else:
    low, high = heart.easy_band
    st.caption(f"Metres per minute per heartbeat on easy road runs: average HR {low} to {high}, "
               f"at least {trends.MIN_EFFICIENCY_MINUTES} minutes, under "
               f"{cfg.efficiency_max_hilliness_m_per_km:g} m of climb per km. Higher is fitter. "
               f"The HR band is {heart.source}.")
if heart.easy_band is None:
    pass
elif efficiency.empty:
    st.info("No runs qualify. Set hr.easy_band in the config if the band above is not yours.")
else:
    shown = efficiency.assign(median_pace=efficiency["median_pace_min_km"].map(fmt.pace))
    st.plotly_chart(px.line(shown, x="month", y="efficiency", markers=True,
                            hover_data={"n_runs": True, "median_pace": True}))

# ---- volume ---------------------------------------------------------------
st.subheader("Volume")
left, right = st.columns(2)
by = left.radio("Per", ["week", "month", "year"], index=1, horizontal=True)
measure = right.radio("Measure", ["distance_km", "duration_h", "elevation_m"], horizontal=True)
st.plotly_chart(px.bar(trends.volume(by, activities=acts), x="period", y=measure, color="sport"))
if len(runs):
    st.caption("Running distance, cumulative through each year.")
    st.plotly_chart(px.line(trends.year_over_year(runs), x="day_of_year", y="cumulative_km",
                            color="year"))

# ---- best efforts ---------------------------------------------------------
st.subheader("Best efforts")
efforts = trends.best_efforts(cfg=cfg)
if efforts.empty:
    st.caption("No best efforts recorded.")
else:
    distance = st.selectbox("Distance (m)", sorted(efforts["distance_m"].unique()))
    chosen = efforts[efforts["distance_m"] == distance].copy()
    chosen["time"] = chosen["time_s"].map(fmt.duration)
    chosen["pace"] = chosen["pace_min_km"].map(fmt.pace)
    chosen["kind"] = chosen["is_record"].map({True: "record at the time", False: "other"})
    figure = px.scatter(chosen, x="date", y="time_s", color="kind",
                        hover_data={"time_s": False, "time": True, "pace": True})
    vals, text = fmt.duration_ticks(chosen["time_s"])
    figure.update_yaxes(autorange="reversed", title="Time",
                        **(dict(tickmode="array", tickvals=vals, ticktext=text) if vals else {}))
    st.plotly_chart(figure)

# ---- races ----------------------------------------------------------------
races, race_state = optional.read_races(cfg)
if race_state.status != "off":
    st.subheader("Races")
    if races is not None:
        if "type" in races:
            kinds = st.multiselect("Type", sorted(races["type"].dropna().unique()))
            if kinds:
                races = races[races["type"].isin(kinds)]
        if "rank_pct" in races and races["rank_pct"].notna().any():
            figure = px.scatter(races, x="date", y="rank_pct", hover_name="name",
                                color="type" if "type" in races else None)
            figure.update_yaxes(autorange="reversed", title="Rank percentile (lower is better)")
            st.plotly_chart(figure)
        links_config = {c: st.column_config.LinkColumn(display_text="open")
                        for c in ("garmin_url", "strava_url") if c in races}
        st.dataframe(races.sort_values("date", ascending=False), hide_index=True,
                     column_config=links_config)

# ---- wellness -------------------------------------------------------------
wellness, wellness_state = optional.read_wellness(cfg)
if wellness_state.status != "off":
    st.subheader("Wellness")
    common.notice(wellness_state)
    if wellness is not None:
        present = [c for c in optional.WELLNESS_COLUMNS if c in wellness.columns]
        monthly = (wellness.assign(month=wellness["date"].dt.to_period("M").dt.start_time)
                   .groupby("month", as_index=False)[present].mean())
        for column in present:
            st.plotly_chart(px.line(monthly, x="month", y=column, markers=True),
                            key=f"wellness-{column}")

common.footer(acts, states)
