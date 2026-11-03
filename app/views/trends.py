"""Trends: am I getting fitter?"""

import pandas as pd
import plotly.express as px
import streamlit as st

from myrun import bands, dynamics, fmt, links, metrics, optional, trends
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


def _titled(figure, x, y, legend=None):
    """Human axis titles (and legend title) on a Plotly Express figure."""
    figure.update_layout(xaxis_title=fmt.label(x), yaxis_title=fmt.label(y))
    if legend:
        figure.update_layout(legend_title_text=fmt.label(legend))
    return figure


tabs = st.tabs(["Fitness", "Volume", "Efforts", "Dynamics", "Gear", "Races", "Wellness"])


with tabs[0]:
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

    # ---- like for like: HR by pace band, per year ------------------------------
    st.subheader("Like for like, year on year")
    st.caption("Is a lower heart rate fitness, or an easier mix and more trail? Runs are compared "
               "only with runs of the same surface and grade-adjusted pace band. Each run counts "
               "by its core (first and last km and lap dropped); races, intervals and unsteady "
               "workout-lap runs are left out. Heart rate is corrected for a change of watch "
               "where enough runs on both watches allow fitting the offset (see the fitness "
               "report). Open markers: fewer than "
               f"{bands.NOISY_RUNS} runs in that cell.")
    picked = st.multiselect("Only these months each year (same season)", list(range(1, 13)),
                            format_func=lambda m: pd.Timestamp(2000, m, 1).strftime("%b"))
    season = tuple(sorted(picked)) or None
    this_year = pd.Timestamp.today().year
    first_year = st.slider("From year", this_year - 10, this_year, this_year - 5)

    yearly_eff = bands.since_year(common.cached("efficiency_yearly", cfg, season), first_year, "year")
    if len(yearly_eff):
        st.markdown("**Aerobic efficiency per year** (easy flat road runs, monthly medians "
                    "weighted by run count)")
        st.plotly_chart(common.figure("efficiency_yearly", cfg,
                                      lambda: charts.efficiency_year_bars(yearly_eff),
                                      season, first_year))

    band_cells = bands.since_year(common.cached("band_table", cfg, "year", season), first_year)
    for surface in bands.SURFACES:
        cells = band_cells[band_cells["surface"] == surface]
        if cells.empty:
            continue
        st.markdown(f"**{surface.title()}: heart rate by pace band**")
        st.plotly_chart(common.figure(
            "band_hr", cfg, lambda: charts.band_hr_lines(cells, bands.PACE_BANDS),
            surface, season, first_year), key=f"band-hr-{surface}")

    mix = bands.since_year(common.cached("intensity_yearly", cfg, season), first_year, "year")
    if len(mix):
        st.markdown("**Training mix per year** (share of running minutes, Garmin training effect)")
        st.plotly_chart(common.figure("intensity_yearly", cfg,
                                      lambda: charts.intensity_share_bars(mix), season, first_year))

    # ---- VO2max and intensity (Garmin) -----------------------------------------
    vo2max = common.cached("vo2max_trend", cfg)
    if len(vo2max):
        st.subheader("VO2max")
        st.plotly_chart(common.figure(
            "vo2max", cfg, lambda: charts.trend_line(vo2max, "month", "value", "VO2max")))
        st.caption("Garmin's estimate, monthly median over runs.")

    if "aerobic_te" in runs and runs["aerobic_te"].notna().any():
        st.subheader("Intensity")
        span = st.radio("Weeks", [12, 26, 52], horizontal=True)
        st.plotly_chart(common.figure(
            "intensity", cfg,
            lambda: charts.intensity_bars(common.cached("intensity_weekly", cfg, span)), span))
        st.caption(f"Running minutes per week by session intensity, from Garmin's training effect: "
                   f"hard is an aerobic effect of {metrics.HARD_AEROBIC_TE:g} or more or an "
                   f"anaerobic effect of {metrics.HARD_ANAEROBIC_TE:g} or more, steady an aerobic "
                   f"effect of {metrics.STEADY_AEROBIC_TE:g} or more, the rest easy.")

    if not (len(vo2max) or ("aerobic_te" in runs and runs["aerobic_te"].notna().any())):
        st.caption("Needs the Garmin activities file.")

