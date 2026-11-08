"""The dashboard's headline numbers. No Streamlit here: usable from a notebook."""

from __future__ import annotations

import numpy as np
import pandas as pd

from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.dates import monday_of, today_ts, week_range, week_starts
from myrun.load import load_status
from myrun.metric import Metric, clean
from myrun.optional import NON_RUN_PLAN_TYPES, read_plan, read_wellness
from myrun.trends import easy_runs

# Thresholds. Each says where its value comes from: "confirmed" by the owner, "Garmin" for
# Garmin's own scale, "fitted" from the data at run time, or "chosen": a judgement call that
# no data backs, to be changed here when it reads wrong on the dashboard.
TREND_WEEKS = 12               # chosen: weeks in a card's trend line and in the weekly charts
RECOVERY_DAYS = 14             # chosen: days in a recovery card's trend line
MIN_PLAN_DAYS = 7              # chosen: Plan done needs this many days covered by the plan
FEED_LAG_DAYS = 1              # chosen: days of activities without a Garmin load before the card says so
TONE_TOLERANCE = 0.05          # chosen: a change under 5 % is not coloured
_LOAD_TONES = {"low": "warn", "steady": "good", "high": "warn", "very high": "bad",
               "no data": "neutral"}
# column: (label, unit, higher is better)
_RECOVERY = {
    "readiness": ("Readiness", "score", True),
    "hrv_ms": ("HRV", "ms", True),
    "resting_hr": ("Resting HR", "bpm", False),
    "sleep_hours": ("Sleep", "hours", True),
    "body_battery": ("Body battery", "score", True),
    "stress": ("Stress", "score", False),
}
VO2MAX_STEP = 1.0              # Garmin: it reports whole numbers, so one point is a real change
STEADY_AEROBIC_TE = 3.0        # Garmin: training effect 3.0-3.9 is "improving"
HARD_AEROBIC_TE = 4.0          # Garmin: 4.0 and up is "highly improving"
HARD_ANAEROBIC_TE = 2.0        # Garmin: 2.0 and up, the session had real anaerobic work
INTENSITIES = ("easy", "steady", "hard")
# What a degree of warmth costs in easy pace is fitted from the runner's own easy runs
# (heat_cost), not assumed: a fixed "3 °C explains it" rule did not hold on real data.
HEAT_FIT_DAYS = 730            # chosen: two full years, so every season counts twice
HEAT_MIN_RUNS = 30             # chosen: fewer easy runs with a temperature give no usable fit
STREAK_RUNS = 3                # confirmed: runs that make a week count towards the streak
# chosen, after the owner said the build-up depends on the distance:
BUILD_WEEKS = ((15.0, 6), (30.0, 8), (float("inf"), 12))   # race km below -> build-up weeks compared
DEFAULT_BUILD_WEEKS = 8        # chosen: when the race distance is unknown
ROAD_RACE_SHARE = 0.05         # confirmed ("very close"): an earlier road race within 5 % of the distance
ROAD_RACE_CLIMB_M = 100.0      # confirmed: ... and within 100 m of climb, when the coming race's is known
TRAIL_RACE_SHARE = 0.25        # confirmed (10-25 %): trail, within 25 % of distance and of climb when known


