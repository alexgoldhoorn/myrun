"""Long-term trend tables."""

from __future__ import annotations

from contextlib import closing

import pandas as pd

from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.stravadb import open_db

_FREQ = {"week": "W-SUN", "month": "M", "year": "Y"}
MIN_EFFICIENCY_MINUTES = 20


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


def aerobic_efficiency(*, activities: pd.DataFrame | None = None,
                       cfg: Config | None = None) -> pd.DataFrame:
    """Monthly median of speed (m/min) per heartbeat on easy, flat road runs."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    low, high = cfg.easy_hr_band
    easy = acts[
        (acts["sport"] == "Run")
        & (acts["duration_min"] >= MIN_EFFICIENCY_MINUTES)
        & (acts["hilliness_m_km"] < cfg.efficiency_max_hilliness_m_per_km)
        & acts["avg_hr"].between(low, high)
        & (acts["speed_kmh"] > 0)
    ].copy()
    easy["efficiency"] = easy["speed_kmh"] * 1000 / 60 / easy["avg_hr"]
    easy["month"] = easy["date"].dt.to_period("M").dt.start_time
    return easy.groupby("month", as_index=False).agg(
        efficiency=("efficiency", "median"),
        n_runs=("activity_id", "count"),
        median_pace_min_km=("pace_min_km", "median"),
    )
