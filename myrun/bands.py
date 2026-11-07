"""Heart rate by pace band and surface, year on year: a like-for-like fitness comparison.

A lower average heart rate over a year can mean fitter, or just an easier mix of runs or
more slow trail running. Grouping runs by surface and by grade-adjusted pace band before
averaging heart rate separates the two: within one cell the effort is comparable.

Each run is reduced to its core: the first and last km split and the first and last lap
are dropped (warm-up and cool-down), pace is Strava's grade-adjusted pace over the core
splits, heart rate the time-weighted lap average over the core laps. Races, interval
sessions and unsteady road runs are left out, with a reason per run.
"""

from __future__ import annotations

import re
from contextlib import closing
from datetime import date

import numpy as np
import pandas as pd

from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.hr import hr_settings
from myrun.metrics import INTENSITIES, intensity
from myrun.stravadb import open_db
from myrun.trends import MIN_EFFICIENCY_MINUTES, aerobic_efficiency

# Thresholds, labelled as in metrics.py: "chosen" (a judgement call), "fitted" (from the data).
PACE_EDGES = (4.5, 5.0, 5.5, 6.0, 7.0)        # chosen: min/km band edges (asked for by the owner)
PACE_BANDS = ("<4:30", "4:30–5:00", "5:00–5:30", "5:30–6:00", "6:00–7:00", ">7:00")
NOISY_RUNS = 3                 # chosen: a cell with fewer runs is flagged as noisy
MIN_CORE_SPLITS = 4            # chosen: from this many km splits, the first and last are dropped
MIN_CORE_LAPS = 3              # chosen: from this many laps, the first and last are dropped
MIN_LAP_M = 100                # chosen: shorter laps are button presses, not running
AUTO_LAP_M = (990, 1010)       # chosen: laps of 1 km (+-10 m) are the watch's auto-laps: no workout structure
MIN_PAIRED_RUNS = 8            # chosen: runs needed on each watch, in shared cells, to fit an HR offset
MAX_LAP_CV = 0.15              # chosen, from the lap data: core lap speeds of workout-lap runs varying more
                               # than this are intervals or fartlek (25 % of labelled interval sessions
                               # are under 0.144, half of long runs under 0.131)
TRAIL_FALLBACK_M_PER_KM = 30.0  # chosen default; fitted from the data by trail_threshold() when it can
MIN_TRAIL_FIT_RUNS = 20        # chosen: TrailRun-tagged runs needed to fit the trail threshold
SURFACES = ("road", "trail")

_LAPS_SQL = """
SELECT l.activityId AS activity_id, l.lapNumber AS lap, l.distance AS distance_m,
       l.movingTimeInSeconds AS duration_s, l.averageHeartRate AS hr
FROM ActivityLap l JOIN Activity a ON a.activityId = l.activityId
WHERE COALESCE(a.markedForDeletion, 0) != 1 AND a.sportType IN ({sports})
ORDER BY l.activityId, l.lapNumber
"""
_SPLITS_SQL = """
SELECT s.activityId AS activity_id, s.splitNumber AS split, s.distance AS distance_m,
       s.movingTimeInSeconds AS duration_s, s.gapPaceInSecondsPerKm AS gap_s_km
FROM ActivitySplit s JOIN Activity a ON a.activityId = s.activityId
WHERE s.unitSystem = 'metric' AND COALESCE(a.markedForDeletion, 0) != 1
  AND a.sportType IN ({sports})
ORDER BY s.activityId, s.splitNumber
"""


def pace_band(pace_min_km: pd.Series) -> pd.Series:
    """Band label per pace; a pace on an edge goes to the slower band (4:30 is 4:30–5:00)."""
    index = np.searchsorted(np.asarray(PACE_EDGES), pace_min_km.to_numpy(dtype=float), side="right")
    out = pd.Series([PACE_BANDS[i] for i in index], index=pace_min_km.index, dtype="object")
    out[pace_min_km.isna()] = None
    return out


def parse_season(text: str | None) -> tuple[int, ...] | None:
    """'9-10' or '9,10' or '11-2' (wrapping the new year) to month numbers; '' to None."""
    if not text:
        return None
    text = text.strip()
    if m := re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", text):
        first, last = int(m[1]), int(m[2])
        if not (1 <= first <= 12 and 1 <= last <= 12):
            raise ValueError(f"months must be 1-12: {text!r}")
        if first <= last:
            return tuple(range(first, last + 1))
        return tuple(range(first, 13)) + tuple(range(1, last + 1))
    parts = [p for p in re.split(r"[,\s]+", text) if p]
    if not parts or not all(p.isdigit() and 1 <= int(p) <= 12 for p in parts):
        raise ValueError(f"season must be like '9-10' or '9,10': {text!r}")
    return tuple(sorted({int(p) for p in parts}))