def _between(df: pd.DataFrame, first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    return df[(df["date"] >= first) & (df["date"] <= last)]


def _last(df: pd.DataFrame, end: pd.Timestamp, days: int = 28) -> pd.DataFrame:
    return df[(df["date"] > end - pd.Timedelta(days=days)) & (df["date"] <= end)]


def _tone(value, previous, higher_is_better: bool) -> str:
    if value is None or previous is None or previous == 0:
        return "neutral"
    change = (value - previous) / abs(previous)
    if abs(change) < TONE_TOLERANCE:
        return "neutral"
    return "good" if (change > 0) == higher_is_better else "bad"


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
    runs = _between(runs, all_weeks[0], now).copy()
    runs["week_start"] = week_starts(runs["date"])
    out = runs.groupby("week_start").agg(
        run_km=("distance_km", "sum"), elevation_m=("elevation_m", "sum"),
        longest_km=("distance_km", "max"), n_runs=("activity_id", "count"),
    ).reindex(all_weeks, fill_value=0).rename_axis("week_start").reset_index()
    out = out.astype({"run_km": "float64", "elevation_m": "float64", "longest_km": "float64",
                      "n_runs": "int64"})

    easy = easy_runs(acts, cfg)
    easy = _between(easy, all_weeks[0], now).copy()
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


def _series(values) -> tuple[float, ...]:
    return tuple(float(v) for v in values if clean(v) is not None)


def vo2max_card(runs: pd.DataFrame, now: pd.Timestamp) -> Metric | None:
    """Garmin's VO2max estimate: the newest value against the newest one from 4 to 8 weeks ago.

    None when the activities carry no VO2max column at all (no Garmin input)."""
    if "vo2max" not in runs.columns:
        return None
    known = runs.dropna(subset=["vo2max"]).sort_values("date")
    recent = _last(known, now)
    earlier = _last(known, now - pd.Timedelta(days=28))       # 4 to 8 weeks ago, nothing older
    value = clean(recent["vo2max"].iloc[-1]) if len(recent) else None
    previous = clean(earlier["vo2max"].iloc[-1]) if len(earlier) else None
    tone = "neutral"
    if value is not None and previous is not None and abs(value - previous) >= VO2MAX_STEP:
        tone = "good" if value > previous else "bad"
    return Metric("vo2max", "VO2max", value, previous, "score",
                  _series(_last(known, now, days=7 * TREND_WEEKS)["vo2max"]), tone=tone,
                  note="no VO2max value in the last 4 weeks" if value is None
                  else "Garmin estimate, vs 4 weeks ago" if previous is not None
                  else "Garmin estimate; no value from 4 to 8 weeks ago to compare")


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


def _shares(runs: pd.DataFrame) -> dict[str, float] | None:
    kinds = intensity(runs)
    minutes = runs["duration_min"].where(kinds.notna()).groupby(kinds).sum()
    total = float(minutes.sum())
    if total <= 0:
        return None
    return {kind: 100 * float(minutes.get(kind, 0.0)) / total for kind in INTENSITIES}


def intensity_card(runs: pd.DataFrame, now: pd.Timestamp) -> Metric | None:
    """Share of running time spent in easy sessions, last 4 weeks against the 4 before.

    None when the activities carry no training effect at all (no Garmin input)."""
    if "aerobic_te" not in runs.columns:
        return None
    recent, before = _shares(_last(runs, now)), _shares(_last(runs, now - pd.Timedelta(days=28)))
    if recent is None:
        return Metric("easy_share", "Easy share", None, None, "share",
                      note="no runs with a training effect in the last 4 weeks")
    return Metric("easy_share", "Easy share", recent["easy"],
                  None if before is None else before["easy"], "share",
                  note="of running time, vs previous 4 weeks",
                  detail=f"{recent['steady']:.0f} % steady, {recent['hard']:.0f} % hard")


def intensity_weekly(weeks: int = TREND_WEEKS, *, activities: pd.DataFrame | None = None,
                     today=None, cfg: Config | None = None) -> pd.DataFrame:
    """Running minutes per week (Monday start) in easy, steady and hard sessions."""
    acts = activities if activities is not None else _load(cfg=cfg or load_config())
    now = today_ts(today)
    all_weeks = week_range(now, weeks)
    columns = [f"{kind}_min" for kind in INTENSITIES]
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    runs = _between(runs, all_weeks[0], now)
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


def _plan_window(runs: pd.DataFrame, plan: pd.DataFrame, end: pd.Timestamp):
    """(km done, km planned, days) over the part of the 28 days to `end` that the plan covers.

    Runs count only where the plan can be compared with them: from its first to its last
    day, and not on days whose running session has no distance (planned by time)."""
    first, last = max(end - pd.Timedelta(days=27), plan["date"].min()), min(end, plan["date"].max())
    days = int((last - first).days) + 1
    if days <= 0:
        return 0.0, 0.0, 0
    planned = _between(plan[~plan["type"].isin(NON_RUN_PLAN_TYPES)], first, last)
    by_time = planned.loc[planned["distance_km"].isna(), "date"]
    done = _between(runs, first, last)
    done = done[~done["date"].isin(by_time)]
    return float(done["distance_km"].sum()), float(planned["distance_km"].sum()), days


def adherence_card(runs: pd.DataFrame, plan: pd.DataFrame | None, now: pd.Timestamp) -> Metric | None:
    """Running km done as a share of the km planned, over the 4 weeks ending yesterday.

    Today is left out: its session is not due yet. Only the days the plan covers are
    compared; with under a week of them there is no value. None when there is no plan."""
    if plan is None or plan.empty:
        return None
    end = now - pd.Timedelta(days=1)
    done, due, days = _plan_window(runs, plan, end)
    done_before, due_before, days_before = _plan_window(runs, plan, end - pd.Timedelta(days=28))
    if days < MIN_PLAN_DAYS:
        return Metric("plan_done", "Plan done", None, None, "share",
                      note="the plan covers under a week of the last 4")
    if due <= 0:
        return Metric("plan_done", "Plan done", None, None, "share",
                      note="no planned distances in the last 4 weeks")
    previous = 100 * done_before / due_before if due_before > 0 and days_before >= MIN_PLAN_DAYS else None
    note = ("last 4 weeks to yesterday, vs the 4 before" if days == 28
            else f"the {days} days the plan covers, to yesterday")
    return Metric("plan_done", "Plan done", 100 * done / due, previous, "share",
                  note=note, detail=f"{done:.1f} of {due:.1f} km")


def garmin_load_card(acts: pd.DataFrame, now: pd.Timestamp, cfg: Config) -> Metric | None:
    """The load ratio again, on Garmin's training load (every activity, gym and walks too).

    None when the activities carry no Garmin load at all (no Garmin input). No value while
    the feed is behind: activities without a load would count as no load at all. Today's
    are expected to lack one, the feed runs once a day."""
    if "garmin_load" not in acts.columns:
        return None
    label = "Garmin load, 7 days vs 4 weeks"
    recent = _last(acts, now, days=7)
    newest = recent.loc[recent["garmin_load"].notna(), "date"].max()
    behind = recent if pd.isna(newest) else recent[recent["date"] > newest]
    if behind["date"].nunique() > FEED_LAG_DAYS:
        return Metric("garmin_load_ratio", label, None, None, "ratio",
                      note=f"the Garmin feed is behind: {len(behind)} recent activities "
                           "have no load yet")
    status = load_status(activities=acts, today=now, cfg=cfg, column="garmin_load")
    earlier = load_status(activities=acts, today=now - pd.Timedelta(days=7), cfg=cfg,
                          column="garmin_load")
    return Metric("garmin_load_ratio", label, clean(status["ratio"]),
                  clean(earlier["ratio"]), "ratio", tone=_LOAD_TONES[status["label"]],
                  note="all activities, vs a week ago" if status["ratio"] is not None
                  else "no Garmin load in the last 4 weeks", detail=status["label"])


def heat_cost(easy: pd.DataFrame, now: pd.Timestamp) -> float | None:
    """Minutes per km that one °C of warmth costs this runner at easy effort.

    A straight-line fit of pace on temperature over the easy runs of the last HEAT_FIT_DAYS.
    None without HEAT_MIN_RUNS runs at different temperatures. Never below zero: a fit that
    says heat makes the runner faster is noise."""
    if "temp_c" not in easy.columns:
        return None
    runs = _last(easy, now, HEAT_FIT_DAYS).dropna(subset=["temp_c", "pace_min_km"])
    if len(runs) < HEAT_MIN_RUNS or runs["temp_c"].nunique() < 2:
        return None
    slope = np.polyfit(runs["temp_c"].astype(float), runs["pace_min_km"].astype(float), 1)[0]
    return max(0.0, float(slope))


def easy_pace_card(easy: pd.DataFrame, series: tuple[float, ...], now: pd.Timestamp) -> Metric:
    """Median pace of easy runs, last 4 weeks against the 4 before.

    A change the weather accounts for is said in the note and not coloured: when the pace
    with the fitted cost of the temperature change taken out (heat_cost) is within the
    tolerance of the earlier pace."""
    recent, before = _last(easy, now), _last(easy, now - pd.Timedelta(days=28))
    pace = clean(recent["pace_min_km"].median()) if len(recent) else None
    pace_before = clean(before["pace_min_km"].median()) if len(before) else None
    if pace is None:
        return Metric("easy_pace", "Easy pace", None, pace_before, "pace", series,
                      note="no easy road runs in the last 4 weeks")
    tone, note = _tone(pace, pace_before, higher_is_better=False), "vs previous 4 weeks, easy road runs"
    cost = heat_cost(easy, now) if tone != "neutral" else None
    if cost:
        warmer = clean(recent["temp_c"].median() - before["temp_c"].median())
        if warmer is not None and (warmer > 0) == (tone == "bad") and _tone(
                pace - cost * warmer, pace_before, higher_is_better=False) == "neutral":
            note = (f"{'slower' if tone == 'bad' else 'faster'}, but {abs(warmer):.0f} °C "
                    f"{'warmer' if warmer > 0 else 'cooler'} than the previous 4 weeks")
            tone = "neutral"
    n = len(recent)
    return Metric("easy_pace", "Easy pace", pace, pace_before, "pace", series, tone=tone,
                  note=note, detail=f"{n} run" + ("" if n == 1 else "s"))


def streak_card(runs: pd.DataFrame, now: pd.Timestamp) -> Metric:
    """Weeks in a row with STREAK_RUNS or more runs. The current week counts once it
    qualifies and never breaks the streak before it is over."""
    monday = monday_of(now)
    per_week = week_starts(runs.loc[runs["date"] <= now, "date"]).value_counts()
    this_week = int(per_week.get(monday, 0))
    streak, week = (1 if this_week >= STREAK_RUNS else 0), monday - pd.Timedelta(days=7)
    while per_week.get(week, 0) >= STREAK_RUNS:
        streak, week = streak + 1, week - pd.Timedelta(days=7)
    recent = [float(per_week.get(monday - pd.Timedelta(weeks=i), 0))
              for i in range(TREND_WEEKS - 1, -1, -1)]
    return Metric("run_streak", "Weeks in a row", float(streak), None, "weeks", tuple(recent),
                  note=f"weeks in a row with {STREAK_RUNS} or more runs",
                  detail=f"{this_week} this week")


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
    window = _last(runs, end, days=7 * weeks)
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


def _volume(runs: pd.DataFrame, weekly: pd.DataFrame, now: pd.Timestamp) -> list[Metric]:
    monday = monday_of(now)
    week = float(_between(runs, monday, now)["distance_km"].sum())
    week_before = float(_between(runs, monday - pd.Timedelta(days=7),
                                 now - pd.Timedelta(days=7))["distance_km"].sum())
    recent, before = _last(runs, now), _last(runs, now - pd.Timedelta(days=28))
    year_start = pd.Timestamp(year=now.year, month=1, day=1)
    ytd = float(_between(runs, year_start, now)["distance_km"].sum())
    ytd_before = float(_between(runs, year_start - pd.DateOffset(years=1),
                                now - pd.DateOffset(years=1))["distance_km"].sum())
    km_series = _series(weekly["run_km"])
    return [
        Metric("km_week", "This week", week, week_before, "km", km_series,
               note="vs same days last week"),
        Metric("km_4w", "Last 4 weeks", float(recent["distance_km"].sum()),
               float(before["distance_km"].sum()), "km", km_series, note="vs previous 4 weeks"),
        Metric("km_ytd", "Year to date", ytd, ytd_before, "km", note="vs same period last year"),
        Metric("elevation_4w", "Climb, 4 weeks", float(recent["elevation_m"].sum()),
               float(before["elevation_m"].sum()), "m", _series(weekly["elevation_m"]),
               note="vs previous 4 weeks"),
    ]


def _fitness(acts: pd.DataFrame, runs: pd.DataFrame, weekly: pd.DataFrame, now: pd.Timestamp,
             cfg: Config) -> list[Metric]:
    status = load_status(activities=acts, today=now, cfg=cfg)
    earlier = load_status(activities=acts, today=now - pd.Timedelta(days=7), cfg=cfg)
    load = Metric("load_ratio", "Load, 7 days vs 4 weeks", clean(status["ratio"]),
                  clean(earlier["ratio"]), "ratio", tone=_LOAD_TONES[status["label"]],
                  note="vs a week ago" if status["ratio"] is not None
                  else "no relative effort in the last 4 weeks",
                  detail=status["label"])

    easy_card = easy_pace_card(easy_runs(acts, cfg), _series(weekly["easy_pace_min_km"]), now)
    garmin = garmin_load_card(acts, now, cfg)
    extra = [card for card in (garmin, intensity_card(runs, now), vo2max_card(runs, now)) if card]
    return [load, *extra, easy_card]


def _pace_cards(runs: pd.DataFrame, weekly: pd.DataFrame, now: pd.Timestamp) -> list[Metric]:
    recent, before = _last(runs, now), _last(runs, now - pd.Timedelta(days=28))
    longest = Metric("longest_run", "Longest run, 4 weeks",
                     clean(recent["distance_km"].max()) if len(recent) else None,
                     clean(before["distance_km"].max()) if len(before) else None, "km",
                     _series(weekly["longest_km"]),
                     note="vs previous 4 weeks" if len(recent) else "no runs in the last 4 weeks")
    frequency = Metric("runs_per_week", "Runs per week", len(recent) / 4, len(before) / 4, "count",
                       _series(weekly["n_runs"]), note="4-week mean vs previous 4 weeks")
    return [longest, frequency]


def _recovery_detail(column: str, row: pd.Series) -> str | None:
    """Garmin's own reading beside the number: sleep score and stages, HRV status."""
    if column == "hrv_ms":
        status = row.get("hrv_status")
        return status.strip().lower().replace("_", " ") if isinstance(status, str) and status.strip() else None
    if column != "sleep_hours":
        return None
    parts = []
    score = clean(row.get("sleep_score"))
    if score is not None:
        parts.append(f"score {score:.0f}")
    for label, source in (("deep", "deep_sleep_seconds"), ("REM", "rem_sleep_seconds")):
        seconds = clean(row.get(source))
        if seconds is not None:
            parts.append(f"{label} {seconds / 3600:.1f} h")
    return ", ".join(parts) or None


def _recovery(cfg: Config, now: pd.Timestamp, clock: float | None) -> list[Metric]:
    wellness, state = read_wellness(cfg, clock)
    if state.status == "off":
        return []
    present = [c for c in _RECOVERY if wellness is not None and c in wellness.columns]
    reason = None
    if state.status in ("error", "stale"):
        reason = state.message
    elif wellness["date"].iloc[-1] < now - pd.Timedelta(days=1):
        reason = f"newest value is from {wellness['date'].iloc[-1]:%a %d %b}"
    if reason is not None:
        return [Metric(c, _RECOVERY[c][0], None, None, _RECOVERY[c][1], note=reason)
                for c in (present or list(_RECOVERY))]
    newest = wellness["date"].iloc[-1]
    usable = wellness[wellness["date"] >= now - pd.Timedelta(days=1)]   # today or yesterday
    baseline = _last(wellness, now)
    out = []
    for column in present:
        label, unit, higher = _RECOVERY[column]
        filled = usable.dropna(subset=[column])
        mean = clean(baseline[column].mean())
        if filled.empty:
            known = wellness.dropna(subset=[column])
            value = None
            note = (f"no value since {known['date'].iloc[-1]:%a %d %b}" if len(known)
                    else "no values in the file")
            detail = None
        else:
            value, when = clean(filled[column].iloc[-1]), filled["date"].iloc[-1]
            note = "vs 4-week average" if when == newest else f"{when:%a %d %b}, vs 4-week average"
            detail = _recovery_detail(column, filled.iloc[-1])
        out.append(Metric(column, label, value, mean, unit,
                          _series(wellness[column].tail(RECOVERY_DAYS)),
                          tone=_tone(value, mean, higher), note=note, detail=detail))
    return out


def headline(*, activities: pd.DataFrame | None = None, today=None, cfg: Config | None = None,
             now: float | None = None) -> dict[str, list[Metric]]:
    """Every dashboard card, grouped by row: volume, consistency, fitness, recovery.

    `today` is the date the numbers are for; `now` is the clock used to judge whether the
    wellness file is stale (both only differ from the real ones in tests)."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    day = today_ts(today)
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    weekly = weekly_runs(TREND_WEEKS, activities=acts, today=day, cfg=cfg)
    adherence = adherence_card(runs, read_plan(cfg, today=day)[0], day)
    return {
        "volume": [*_volume(runs, weekly, day), *_pace_cards(runs, weekly, day)],
        "consistency": [*([adherence] if adherence is not None else []), streak_card(runs, day)],
        "fitness": _fitness(acts, runs, weekly, day, cfg),
        "recovery": _recovery(cfg, day, now),
    }