with tabs[1]:
    # ---- volume ---------------------------------------------------------------
    st.subheader("Volume")
    left, right = st.columns(2)
    by = left.radio("Per", ["week", "month", "year"], index=1, horizontal=True)
    measure = right.radio("Measure", ["distance_km", "duration_h", "elevation_m"],
                         format_func=fmt.label, horizontal=True)
    st.plotly_chart(common.figure(
        "volume", cfg, lambda: _titled(theme.style(
            px.bar(common.cached("volume", cfg, by), x="period", y=measure, color="sport",
                    category_orders={"sport": list(fmt.SPORT_GROUPS)}),
            height=360), "period", measure, "sport"),
        by, measure))
    if len(runs):
        st.caption("Running distance, cumulative through each year.")
        st.plotly_chart(common.figure(
            "year_over_year", cfg, lambda: _titled(theme.style(px.line(
                trends.year_over_year(runs), x="day_of_year", y="cumulative_km", color="year"),
                height=360), "day_of_year", "cumulative_km", "year")))


with tabs[2]:
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
            figure.update_yaxes(autorange="reversed",
                                **(dict(tickmode="array", tickvals=vals, ticktext=text) if vals else {}))
            return _titled(theme.style(figure, height=360), "date", "time", "kind")

        st.plotly_chart(common.figure("best_efforts", cfg, _efforts_figure, int(distance)))


with tabs[3]:
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

    if not dynamic_columns:
        st.caption("Needs the Garmin activities file.")

with tabs[4]:
    # ---- shoes -----------------------------------------------------------------
    shoes = common.cached("shoes", cfg)
    if len(shoes):
        st.subheader("Shoes")
        table = pd.DataFrame({
            "Shoe": shoes["name"], "km": shoes["km"].round(0), "Runs": shoes["runs"],
            "Last used": shoes["last_used"],
            "Status": [trends.shoe_status(km, retired)
                       for km, retired in zip(shoes["km"], shoes["retired"])],
        })
        st.dataframe(table, hide_index=True, column_config={
            "Shoe": st.column_config.Column("Shoe"), "km": st.column_config.NumberColumn("km"),
            "Runs": st.column_config.NumberColumn("Runs"),
            "Last used": st.column_config.DateColumn("Last used", format="DD MMM YYYY"),
            "Status": st.column_config.Column("Status")})
        st.caption(f"Running distance per shoe from Strava gear. Worth a check from "
                   f"{trends.SHOE_CHECK_KM:g} km; past {trends.SHOE_LIMIT_KM:g} km a pair is due "
                   "for walking only.")

    if not len(shoes):
        st.caption("No shoes recorded in the Strava gear.")

with tabs[5]:
    # ---- races ----------------------------------------------------------------
    races, race_state = common.cached("races", cfg)
    if race_state.status != "off":
        st.subheader("Races")
        if races is not None:
            races = common.cached("races_linked", cfg)
            kinds = []
            if "type" in races:
                kinds = st.multiselect("Type", sorted(races["type"].dropna().unique()))
                if kinds:
                    races = races[races["type"].isin(kinds)]
            if "rank_pct" in races and races["rank_pct"].notna().any():
                def _rank_figure():
                    figure = px.scatter(races, x="date", y="rank_pct", hover_name="name",
                                        color="type" if "type" in races else None)
                    figure.update_yaxes(autorange="reversed")
                    return _titled(theme.style(figure, height=360), "date", "rank_pct", "type")

                st.plotly_chart(common.figure("race_rank", cfg, _rank_figure, tuple(kinds)))
            shown = races.sort_values("date", ascending=False)
            config = {c: st.column_config.Column(fmt.label(c)) for c in shown.columns}
            config.update({c: st.column_config.LinkColumn(fmt.label(c), display_text="open")
                           for c in ("garmin_url", "strava_url", "diploma_url") if c in shown})
            config["date"] = st.column_config.DateColumn(fmt.label("date"), format="DD MMM YYYY")
            st.dataframe(shown, hide_index=True, column_config=config)

    if race_state.status == "off":
        st.caption("Needs the race log file.")

with tabs[6]:
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
                return _titled(theme.style(px.line(monthly, x="month", y=column, markers=True),
                                           height=320), "month", column)

            for column in present:
                st.plotly_chart(common.figure("wellness", cfg, lambda: _wellness_figure(column), column),
                                key=f"wellness-{column}")

    if wellness_state.status == "off":
        st.caption("Needs the wellness file.")

common.footer(acts, states)