def trail_threshold(runs: pd.DataFrame) -> tuple[float, str]:
    """Climb per km above which an untagged Run counts as trail, and where it comes from.

    Fitted on the runs from years in which the owner tagged trail runs as TrailRun: the
    threshold that misclassifies the smallest share of Run and TrailRun together."""
    tagged_years = runs.loc[runs["sport"] == "TrailRun", "year"].unique()
    pool = runs[runs["year"].isin(tagged_years)].dropna(subset=["hilliness_m_km"])
    trail = pool.loc[pool["sport"] == "TrailRun", "hilliness_m_km"].to_numpy()
    road = pool.loc[pool["sport"] == "Run", "hilliness_m_km"].to_numpy()
    if len(trail) < MIN_TRAIL_FIT_RUNS or len(road) < MIN_TRAIL_FIT_RUNS:
        return TRAIL_FALLBACK_M_PER_KM, "chosen default (too few tagged trail runs to fit)"
    candidates = np.arange(10.0, 61.0)
    errors = [(road >= t).mean() + (trail < t).mean() for t in candidates]
    best = float(candidates[int(np.argmin(errors))])
    return best, f"fitted on {len(trail)} TrailRun and {len(road)} Run activities"


def surfaces(runs: pd.DataFrame, threshold: float) -> pd.Series:
    """road or trail. The sport type decides; in years without any TrailRun, climb per km."""
    out = pd.Series("road", index=runs.index, dtype="object")
    out[runs["sport"] == "TrailRun"] = "trail"
    if "surface" in runs.columns:
        out[runs["surface"].isin(["trail", "mixed"])] = "trail"   # a race log entry, or mixed
    untagged_years = set(runs["year"]) - set(runs.loc[runs["sport"] == "TrailRun", "year"])
    fallback = runs["year"].isin(untagged_years) & (runs["hilliness_m_km"] >= threshold)
    out[fallback] = "trail"
    return out


