"""Trends: am I getting fitter?"""

import plotly.express as px
import streamlit as st

from myrun import dynamics, fmt, links, optional, trends
from myrun.config import RUN_SPORTS
from myrun.ui import charts, common, theme

cfg = common.setup("Trends")
acts = common.load_activities(cfg)
states = common.cached("input_states", cfg)

common.banner(states)
st.title("Trends")
if acts.empty:
    st.info("No activities in the database yet.")
    common.footer(acts, states)
    st.stop()
runs = acts[acts["sport"].isin(RUN_SPORTS)]

# ---- aerobic efficiency ---------------------------------------------------
st.subheader("Aerobic efficiency")
heart = common.cached("hr_settings", cfg)
efficiency = common.cached("efficiency", cfg)
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
    def _efficiency_figure():
        shown = efficiency.assign(median_pace=efficiency["median_pace_min_km"].map(fmt.pace))
        return theme.style(px.line(shown, x="month", y="efficiency", markers=True,
                                   hover_data={"n_runs": True, "median_pace": True}), height=320)

    st.plotly_chart(common.figure("efficiency", cfg, _efficiency_figure))

# ---- volume ---------------------------------------------------------------
st.subheader("Volume")
left, right = st.columns(2)
by = left.radio("Per", ["week", "month", "year"], index=1, horizontal=True)
measure = right.radio("Measure", ["distance_km", "duration_h", "elevation_m"], horizontal=True)
st.plotly_chart(common.figure(
    "volume", cfg, lambda: theme.style(px.bar(common.cached("volume", cfg, by), x="period",
                                              y=measure, color="sport"), height=360),
    by, measure))
if len(runs):
    st.caption("Running distance, cumulative through each year.")
    st.plotly_chart(common.figure(
        "year_over_year", cfg, lambda: theme.style(px.line(
            trends.year_over_year(runs), x="day_of_year", y="cumulative_km", color="year"),
            height=360)))

# ---- best efforts ---------------------------------------------------------
st.subheader("Best efforts")
efforts = common.cached("best_efforts", cfg)
if efforts.empty:
    st.caption("No best efforts recorded.")
else:
    distance = st.selectbox("Distance (m)", sorted(efforts["distance_m"].unique()))
    def _efforts_figure():
        chosen = efforts[efforts["distance_m"] == distance].copy()
        chosen["time"] = chosen["time_s"].map(fmt.duration)
        chosen["pace"] = chosen["pace_min_km"].map(fmt.pace)
        chosen["kind"] = chosen["is_record"].map({True: "record at the time", False: "other"})
        figure = px.scatter(chosen, x="date", y="time_s", color="kind",
                            hover_data={"time_s": False, "time": True, "pace": True})
        vals, text = fmt.duration_ticks(chosen["time_s"])
        figure.update_yaxes(autorange="reversed", title="Time",
                            **(dict(tickmode="array", tickvals=vals, ticktext=text) if vals else {}))
        return theme.style(figure, height=360)

    st.plotly_chart(common.figure("best_efforts", cfg, _efforts_figure, int(distance)))

# ---- running dynamics -----------------------------------------------------
dynamic_columns = dynamics.available(runs)
if dynamic_columns:
    st.subheader("Running dynamics")
    column = st.selectbox("Metric", dynamic_columns,
                          format_func=lambda c: dynamics.DYNAMICS[c][0])
    trend = common.cached("dynamics_trend", cfg, column)
    if trend.empty:
        st.caption("No easy runs carry this value yet.")
    else:
        st.plotly_chart(common.figure(
            "dynamics_trend", cfg,
            lambda: charts.trend_line(trend, "month", "value", dynamics.DYNAMICS[column][0]),
            column))
        st.caption("Monthly median on easy, flat road runs, from the first month with data.")

# ---- races ----------------------------------------------------------------
races, race_state = common.cached("races", cfg)
if race_state.status != "off":
    st.subheader("Races")
    if races is not None:
        kinds = []
        if "type" in races:
            kinds = st.multiselect("Type", sorted(races["type"].dropna().unique()))
            if kinds:
                races = races[races["type"].isin(kinds)]
        if "rank_pct" in races and races["rank_pct"].notna().any():
            def _rank_figure():
                figure = px.scatter(races, x="date", y="rank_pct", hover_name="name",
                                    color="type" if "type" in races else None)
                figure.update_yaxes(autorange="reversed",
                                    title="Rank percentile (lower is better)")
                return theme.style(figure, height=360)

            st.plotly_chart(common.figure("race_rank", cfg, _rank_figure, tuple(kinds)))
        races = links.fill_race_garmin_urls(races, acts)
        links_config = {c: st.column_config.LinkColumn(display_text="open")
                        for c in ("garmin_url", "strava_url") if c in races}
        st.dataframe(races.sort_values("date", ascending=False), hide_index=True,
                     column_config=links_config)

# ---- wellness -------------------------------------------------------------
wellness, wellness_state = common.cached("wellness", cfg)
if wellness_state.status != "off":
    st.subheader("Wellness")
    common.notice(wellness_state)
    if wellness is not None:
        present = [c for c in optional.WELLNESS_COLUMNS if c in wellness.columns]
        def _wellness_figure(column):
            monthly = (wellness.assign(month=wellness["date"].dt.to_period("M").dt.start_time)
                       .groupby("month", as_index=False)[column].mean())
            return theme.style(px.line(monthly, x="month", y=column, markers=True), height=320)

        for column in present:
            st.plotly_chart(common.figure("wellness", cfg, lambda: _wellness_figure(column), column),
                            key=f"wellness-{column}")

common.footer(acts, states)
