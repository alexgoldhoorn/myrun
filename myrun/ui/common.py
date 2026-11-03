"""Shared Streamlit plumbing: page setup, cached loaders, notices, footer."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from myrun import bands, dynamics, fmt, links, metrics, optional, streams, trends
from myrun.activities import activities
from myrun.config import RUN_SPORTS, Config, ConfigError, load_config
from myrun.hr import hr_settings
from myrun.load import weekly_load
from myrun.optional import InputState
from myrun.planmatch import plan_vs_actual
from myrun.splits import splits
from myrun.stravadb import StravaDbError, db_mtime, open_db
from myrun.ui import theme


def setup(title: str) -> Config:
    """First call of every page. Stops the page with one error if it cannot start."""
    if not st.session_state.get("_mr_nav"):   # the router in app/Dashboard.py sets this itself
        st.set_page_config(page_title=f"myrun · {title}", layout="wide")
    theme.apply()
    try:
        cfg = load_config()
        open_db(cfg).close()
    except (ConfigError, StravaDbError) as exc:
        st.error(f"myrun cannot start: {exc}")
        st.stop()
    return cfg


def _mtime(path: Path | None) -> float:
    try:
        return path.stat().st_mtime if path else 0.0
    except OSError:
        return 0.0


_log = logging.getLogger("myrun.cache")   # one debug line per real computation (a cache miss)
CACHE_TTL_S = 300        # bounds how long an input's age or status can lag on screen
CACHE_ENTRIES = 64         # per cache; stream tables and figures are the large ones


def _today() -> pd.Timestamp:
    return pd.Timestamp(dt.date.today())


def _key(cfg: Config) -> tuple:
    """Everything a result depends on besides its arguments: config, input files, the day."""
    inputs = (cfg.plan_csv, cfg.race_log_csv, cfg.garmin_activities, cfg.wellness_parquet)
    return (repr(cfg), db_mtime(cfg.strava_db).timestamp(), tuple(_mtime(p) for p in inputs),
            _today().toordinal())


@st.cache_data(show_spinner=False, max_entries=8)
def _activities(_cfg: Config, key: tuple) -> pd.DataFrame:
    _log.debug("computing activities")
    return activities(cfg=_cfg)


@st.cache_data(show_spinner="Computing per-km splits (slow only the first time)", max_entries=4)
def _splits(_cfg: Config, key: tuple) -> pd.DataFrame:
    return splits(cfg=_cfg)


def load_activities(cfg: Config) -> pd.DataFrame:
    return _activities(cfg, _key(cfg))


def load_splits(cfg: Config) -> pd.DataFrame:
    return _splits(cfg, _key(cfg))


def _runs_only(acts: pd.DataFrame) -> pd.DataFrame:
    return acts[acts["sport"].isin(RUN_SPORTS)]


def _activity_dynamics(cfg: Config, activity_id: str) -> list:
    acts = load_activities(cfg)
    return dynamics.activity_dynamics(acts.set_index("activity_id").loc[activity_id],
                                      _runs_only(acts))


def _races_linked(cfg: Config) -> pd.DataFrame | None:
    races = optional.read_races(cfg)[0]
    return None if races is None else links.fill_race_garmin_urls(races, load_activities(cfg))


# Every table and number a page shows, by name. Each takes the config and plain arguments,
# so one cache covers them all and a rerun (a widget click, another visitor) computes nothing.
COMPUTE = {
    "input_states": lambda cfg: optional.input_states(cfg),
    "plan": lambda cfg: optional.read_plan(cfg),
    "wellness": lambda cfg: optional.read_wellness(cfg),
    "races": lambda cfg: optional.read_races(cfg),
    "races_linked": _races_linked,
    "hr_settings": lambda cfg: hr_settings(cfg, load_activities(cfg)),
    "headline": lambda cfg: metrics.headline(activities=load_activities(cfg), cfg=cfg),
    "weekly_load": lambda cfg, weeks: weekly_load(weeks, activities=load_activities(cfg), cfg=cfg),
    "weekly_runs": lambda cfg, weeks: metrics.weekly_runs(weeks, activities=load_activities(cfg),
                                                          cfg=cfg),
    "plan_vs_actual": lambda cfg: plan_vs_actual(activities=load_activities(cfg), cfg=cfg),
    "efficiency": lambda cfg: trends.aerobic_efficiency(activities=load_activities(cfg), cfg=cfg),
    "volume": lambda cfg, by: trends.volume(by, activities=load_activities(cfg),
                                           group_sports=True),
    "best_efforts": lambda cfg: trends.best_efforts(cfg=cfg),
    "shoes": lambda cfg: trends.shoes(cfg=cfg),
    "training_days": lambda cfg, weeks: metrics.training_days(
        weeks, activities=load_activities(cfg), cfg=cfg),
    "race_readiness": lambda cfg: metrics.race_readiness(
        _runs_only(load_activities(cfg)), optional.read_plan(cfg)[0], _today()),
    "vo2max_trend": lambda cfg: metrics.vo2max_trend(load_activities(cfg)),
    "intensity_weekly": lambda cfg, weeks: metrics.intensity_weekly(
        weeks, activities=load_activities(cfg), cfg=cfg),
    "dynamics_trend": lambda cfg, column: dynamics.dynamics_trend(
        column, activities=load_activities(cfg), cfg=cfg),
    "streams": lambda cfg, activity_id: streams.activity_streams(activity_id, cfg=cfg),
    "laps": lambda cfg, activity_id: streams.activity_laps(activity_id, cfg=cfg),
    "drift": lambda cfg, activity_id: streams.drift_pct(cached("streams", cfg, activity_id)),
    "activity_dynamics": _activity_dynamics,
    "band_runs": lambda cfg: bands.band_runs(activities=load_activities(cfg), cfg=cfg),
    "band_table": lambda cfg, by, season: bands.band_table(cached("band_runs", cfg), by, season),
    "efficiency_yearly": lambda cfg, season: bands.yearly_efficiency(
        activities=load_activities(cfg), cfg=cfg, season=season),
    "intensity_yearly": lambda cfg, season: bands.intensity_yearly(
        activities=load_activities(cfg), cfg=cfg, season=season),
}


# Results that judge an input's age against the clock. A file can go stale without changing,
# so these are refreshed on a timer; the rest live until an input file or the day changes.
CLOCKED = frozenset({"input_states", "wellness", "headline"})


@st.cache_data(show_spinner=False, max_entries=CACHE_ENTRIES)
def _cached(name: str, _cfg: Config, key: tuple, args: tuple):
    _log.debug("computing %s %s", name, args)
    return COMPUTE[name](_cfg, *args)


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_S, max_entries=CACHE_ENTRIES)
def _cached_clocked(name: str, _cfg: Config, key: tuple, args: tuple):
    _log.debug("computing %s %s", name, args)
    return COMPUTE[name](_cfg, *args)


def drop_clocked() -> None:
    """Forget the timed results, so the next call computes them. For the warm-up."""
    _cached_clocked.clear()


def cached(name: str, cfg: Config, *args):
    """COMPUTE[name](cfg, *args), computed once until an input file or the day changes."""
    if name not in COMPUTE:
        raise KeyError(f"no cached result named {name!r}; known: {', '.join(sorted(COMPUTE))}")
    return (_cached_clocked if name in CLOCKED else _cached)(name, cfg, _key(cfg), args)


@st.cache_data(show_spinner=False, max_entries=CACHE_ENTRIES)
def _figure(name: str, _build, key: tuple, args: tuple):
    _log.debug("building figure %s %s", name, args)
    return _build()


def figure(name: str, cfg: Config, build, *args):
    """build(), a Plotly figure, built once per name and arguments.

    Building a figure costs more than the numbers behind it. `args` must name everything
    the figure depends on besides the inputs: the widget choices that shape it."""
    return _figure(name, build, _key(cfg), args)


def notice(state: InputState) -> bool:
    """Warn about a stale or broken input. True only when the input is usable as current."""
    if state.status in ("stale", "error"):
        st.warning(f"**{state.name}**: {state.message}")
    return state.status == "ok"


# These inputs shape activities() itself (session types, surfaces, Garmin columns), so
# every page consumes them and every page must say when one is stale or broken.
FEEDS_ACTIVITIES = ("plan", "race_log", "garmin_activities")


def banner(states: dict[str, InputState], page: str = "") -> None:
    strava = states["strava_db"]
    if strava.status != "ok":
        st.error(f"**Activities may be out of date**: {strava.message}")
    for name in FEEDS_ACTIVITIES:
        state = states[name]
        if state.status == "empty":     # a status, not a fault: only the Dashboard says it
            if page == "Dashboard":
                st.info(f"**{state.name}**: {state.message}")
            continue
        notice(state)


def footer(acts: pd.DataFrame, states: dict[str, InputState]) -> None:
    parts = []
    if len(acts):
        parts.append(f"Newest activity: {acts['start'].max():%a %d %b %Y %H:%M}")
    for state in states.values():
        if state.status == "off":
            continue
        age = f", {state.age_hours:.0f} h old" if state.age_hours is not None else ""
        parts.append(f"{fmt.label(state.name)}: {state.status}{age}")
    st.divider()
    st.caption(" · ".join(parts))
