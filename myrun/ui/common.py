"""Shared Streamlit plumbing: page setup, cached loaders, notices, footer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from myrun.activities import activities
from myrun.config import Config, ConfigError, load_config
from myrun.optional import InputState
from myrun.splits import splits
from myrun.stravadb import StravaDbError, db_mtime, open_db


def setup(title: str) -> Config:
    """First call of every page. Stops the page with one error if it cannot start."""
    st.set_page_config(page_title=f"myrun · {title}", layout="wide")
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


def _key(cfg: Config) -> tuple:
    inputs = (cfg.plan_csv, cfg.race_log_csv, cfg.garmin_activities_parquet)
    return (repr(cfg), db_mtime(cfg.strava_db).timestamp(), tuple(_mtime(p) for p in inputs))


@st.cache_data(show_spinner=False)
def _activities(_cfg: Config, key: tuple) -> pd.DataFrame:
    return activities(cfg=_cfg)


@st.cache_data(show_spinner="Computing per-km splits (slow only the first time)")
def _splits(_cfg: Config, key: tuple) -> pd.DataFrame:
    return splits(cfg=_cfg)


def load_activities(cfg: Config) -> pd.DataFrame:
    return _activities(cfg, _key(cfg))


def load_splits(cfg: Config) -> pd.DataFrame:
    return _splits(cfg, _key(cfg))


def notice(state: InputState) -> bool:
    """Warn about a stale or broken input. True only when the input is usable as current."""
    if state.status in ("stale", "error"):
        st.warning(f"**{state.name}**: {state.message}")
    return state.status == "ok"


# These inputs shape activities() itself (session types, surfaces, Garmin columns), so
# every page consumes them and every page must say when one is stale or broken.
FEEDS_ACTIVITIES = ("plan", "race_log", "garmin_activities")


def banner(states: dict[str, InputState]) -> None:
    strava = states["strava_db"]
    if strava.status != "ok":
        st.error(f"**Activities may be out of date**: {strava.message}")
    for name in FEEDS_ACTIVITIES:
        notice(states[name])


def footer(acts: pd.DataFrame, states: dict[str, InputState]) -> None:
    parts = []
    if len(acts):
        parts.append(f"Newest activity: {acts['start'].max():%a %d %b %Y %H:%M}")
    for state in states.values():
        if state.status == "off":
            continue
        age = f", {state.age_hours:.0f} h old" if state.age_hours is not None else ""
        parts.append(f"{state.name}: {state.status}{age}")
    st.divider()
    st.caption(" · ".join(parts))