def _read(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    marks = ",".join("?" for _ in RUN_SPORTS)
    with closing(open_db(cfg)) as conn:
        laps = pd.read_sql_query(_LAPS_SQL.format(sports=marks), conn, params=list(RUN_SPORTS))
        splits = pd.read_sql_query(_SPLITS_SQL.format(sports=marks), conn, params=list(RUN_SPORTS))
    for frame in (laps, splits):
        for column in frame.columns.drop("activity_id"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
        frame["activity_id"] = frame["activity_id"].astype(str)
    return laps, splits


def _core(frame: pd.DataFrame, key: str, minimum: int) -> pd.DataFrame:
    """Drop each activity's first and last row when it has at least `minimum` rows."""
    frame = frame.sort_values(["activity_id", key])
    position = frame.groupby("activity_id").cumcount()
    count = frame.groupby("activity_id")[key].transform("size")
    keep = (count < minimum) | ((position > 0) & (position < count - 1))
    return frame[keep]


def core_stats(laps: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Per activity: core HR, core lap speed spread, and core pace (grade-adjusted and raw)."""
    laps = laps[(laps["distance_m"] >= MIN_LAP_M) & (laps["duration_s"] > 0)]
    core_laps = _core(laps, "lap", MIN_CORE_LAPS).copy()
    core_laps["speed"] = core_laps["distance_m"] / core_laps["duration_s"]
    with_hr = core_laps.dropna(subset=["hr"])
    hr = ((with_hr["hr"] * with_hr["duration_s"]).groupby(with_hr["activity_id"]).sum()
          / with_hr.groupby("activity_id")["duration_s"].sum())

    def _cv(group: pd.DataFrame) -> float:
        if len(group) < 3:
            return float("nan")
        weights = group["duration_s"]
        mean = np.average(group["speed"], weights=weights)
        return float(np.sqrt(np.average((group["speed"] - mean) ** 2, weights=weights)) / mean)

    cv = core_laps.groupby("activity_id")[["speed", "duration_s"]].apply(_cv)
    lap_pace = (core_laps.groupby("activity_id")["duration_s"].sum() / 60
                / (core_laps.groupby("activity_id")["distance_m"].sum() / 1000))
    low, high = AUTO_LAP_M
    all_but_last = laps.sort_values(["activity_id", "lap"]).groupby("activity_id")["distance_m"]
    workout_laps = all_but_last.apply(lambda d: bool(len(d) > 1 and not d.iloc[:-1].between(low, high).all()))

    splits = splits[(splits["distance_m"] > 0) & (splits["duration_s"] > 0)]
    core_splits = _core(splits, "split", MIN_CORE_SPLITS)
    grouped = core_splits.groupby("activity_id")
    distance = grouped["distance_m"].sum()
    raw = grouped["duration_s"].sum() / 60 / (distance / 1000)
    has_gap = grouped["gap_s_km"].apply(lambda g: bool((g > 0).all()))
    gap = ((core_splits["gap_s_km"] * core_splits["distance_m"]).groupby(core_splits["activity_id"]).sum()
           / distance / 60).where(has_gap)

    out = pd.DataFrame({"core_hr": hr, "lap_cv": cv, "workout_laps": workout_laps,
                        "lap_pace_min_km": lap_pace, "gap_pace_min_km": gap,
                        "raw_pace_min_km": raw, "core_km": distance / 1000})
    return out.rename_axis("activity_id").reset_index()


def band_runs(*, activities: pd.DataFrame | None = None, cfg: Config | None = None,
              today=None) -> pd.DataFrame:
    """One row per run with its surface, core pace and HR, band, and `excluded` (None = kept)."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    runs = acts[acts["sport"].isin(RUN_SPORTS)].copy()
    columns = ["activity_id", "date", "year", "month", "sport", "surface_band", "distance_km",
               "temp_c", "core_hr", "hr_pct_max", "pace_min_km", "pace_source", "band",
               "speed_per_beat", "lap_cv", "workout_laps", "device", "hr_sensor", "core_hr_raw",
               "hr_offset", "excluded"]
    if runs.empty:
        return pd.DataFrame(columns=columns)
    runs["activity_id"] = runs["activity_id"].astype(str)
    threshold, _ = trail_threshold(runs)
    runs["surface_band"] = surfaces(runs, threshold)
    runs["month"] = runs["date"].dt.to_period("M").dt.start_time

    laps, splits = _read(cfg)
    runs = runs.merge(core_stats(laps, splits), on="activity_id", how="left")
    device = runs["device"] if "device" in runs else pd.Series(None, index=runs.index, dtype=object)
    runs["device"] = device.str.replace(r"^Garmin ", "", regex=True)
    runs["hr_sensor"] = hr_sensor(runs["date"], cfg.hr_sensors)
    flat_road = (runs["surface_band"] == "road") & (
        runs["hilliness_m_km"] < cfg.efficiency_max_hilliness_m_per_km)
    runs["pace_min_km"] = runs["gap_pace_min_km"]
    runs["pace_source"] = np.where(runs["gap_pace_min_km"].notna(), "grade-adjusted", None)
    use_raw = runs["pace_min_km"].isna() & flat_road & runs["raw_pace_min_km"].notna()
    runs.loc[use_raw, "pace_min_km"] = runs.loc[use_raw, "raw_pace_min_km"]
    runs.loc[use_raw, "pace_source"] = "flat, raw"
    runs["workout_laps"] = runs["workout_laps"].astype("boolean").fillna(False).astype(bool)
    lap_paced = runs["workout_laps"] & flat_road & runs["lap_pace_min_km"].notna()
    runs.loc[lap_paced, "pace_min_km"] = runs.loc[lap_paced, "lap_pace_min_km"]
    runs.loc[lap_paced, "pace_source"] = "flat, core laps"
    # no laps with heart rate: the whole-run average, as a run without laps is one piece
    runs["core_hr"] = runs["core_hr"].fillna(runs["avg_hr"])

    session = runs["session_type"] if "session_type" in runs else pd.Series(None, index=runs.index)
    is_race = (session == "race") | (runs["workout_type"] == "race")
    if "race_name" in runs:
        is_race |= runs["race_name"].notna()
    reasons = [
        (is_race, "race"),
        (session == "intervals", "intervals"),
        (runs["duration_min"] < MIN_EFFICIENCY_MINUTES, "short"),
        (runs["core_hr"].isna() | (runs["core_hr"] <= 0), "no heart rate"),
        (runs["pace_min_km"].isna(), "no grade-adjusted pace (hilly or trail)"),
        (runs["workout_laps"] & (runs["lap_cv"] > MAX_LAP_CV), "unsteady (workout laps)"),
    ]
    runs["excluded"] = None
    for mask, reason in reversed(reasons):          # the first matching reason wins
        runs.loc[mask.fillna(False).astype(bool), "excluded"] = reason

    runs["band"] = pace_band(runs["pace_min_km"])
    runs["core_hr_raw"] = runs["core_hr"]
    offsets = watch_offsets(runs)
    runs["hr_offset"] = runs["device"].map(offsets.set_index("device")["applied_bpm"]).fillna(0.0)
    runs["core_hr"] = runs["core_hr_raw"] + runs["hr_offset"]
    max_hr = hr_settings(cfg, acts, today).max_hr
    runs["hr_pct_max"] = 100 * runs["core_hr"] / max_hr if max_hr else float("nan")
    runs["speed_per_beat"] = 1000 / runs["pace_min_km"] / runs["core_hr"]
    return runs[columns].reset_index(drop=True)


def watch_offsets(runs: pd.DataFrame) -> pd.DataFrame:
    """Wrist-HR offset of each watch against the one before it, fitted from runs in the same
    quarter, surface and pace band on both watches: the mean HR difference per shared cell,
    weighted by the smaller run count. Offsets chain back to the oldest watch of an unbroken
    chain, so `applied_bpm` puts every run on that watch's scale. A switch with fewer than
    MIN_PAIRED_RUNS on either side is not corrected (and breaks the chain)."""
    columns = ["device", "reference", "offset_bpm", "applied_bpm", "n_runs", "n_reference",
               "n_cells"]
    kept = runs[runs["excluded"].isna() & runs["device"].notna()].copy()
    if kept.empty:
        return pd.DataFrame(columns=columns)
    kept["quarter"] = kept["date"].dt.to_period("Q")
    order = kept.groupby("device")["date"].median().sort_values().index
    rows, applied = [], 0.0
    for previous, device in zip(order[:-1], order[1:]):
        cells = kept[kept["device"].isin([previous, device])].groupby(
            ["quarter", "surface_band", "band"])
        diffs, weights, n_dev, n_ref = [], [], 0, 0
        for _, cell in cells:
            ref = cell.loc[cell["device"] == previous, "core_hr_raw"]
            new = cell.loc[cell["device"] == device, "core_hr_raw"]
            if len(ref) and len(new):
                diffs.append(ref.mean() - new.mean())
                weights.append(min(len(ref), len(new)))
                n_ref, n_dev = n_ref + len(ref), n_dev + len(new)
        if min(n_ref, n_dev) < MIN_PAIRED_RUNS:
            applied = 0.0
            continue
        offset = float(np.average(diffs, weights=weights))
        applied += offset
        rows.append({"device": device, "reference": previous, "offset_bpm": offset,
                     "applied_bpm": applied, "n_runs": n_dev, "n_reference": n_ref,
                     "n_cells": len(diffs)})
    return pd.DataFrame(rows, columns=columns)


def hr_sensor(dates: pd.Series, sensors: tuple[tuple[date, str], ...]) -> pd.Series:
    """The configured heart-rate sensor in use on each date; None before the first one."""
    out = pd.Series([None] * len(dates), index=dates.index, dtype=object)
    for since, name in sorted(sensors):
        out[dates >= pd.Timestamp(since)] = name
    return out


def gear_yearly(runs: pd.DataFrame, season: tuple[int, ...] | None = None) -> pd.DataFrame:
    """Per year, the share of kept runs per watch and per configured HR sensor. A sensor
    change can shift heart rate by a few bpm, so a step that lines up with one is not fitness."""
    kept = runs[runs["excluded"].isna()]
    if season:
        kept = kept[kept["date"].dt.month.isin(season)]
    columns = ["year", "n_runs", "watches", "sensors"]
    if kept.empty:
        return pd.DataFrame(columns=columns)

    def shares(values: pd.Series, missing: str) -> dict[str, float]:
        counts = values.fillna(missing).value_counts()
        return {name: 100 * n / counts.sum() for name, n in counts.items()}

    rows = [{"year": int(year), "n_runs": len(group),
             "watches": shares(group["device"], "unknown"),
             "sensors": shares(group["hr_sensor"], "none set")}
            for year, group in kept.groupby("year")]
    return pd.DataFrame(rows, columns=columns)


def band_table(runs: pd.DataFrame, by: str = "year", season: tuple[int, ...] | None = None
               ) -> pd.DataFrame:
    """Per period (year or month), surface and pace band: n runs, km, HR, % of max HR,
    speed per heartbeat (m/beat, grade-adjusted), median start temperature, noisy flag."""
    if by not in ("year", "month"):
        raise ValueError(f"by must be 'year' or 'month'; got {by!r}")
    kept = runs[runs["excluded"].isna()]
    if season:
        kept = kept[kept["date"].dt.month.isin(season)]
    columns = ["period", "surface", "band", "n_runs", "km", "mean_hr", "hr_pct_max",
               "speed_per_beat", "temp_c", "noisy"]
    if kept.empty:
        return pd.DataFrame(columns=columns)
    out = kept.groupby([by, "surface_band", "band"], as_index=False).agg(
        n_runs=("activity_id", "count"), km=("distance_km", "sum"), mean_hr=("core_hr", "mean"),
        hr_pct_max=("hr_pct_max", "mean"), speed_per_beat=("speed_per_beat", "mean"),
        temp_c=("temp_c", "median"),
    ).rename(columns={by: "period", "surface_band": "surface"})
    out["noisy"] = out["n_runs"] < NOISY_RUNS
    out["band"] = pd.Categorical(out["band"], categories=PACE_BANDS, ordered=True)
    out = out.sort_values(["period", "surface", "band"])
    out["band"] = out["band"].astype(str)
    return out[columns].reset_index(drop=True)


def yearly_efficiency(*, activities: pd.DataFrame | None = None, cfg: Config | None = None,
                      season: tuple[int, ...] | None = None,
                      offsets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aerobic efficiency (easy flat road runs) per year: the monthly medians weighted by
    their run count, optionally only over the months in `season`, with each watch's HR
    offset applied (`offsets` from watch_offsets; fitted here when not given)."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    if offsets is None:
        offsets = watch_offsets(band_runs(activities=acts, cfg=cfg))
    if not offsets.empty and "device" in acts:
        shift = acts["device"].str.replace(r"^Garmin ", "", regex=True).map(
            offsets.set_index("device")["applied_bpm"]).fillna(0.0)
        acts = acts.assign(avg_hr=acts["avg_hr"] + shift)
    monthly = aerobic_efficiency(activities=acts, cfg=cfg)
    columns = ["year", "efficiency", "n_runs", "n_months"]
    if season:
        monthly = monthly[monthly["month"].dt.month.isin(season)]
    if monthly.empty:
        return pd.DataFrame(columns=columns)
    monthly = monthly.assign(year=monthly["month"].dt.year,
                             weighted=monthly["efficiency"] * monthly["n_runs"])
    out = monthly.groupby("year", as_index=False).agg(
        weighted=("weighted", "sum"), n_runs=("n_runs", "sum"), n_months=("month", "count"))
    out["efficiency"] = out.pop("weighted") / out["n_runs"]
    return out[columns]


def intensity_yearly(*, activities: pd.DataFrame | None = None, cfg: Config | None = None,
                     season: tuple[int, ...] | None = None) -> pd.DataFrame:
    """Share of running minutes per year in easy, steady and hard sessions (Garmin
    training effect), plus the rated share: years before the watch had no training effect."""
    acts = activities if activities is not None else _load(cfg=cfg or load_config())
    columns = ["year", *(f"{k}_pct" for k in INTENSITIES), "rated_pct", "minutes"]
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    if season:
        runs = runs[runs["date"].dt.month.isin(season)]
    if runs.empty or "aerobic_te" not in runs.columns:
        return pd.DataFrame(columns=columns)
    kinds = intensity(runs)
    rows = []
    for year, group in runs.groupby("year"):
        minutes = group["duration_min"]
        rated = minutes.where(kinds[group.index].notna())
        total = float(rated.sum())
        if total <= 0:
            continue
        by_kind = rated.groupby(kinds[group.index]).sum()
        rows.append({"year": int(year),
                     **{f"{k}_pct": 100 * float(by_kind.get(k, 0.0)) / total for k in INTENSITIES},
                     "rated_pct": 100 * total / float(minutes.sum()), "minutes": float(minutes.sum())})
    return pd.DataFrame(rows, columns=columns)


def since_year(frame: pd.DataFrame, first_year: int, column: str = "period") -> pd.DataFrame:
    """Rows of `frame` whose `column` (a year, or a date) is `first_year` or later."""
    if frame.empty:
        return frame
    values = frame[column]
    years = values.dt.year if pd.api.types.is_datetime64_any_dtype(values) else values
    return frame[years >= first_year]


def default_first_year(today=None) -> int:
    """Five years before this one: how far back the by-band tables start by default."""
    return pd.Timestamp(today if today is not None else date.today()).year - 5
