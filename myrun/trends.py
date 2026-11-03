"""Long-term trend tables."""

from __future__ import annotations

import re
from contextlib import closing

import pandas as pd

from myrun import fmt
from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.hr import hr_settings
from myrun.stravadb import open_db

_FREQ = {"week": "W-SUN", "month": "M", "year": "Y"}
MIN_EFFICIENCY_MINUTES = 20    # chosen: shorter easy runs are too noisy to compare
SHOE_CHECK_KM = 700            # confirmed (the owner's Garmin Connect band): worth checking from here
SHOE_LIMIT_KM = 1000           # confirmed: from here it is due for walking only


def volume(by: str = "month", *, activities: pd.DataFrame | None = None,
           cfg: Config | None = None) -> pd.DataFrame:
    """Distance, time and elevation per period and sport."""
    if by not in _FREQ:
        raise ValueError(f"by must be one of {', '.join(_FREQ)}; got {by!r}")
    acts = activities if activities is not None else _load(cfg=cfg or load_config())
    df = acts.assign(period=acts["date"].dt.to_period(_FREQ[by]).dt.start_time,
                     duration_h=acts["duration_min"] / 60)
    out = df.groupby(["period", "sport"], as_index=False).agg(
        distance_km=("distance_km", "sum"),
        duration_h=("duration_h", "sum"),
        elevation_m=("elevation_m", "sum"),
        n=("activity_id", "count"),
    )
    return out.sort_values(["period", "sport"]).reset_index(drop=True)


def year_over_year(activities: pd.DataFrame) -> pd.DataFrame:
    """Cumulative distance by day of the year, one line per year."""
    df = activities[["date", "distance_km"]].sort_values("date")
    out = pd.DataFrame({
        "year": df["date"].dt.year.astype(str),
        "day_of_year": df["date"].dt.dayofyear,
        "distance_km": df["distance_km"].fillna(0.0),
    })
    out["cumulative_km"] = out.groupby("year")["distance_km"].cumsum()
    return out[["year", "day_of_year", "cumulative_km"]].reset_index(drop=True)


def best_efforts(distances=(1000, 5000, 10000, 21097), *, cfg: Config | None = None) -> pd.DataFrame:
    """Every recorded running best effort at the given distances; is_record marks a new all-time best."""
    cfg = cfg or load_config()
    marks = ",".join("?" for _ in distances)
    sports = ",".join("?" for _ in RUN_SPORTS)
    with closing(open_db(cfg)) as conn:
        df = pd.read_sql_query(
            f"""SELECT b.activityId AS activity_id, a.startDateTime AS start,
                       b.distanceInMeter AS distance_m, b.timeInSeconds AS time_s
                FROM ActivityBestEffort b JOIN Activity a ON a.activityId = b.activityId
                WHERE COALESCE(a.markedForDeletion, 0) != 1 AND b.distanceInMeter IN ({marks})
                  AND b.sportType IN ({sports})
                ORDER BY a.startDateTime""",
            conn, params=[*(int(d) for d in distances), *RUN_SPORTS],
        )
    df["date"] = pd.to_datetime(df.pop("start")).dt.normalize()
    df["pace_min_km"] = df["time_s"] / 60 / (df["distance_m"] / 1000)
    df["is_record"] = df["time_s"] == df.groupby("distance_m")["time_s"].cummin()
    return df[["activity_id", "date", "distance_m", "time_s", "pace_min_km", "is_record"]]


# What SQLite says when the database predates gear: no table, or no gear columns.
_NO_GEAR = re.compile(r"no such (table: Gear|column: \w+\.(gearId|isRetired))\b")


def shoes(*, cfg: Config | None = None) -> pd.DataFrame:
    """Running distance per shoe: name, km, runs, last_used, retired. In use first.

    Empty when the database has no gear (an older statistics-for-strava, or none assigned)."""
    cfg = cfg or load_config()
    columns = ["name", "km", "runs", "last_used", "retired"]
    marks = ",".join("?" for _ in RUN_SPORTS)
    try:
        with closing(open_db(cfg)) as conn:
            df = pd.read_sql_query(
                f"""SELECT g.name AS name, SUM(a.distance) / 1000.0 AS km, COUNT(*) AS runs,
                           MAX(a.startDateTime) AS last_used, COALESCE(g.isRetired, 0) AS retired
                    FROM Activity a JOIN Gear g ON g.gearId = a.gearId
                    WHERE COALESCE(a.markedForDeletion, 0) != 1 AND a.sportType IN ({marks})
                    GROUP BY g.gearId ORDER BY retired, km DESC""",
                conn, params=list(RUN_SPORTS))
    except Exception as exc:
        if not _NO_GEAR.search(str(exc)):      # any other database error is a real one
            raise
        return pd.DataFrame(columns=columns)
    df["name"] = df["name"].map(fmt.shoe_name)
    df["last_used"] = pd.to_datetime(df["last_used"]).dt.normalize()
    df["retired"] = df["retired"].astype(bool)
    return df[columns]


def shoe_status(km: float, retired: bool) -> str:
    """'' while a pair is fresh, a check note from SHOE_CHECK_KM, over from SHOE_LIMIT_KM."""
    if retired:
        return "retired"
    if km >= SHOE_LIMIT_KM:
        return f"over {SHOE_LIMIT_KM:g} km"
    return f"check ({SHOE_CHECK_KM:g} km)" if km >= SHOE_CHECK_KM else ""


def easy_runs(activities: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Easy, flat road runs of at least MIN_EFFICIENCY_MINUTES: comparable from month to month.

    Empty when no easy heart-rate band can be established."""
    band = hr_settings(cfg, activities).easy_band
    if band is None:
        return activities.iloc[0:0].copy()
    low, high = band
    return activities[
        (activities["sport"] == "Run")
        & (activities["duration_min"] >= MIN_EFFICIENCY_MINUTES)
        & (activities["hilliness_m_km"] < cfg.efficiency_max_hilliness_m_per_km)
        & activities["avg_hr"].between(low, high)
        & (activities["speed_kmh"] > 0)
    ].copy()


def aerobic_efficiency(*, activities: pd.DataFrame | None = None,
                       cfg: Config | None = None) -> pd.DataFrame:
    """Monthly median of speed (m/min) per heartbeat on easy, flat road runs."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    band = hr_settings(cfg, acts).easy_band
    if band is None:
        return pd.DataFrame(columns=["month", "efficiency", "n_runs", "median_pace_min_km"])
    easy = easy_runs(acts, cfg)
    easy["efficiency"] = easy["speed_kmh"] * 1000 / 60 / easy["avg_hr"]
    easy["month"] = easy["date"].dt.to_period("M").dt.start_time
    return easy.groupby("month", as_index=False).agg(
        efficiency=("efficiency", "median"),
        n_runs=("activity_id", "count"),
        median_pace_min_km=("pace_min_km", "median"),
    )
