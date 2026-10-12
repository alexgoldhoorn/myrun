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
}


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

    easy = easy_runs(acts, cfg)
    easy_now, easy_before = _last(easy, now), _last(easy, now - pd.Timedelta(days=28))
    pace = clean(easy_now["pace_min_km"].median()) if len(easy_now) else None
    pace_before = clean(easy_before["pace_min_km"].median()) if len(easy_before) else None
    n = len(easy_now)
    easy_card = Metric(
        "easy_pace", "Easy pace", pace, pace_before, "pace", _series(weekly["easy_pace_min_km"]),
        tone=_tone(pace, pace_before, higher_is_better=False),
        note="vs previous 4 weeks, easy road runs" if pace is not None
        else "no easy road runs in the last 4 weeks",
        detail=None if pace is None else f"{n} run" + ("" if n == 1 else "s"))

    recent, before = _last(runs, now), _last(runs, now - pd.Timedelta(days=28))
    longest = Metric("longest_run", "Longest run, 4 weeks",
                     clean(recent["distance_km"].max()) if len(recent) else None,
                     clean(before["distance_km"].max()) if len(before) else None, "km",
                     _series(weekly["longest_km"]),
                     note="vs previous 4 weeks" if len(recent) else "no runs in the last 4 weeks")
    frequency = Metric("runs_per_week", "Runs per week", len(recent) / 4, len(before) / 4, "count",
                       _series(weekly["n_runs"]), note="4-week mean vs previous 4 weeks")
    return [load, easy_card, longest, frequency]


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
    latest = wellness.iloc[-1]
    baseline = _last(wellness, now)
    out = []
    for column in present:
        label, unit, higher = _RECOVERY[column]
        value, mean = clean(latest[column]), clean(baseline[column].mean())
        out.append(Metric(column, label, value, mean, unit,
                          _series(wellness[column].tail(RECOVERY_DAYS)),
                          tone=_tone(value, mean, higher),
                          note="vs 4-week average" if value is not None
                          else f"no value for {latest['date']:%a %d %b}"))
    return out


def headline(*, activities: pd.DataFrame | None = None, today=None, cfg: Config | None = None,
             now: float | None = None) -> dict[str, list[Metric]]:
    """Every dashboard card, grouped by row: volume, fitness, recovery.

    `today` is the date the numbers are for; `now` is the clock used to judge whether the
    wellness file is stale (both only differ from the real ones in tests)."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    day = _now(today)
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    weekly = weekly_runs(TREND_WEEKS, activities=acts, today=day, cfg=cfg)
    return {
        "volume": _volume(runs, weekly, day),
        "fitness": _fitness(acts, runs, weekly, day, cfg),
        "recovery": _recovery(cfg, day, now),
    }
