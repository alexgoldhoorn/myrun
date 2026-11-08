"""The numbers behind the dashboard: weekly tables, intensity, race readiness, the heat fit.

No Streamlit here: usable from a notebook. The cards built from them live in
`myrun.headline_cards`; their names are still reachable here (`metrics.headline` etc.)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.dates import between, last_days, monday_of, today_ts, week_range, week_starts
from myrun.metric import clean
from myrun.optional import NON_RUN_PLAN_TYPES, read_plan
from myrun.trends import easy_runs

# Thresholds. Each says where its value comes from: "confirmed" by the owner, "Garmin" for
# Garmin's own scale, "fitted" from the data at run time, or "chosen": a judgement call that
# no data backs, to be changed here when it reads wrong on the dashboard.
TREND_WEEKS = 12               # chosen: weeks in a card's trend line and in the weekly charts
STEADY_AEROBIC_TE = 3.0        # Garmin: training effect 3.0-3.9 is "improving"
HARD_AEROBIC_TE = 4.0          # Garmin: 4.0 and up is "highly improving"
HARD_ANAEROBIC_TE = 2.0        # Garmin: 2.0 and up, the session had real anaerobic work
INTENSITIES = ("easy", "steady", "hard")
# What a degree of warmth costs in easy pace is fitted from the runner's own easy runs
# (heat_cost), not assumed: a fixed "3 °C explains it" rule did not hold on real data.
HEAT_FIT_DAYS = 730            # chosen: two full years, so every season counts twice
HEAT_MIN_RUNS = 30             # chosen: fewer easy runs with a temperature give no usable fit
# chosen, after the owner said the build-up depends on the distance:
BUILD_WEEKS = ((15.0, 6), (30.0, 8), (float("inf"), 12))   # race km below -> build-up weeks compared
DEFAULT_BUILD_WEEKS = 8        # chosen: when the race distance is unknown
ROAD_RACE_SHARE = 0.05         # confirmed ("very close"): an earlier road race within 5 % of the distance
ROAD_RACE_CLIMB_M = 100.0      # confirmed: ... and within 100 m of climb, when the coming race's is known
TRAIL_RACE_SHARE = 0.25        # confirmed (10-25 %): trail, within 25 % of distance and of climb when known


def weekly_runs(weeks: int = TREND_WEEKS, *, activities: pd.DataFrame | None = None, today=None,
                cfg: Config | None = None) -> pd.DataFrame:
    """Running per week (Monday start), oldest first, the current week last.

    Columns: week_start, run_km, elevation_m, longest_km, n_runs, easy_pace_min_km (median
    pace of easy runs, NaN when there were none) and planned_km (from the plan input, NaN
    without one). Weeks without runs are present with zeros."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    now = today_ts(today)
    all_weeks = week_range(now, weeks)
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    runs = between(runs, all_weeks[0], now).copy()
    runs["week_start"] = week_starts(runs["date"])
    out = runs.groupby("week_start").agg(
        run_km=("distance_km", "sum"), elevation_m=("elevation_m", "sum"),
        longest_km=("distance_km", "max"), n_runs=("activity_id", "count"),
    ).reindex(all_weeks, fill_value=0).rename_axis("week_start").reset_index()
    out = out.astype({"run_km": "float64", "elevation_m": "float64", "longest_km": "float64",
                      "n_runs": "int64"})

    easy = easy_runs(acts, cfg)
    easy = between(easy, all_weeks[0], now).copy()
    easy["week_start"] = week_starts(easy["date"])
    out["easy_pace_min_km"] = out["week_start"].map(
        easy.groupby("week_start")["pace_min_km"].median()).astype("float64")

    plan, _ = read_plan(cfg, today=now)
    out["planned_km"] = float("nan")
    if plan is not None:
        runs_planned = plan[~plan["type"].isin(NON_RUN_PLAN_TYPES)].copy()
        runs_planned["week_start"] = week_starts(runs_planned["date"])
        per_week = runs_planned.groupby("week_start")["distance_km"].sum(min_count=1)
        out["planned_km"] = out["week_start"].map(per_week).astype("float64")
    return out


