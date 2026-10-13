"""The dashboard's headline numbers. No Streamlit here: usable from a notebook."""

from __future__ import annotations

from datetime import date

import pandas as pd

from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.load import load_status
from myrun.metric import Metric, clean
from myrun.optional import NON_RUN_PLAN_TYPES, read_plan, read_wellness
from myrun.trends import easy_runs

TREND_WEEKS = 12
RECOVERY_DAYS = 14
TONE_TOLERANCE = 0.05          # a change under 5 % is not coloured
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
VO2MAX_STEP = 1.0              # Garmin reports whole numbers: one point is a real change
STEADY_AEROBIC_TE = 3.0        # Garmin training effect 3.0-3.9 "improving"
HARD_AEROBIC_TE = 4.0          # 4.0 and up "highly improving"
HARD_ANAEROBIC_TE = 2.0        # 2.0 and up: the session had real anaerobic work
INTENSITIES = ("easy", "steady", "hard")
HEAT_SHIFT_C = 3.0             # a 4-week median this much warmer or cooler explains a pace change
STREAK_RUNS = 3                # runs that make a week count towards the streak
BUILD_WEEKS = ((15.0, 6), (30.0, 8), (float("inf"), 12))   # race km below -> build-up weeks compared
DEFAULT_BUILD_WEEKS = 8        # when the race distance is unknown
ROAD_RACE_SHARE = 0.05         # road: an earlier road race within 5 % of the distance is "similar"
ROAD_RACE_CLIMB_M = 100.0      # ... and within this much climb, when the coming race's climb is known
TRAIL_RACE_SHARE = 0.25        # trail: within 25 % of the distance, and of the climb when known