def intensity(runs: pd.DataFrame) -> pd.Series:
    """easy, steady or hard per run from Garmin's training effect; None without one."""
    aerobic = pd.to_numeric(runs["aerobic_te"], errors="coerce")
    anaerobic = (pd.to_numeric(runs["anaerobic_te"], errors="coerce").fillna(0.0)
                 if "anaerobic_te" in runs.columns else pd.Series(0.0, index=runs.index))
    out = pd.Series("easy", index=runs.index, dtype="object")
    out[aerobic >= STEADY_AEROBIC_TE] = "steady"
    out[(aerobic >= HARD_AEROBIC_TE) | (anaerobic >= HARD_ANAEROBIC_TE)] = "hard"
    out[aerobic.isna()] = None
    return out


def intensity_weekly(weeks: int = TREND_WEEKS, *, activities: pd.DataFrame | None = None,
                     today=None, cfg: Config | None = None) -> pd.DataFrame:
    """Running minutes per week (Monday start) in easy, steady and hard sessions."""
    acts = activities if activities is not None else _load(cfg=cfg or load_config())
    now = today_ts(today)
    all_weeks = week_range(now, weeks)
    columns = [f"{kind}_min" for kind in INTENSITIES]
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    runs = between(runs, all_weeks[0], now)
    if "aerobic_te" not in runs.columns or runs.empty:
        out = pd.DataFrame(0.0, index=all_weeks, columns=columns)
    else:
        week = week_starts(runs["date"])
        rated = runs.assign(week_start=week, kind=intensity(runs)).dropna(subset=["kind"])
        out = (rated.pivot_table(index="week_start", columns="kind", values="duration_min",
                                 aggfunc="sum", fill_value=0.0)
               .reindex(index=all_weeks, columns=list(INTENSITIES), fill_value=0.0))
        out.columns = columns
        # a week with runs and none of them rated is unknown, not a week without running
        out.loc[out.index.isin(week) & ~out.index.isin(rated["week_start"])] = float("nan")
    return out.astype("float64").rename_axis("week_start").reset_index()


def vo2max_trend(activities: pd.DataFrame) -> pd.DataFrame:
    """Monthly median of Garmin's VO2max estimate on runs, from the first month with data."""
    empty = pd.DataFrame(columns=["month", "value", "n_runs"])
    if "vo2max" not in activities.columns:
        return empty
    runs = activities[activities["sport"].isin(RUN_SPORTS)].dropna(subset=["vo2max"])
    if runs.empty:
        return empty
    runs = runs.assign(month=runs["date"].dt.to_period("M").dt.start_time)
    return runs.groupby("month", as_index=False).agg(value=("vo2max", "median"),
                                                     n_runs=("activity_id", "count"))


def heat_cost(easy: pd.DataFrame, now: pd.Timestamp) -> float | None:
    """Minutes per km that one °C of warmth costs this runner at easy effort.

    A straight-line fit of pace on temperature over the easy runs of the last HEAT_FIT_DAYS.
    None without HEAT_MIN_RUNS runs at different temperatures. Never below zero: a fit that
    says heat makes the runner faster is noise."""
    if "temp_c" not in easy.columns:
        return None
    runs = last_days(easy, now, HEAT_FIT_DAYS).dropna(subset=["temp_c", "pace_min_km"])
    if len(runs) < HEAT_MIN_RUNS or runs["temp_c"].nunique() < 2:
        return None
    slope = np.polyfit(runs["temp_c"].astype(float), runs["pace_min_km"].astype(float), 1)[0]
    return max(0.0, float(slope))