def _now(today) -> pd.Timestamp:
    return pd.Timestamp(today if today is not None else date.today()).normalize()


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
    """Running per week (Monday start), oldest first, the current week last."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    now = _now(today)
    monday = now - pd.Timedelta(days=now.weekday())
    all_weeks = pd.date_range(monday - pd.Timedelta(weeks=weeks - 1), periods=weeks, freq="7D")
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    runs = _between(runs, all_weeks[0], now).copy()
    runs["week_start"] = runs["date"] - pd.to_timedelta(runs["date"].dt.weekday, unit="D")
    out = runs.groupby("week_start").agg(
        run_km=("distance_km", "sum"), elevation_m=("elevation_m", "sum"),
        longest_km=("distance_km", "max"), n_runs=("activity_id", "count"),
    ).reindex(all_weeks, fill_value=0).rename_axis("week_start").reset_index()
    out = out.astype({"run_km": "float64", "elevation_m": "float64", "longest_km": "float64",
                      "n_runs": "int64"})

    easy = easy_runs(acts, cfg)
    easy = _between(easy, all_weeks[0], now).copy()
    easy["week_start"] = easy["date"] - pd.to_timedelta(easy["date"].dt.weekday, unit="D")
    out["easy_pace_min_km"] = out["week_start"].map(
        easy.groupby("week_start")["pace_min_km"].median()).astype("float64")

    plan, _ = read_plan(cfg, today=now)
    out["planned_km"] = float("nan")
    if plan is not None:
        runs_planned = plan[~plan["type"].isin(NON_RUN_PLAN_TYPES)].copy()
        runs_planned["week_start"] = (runs_planned["date"]
                                      - pd.to_timedelta(runs_planned["date"].dt.weekday, unit="D"))
        per_week = runs_planned.groupby("week_start")["distance_km"].sum(min_count=1)
        out["planned_km"] = out["week_start"].map(per_week).astype("float64")
    return out


def _series(values) -> tuple[float, ...]:
    return tuple(float(v) for v in values if clean(v) is not None)


def vo2max_card(runs: pd.DataFrame, now: pd.Timestamp) -> Metric | None:
    """Garmin's VO2max estimate: the newest value against the newest one from 4 weeks ago.

    None when the activities carry no VO2max column at all (no Garmin input)."""
    if "vo2max" not in runs.columns:
        return None
    known = runs.dropna(subset=["vo2max"]).sort_values("date")
    recent = _last(known, now)
    earlier = known[known["date"] <= now - pd.Timedelta(days=28)]
    value = clean(recent["vo2max"].iloc[-1]) if len(recent) else None
    previous = clean(earlier["vo2max"].iloc[-1]) if len(earlier) else None
    tone = "neutral"
    if value is not None and previous is not None and abs(value - previous) >= VO2MAX_STEP:
        tone = "good" if value > previous else "bad"
    return Metric("vo2max", "VO2max", value, previous, "score",
                  _series(_last(known, now, days=7 * TREND_WEEKS)["vo2max"]), tone=tone,
                  note="Garmin estimate, vs 4 weeks ago" if value is not None
                  else "no VO2max value in the last 4 weeks")


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
    now = _now(today)
    monday = now - pd.Timedelta(days=now.weekday())
    all_weeks = pd.date_range(monday - pd.Timedelta(weeks=weeks - 1), periods=weeks, freq="7D")
    columns = [f"{kind}_min" for kind in INTENSITIES]
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    runs = _between(runs, all_weeks[0], now)
    if "aerobic_te" not in runs.columns or runs.empty:
        out = pd.DataFrame(0.0, index=all_weeks, columns=columns)
    else:
        week = runs["date"] - pd.to_timedelta(runs["date"].dt.weekday, unit="D")
        out = (runs.assign(week_start=week, kind=intensity(runs)).dropna(subset=["kind"])
               .pivot_table(index="week_start", columns="kind", values="duration_min",
                            aggfunc="sum", fill_value=0.0)
               .reindex(index=all_weeks, columns=list(INTENSITIES), fill_value=0.0))
        out.columns = columns
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


def adherence_card(runs: pd.DataFrame, plan: pd.DataFrame | None, now: pd.Timestamp) -> Metric | None:
    """Running km done as a share of the km planned, over the 4 weeks ending yesterday.

    Today is left out: its session is not due yet. None when there is no plan."""
    if plan is None:
        return None
    planned = plan[~plan["type"].isin(NON_RUN_PLAN_TYPES)]
    end = now - pd.Timedelta(days=1)

    def window(last: pd.Timestamp) -> tuple[float, float]:
        return (float(_last(runs, last)["distance_km"].sum()),
                float(_last(planned, last)["distance_km"].sum()))

    done, due = window(end)
    done_before, due_before = window(end - pd.Timedelta(days=28))
    if due <= 0:
        return Metric("plan_done", "Plan done", None, None, "share",
                      note="no planned distances in the last 4 weeks")
    return Metric("plan_done", "Plan done", 100 * done / due,
                  100 * done_before / due_before if due_before > 0 else None, "share",
                  note="last 4 weeks to yesterday, vs the 4 before",
                  detail=f"{done:.1f} of {due:.1f} km")


def garmin_load_card(acts: pd.DataFrame, now: pd.Timestamp, cfg: Config) -> Metric | None:
    """The load ratio again, on Garmin's training load (every activity, gym and walks too).

    None when the activities carry no Garmin load at all (no Garmin input)."""
    if "garmin_load" not in acts.columns:
        return None
    status = load_status(activities=acts, today=now, cfg=cfg, column="garmin_load")
    earlier = load_status(activities=acts, today=now - pd.Timedelta(days=7), cfg=cfg,
                          column="garmin_load")
    return Metric("garmin_load_ratio", "Garmin load, 7 days vs 4 weeks", clean(status["ratio"]),
                  clean(earlier["ratio"]), "ratio", tone=_LOAD_TONES[status["label"]],
                  note="all activities, vs a week ago" if status["ratio"] is not None
                  else "no Garmin load in the last 4 weeks", detail=status["label"])


def easy_pace_card(easy: pd.DataFrame, series: tuple[float, ...], now: pd.Timestamp) -> Metric:
    """Median pace of easy runs, last 4 weeks against the 4 before.

    A change that goes with the weather (slower and clearly warmer, or faster and clearly
    cooler) is said in the note and not coloured: heat costs pace at the same effort."""
    recent, before = _last(easy, now), _last(easy, now - pd.Timedelta(days=28))
    pace = clean(recent["pace_min_km"].median()) if len(recent) else None
    pace_before = clean(before["pace_min_km"].median()) if len(before) else None
    if pace is None:
        return Metric("easy_pace", "Easy pace", None, pace_before, "pace", series,
                      note="no easy road runs in the last 4 weeks")
    tone, note = _tone(pace, pace_before, higher_is_better=False), "vs previous 4 weeks, easy road runs"
    if "temp_c" in easy.columns and tone != "neutral":
        warmer = clean(recent["temp_c"].median() - before["temp_c"].median())
        if warmer is not None and abs(warmer) >= HEAT_SHIFT_C and (warmer > 0) == (tone == "bad"):
            note = (f"{'slower' if tone == 'bad' else 'faster'}, but {abs(warmer):.0f} °C "
                    f"{'warmer' if warmer > 0 else 'cooler'} than the previous 4 weeks")
            tone = "neutral"
    n = len(recent)
    return Metric("easy_pace", "Easy pace", pace, pace_before, "pace", series, tone=tone,
                  note=note, detail=f"{n} run" + ("" if n == 1 else "s"))


def _week_start(dates: pd.Series) -> pd.Series:
    return dates - pd.to_timedelta(dates.dt.weekday, unit="D")


def streak_card(runs: pd.DataFrame, now: pd.Timestamp) -> Metric:
    """Weeks in a row with STREAK_RUNS or more runs. The current week counts once it
    qualifies and never breaks the streak before it is over."""
    monday = now - pd.Timedelta(days=now.weekday())
    per_week = _week_start(runs.loc[runs["date"] <= now, "date"]).value_counts()
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
    """Minutes of activity (every sport) per day over whole weeks, Monday first.

    Days after today are NaN: they have not happened, which is not the same as a rest day."""
    acts = activities if activities is not None else _load(cfg=cfg or load_config())
    now = _now(today)
    monday = now - pd.Timedelta(days=now.weekday())
    dates = pd.date_range(monday - pd.Timedelta(weeks=weeks - 1), periods=7 * weeks, freq="D")
    minutes = acts.groupby("date")["duration_min"].sum().reindex(dates, fill_value=0.0)
    minutes[minutes.index > now] = float("nan")
    return pd.DataFrame({"date": dates, "minutes": minutes.to_numpy(dtype="float64")})


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
    out = {"race": str(race["session"]), "date": race["date"], "days_to_go": days_to_go,
           "weeks": weeks, **_build_up(runs, now, weeks), "previous": None}
    if distance is None or "session_type" not in runs.columns:
        return out
    surface = race.get("surface")
    trail = surface == "trail" or (surface != "road" and "trail" in str(race["session"]).lower())
    share = TRAIL_RACE_SHARE if trail else ROAD_RACE_SHARE
    similar = runs[(runs["session_type"] == "race") & (runs["date"] < now)
                   & ((runs["distance_km"] - distance).abs() <= share * distance)]
    if "surface" in runs.columns:
        similar = similar[(similar["surface"] != "road") if trail else (similar["surface"] == "road")]
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
                       **_build_up(runs, last["date"] - pd.Timedelta(days=days_to_go), weeks)}
    return out


def _volume(runs: pd.DataFrame, weekly: pd.DataFrame, now: pd.Timestamp) -> list[Metric]:
    monday = now - pd.Timedelta(days=now.weekday())
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
    day = _now(today)
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    weekly = weekly_runs(TREND_WEEKS, activities=acts, today=day, cfg=cfg)
    adherence = adherence_card(runs, read_plan(cfg, today=day)[0], day)
    return {
        "volume": [*_volume(runs, weekly, day), *_pace_cards(runs, weekly, day)],
        "consistency": [*([adherence] if adherence is not None else []), streak_card(runs, day)],
        "fitness": _fitness(acts, runs, weekly, day, cfg),
        "recovery": _recovery(cfg, day, now),
    }