def training_days(weeks: int = TREND_WEEKS, *, activities: pd.DataFrame | None = None,
                  today=None, cfg: Config | None = None) -> pd.DataFrame:
    """Minutes and number of activities (every sport) per day over whole weeks, Monday first.

    Days after today are NaN: they have not happened, which is not the same as a rest day."""
    acts = activities if activities is not None else _load(cfg=cfg or load_config())
    now = today_ts(today)
    monday = monday_of(now)
    dates = pd.date_range(monday - pd.Timedelta(weeks=weeks - 1), periods=7 * weeks, freq="D")
    minutes = acts.groupby("date")["duration_min"].sum().reindex(dates, fill_value=0.0)
    minutes[minutes.index > now] = float("nan")
    count = acts.groupby("date").size().reindex(dates, fill_value=0)
    return pd.DataFrame({"date": dates, "minutes": minutes.to_numpy(dtype="float64"),
                         "activities": count.to_numpy(dtype="int64")})


def build_weeks(distance_km: float | None) -> int:
    """How many weeks of build-up to compare: longer races are prepared for longer."""
    if distance_km is None:
        return DEFAULT_BUILD_WEEKS
    return next(weeks for below, weeks in BUILD_WEEKS if distance_km < below)


def _build_up(runs: pd.DataFrame, end: pd.Timestamp, weeks: int) -> dict:
    window = last_days(runs, end, days=7 * weeks)
    return {"km": float(window["distance_km"].sum()),
            "longest_km": float(window["distance_km"].max()) if len(window) else 0.0}


def race_readiness(runs: pd.DataFrame, plan: pd.DataFrame | None, now: pd.Timestamp) -> dict | None:
    """The build-up to the next planned race, against the same point before the last
    similar race. None without a plan or without a race ahead in it.

    Similar means the same kind and close: road races are compared by time, so only a road
    race of nearly the same distance (and climb, when known) counts; trail races differ
    in everything, so a quarter of difference in distance and climb is allowed. The kind
    is the plan's `surface`, or "trail" when the session name says so, else road.

    {race, date, days_to_go, weeks, km, longest_km, previous: {name, date, km, longest_km} | None}"""
    if plan is None:
        return None
    ahead = plan[(plan["type"] == "race") & (plan["date"] >= now)].sort_values("date")
    if ahead.empty:
        return None
    race = ahead.iloc[0]
    days_to_go = int((race["date"] - now).days)
    distance = clean(race.get("distance_km"))
    weeks = build_weeks(distance)
    # On race day both windows end the day before, so neither holds a race.
    gap = pd.Timedelta(days=1 if days_to_go == 0 else 0)
    out = {"race": str(race["session"]), "date": race["date"], "days_to_go": days_to_go,
           "weeks": weeks, **_build_up(runs, now - gap, weeks), "previous": None}
    if distance is None or "session_type" not in runs.columns:
        return out
    surface = race.get("surface")
    trail = surface == "trail" or (surface != "road" and "trail" in str(race["session"]).lower())
    share = TRAIL_RACE_SHARE if trail else ROAD_RACE_SHARE
    similar = runs[(runs["session_type"] == "race") & (runs["date"] < now)
                   & ((runs["distance_km"] - distance).abs() <= share * distance)]
    if "surface" in runs.columns:
        # "mixed" is a hilly run on the road sport type: it can stand for either kind
        similar = similar[similar["surface"] != ("road" if trail else "trail")]
    climb = clean(race.get("elevation_m"))
    if climb is not None and "elevation_m" in runs.columns:
        allowed = TRAIL_RACE_SHARE * climb if trail else ROAD_RACE_CLIMB_M
        similar = similar[(similar["elevation_m"] - climb).abs() <= allowed]
    if similar.empty:
        return out
    last = similar.sort_values("date").iloc[-1]
    name = last.get("race_name")
    out["previous"] = {"name": name if isinstance(name, str) and name else f"{last['date']:%d %b %Y}",
                       "date": last["date"],
                       **_build_up(runs, last["date"] - pd.Timedelta(days=days_to_go) - gap, weeks)}
    return out




def __getattr__(name: str):
    """The card builders moved to `myrun.headline_cards`; `metrics.<name>` keeps working.

    Looked up lazily because that module imports this one."""
    from myrun import headline_cards

    try:
        return getattr(headline_cards, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
