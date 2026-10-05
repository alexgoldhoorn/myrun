"""splits(): one row per kilometre, with heart rate and cadence computed from streams.

Decoding streams is the slow part, so the per-split averages are cached in a Parquet
file under cfg.cache_dir. The cache is derived data: delete it to rebuild. An activity
re-imported by statistics-for-strava with changed streams is not detected; delete the
cache in that case.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from contextlib import closing

import numpy as np
import pandas as pd

from myrun import derive
from myrun.activities import activities
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.stravadb import open_db
from myrun.streams import activity_streams

log = logging.getLogger(__name__)

CACHE_NAME = "split_metrics.parquet"
MIN_SPLIT_M = 500
_CACHE_COLUMNS = ["activity_id", "split", "avg_hr", "avg_cadence_spm"]
_PARENT = ["activity_id", "date", "hour", "year", "sport", "surface", "session_type", "temp_c",
           "hilliness_m_km"]

_SQL = """
SELECT s.activityId AS activity_id, s.splitNumber AS split, s.distance AS distance_m,
       s.movingTimeInSeconds AS duration_s, s.elevationDifference AS elev_diff_m,
       s.gapPaceInSecondsPerKm AS gap_s_km
FROM ActivitySplit s JOIN Activity a ON a.activityId = s.activityId
WHERE s.unitSystem = 'metric' AND COALESCE(a.markedForDeletion, 0) != 1
ORDER BY s.activityId, s.splitNumber
"""


def split_metrics(streams_df: pd.DataFrame, split_distances_m: Sequence[float]) -> pd.DataFrame:
    """Average HR and cadence per split, assigning each sample by cumulative distance."""
    edges = np.cumsum(np.asarray(split_distances_m, dtype=float))
    s = streams_df[["distance_m", "hr", "cadence_spm"]].apply(pd.to_numeric, errors="coerce")
    s = s.dropna(subset=["distance_m"])
    s["split"] = np.searchsorted(edges, s["distance_m"].to_numpy(), side="right") + 1
    s = s[s["split"] <= len(edges)]
    out = pd.DataFrame({
        "avg_hr": s["hr"].where(s["hr"] > 0).groupby(s["split"]).mean(),
        "avg_cadence_spm": s["cadence_spm"].where(s["cadence_spm"] > 0).groupby(s["split"]).mean(),
    })
    return out.rename_axis("split").reset_index()


def _read_cache(cfg: Config) -> pd.DataFrame:
    path = cfg.cache_dir / CACHE_NAME
    if path.is_file():
        try:
            cached = pd.read_parquet(path)
            if set(_CACHE_COLUMNS) <= set(cached.columns):
                return cached[_CACHE_COLUMNS]
        except Exception as exc:  # any unreadable cache is simply rebuilt
            log.warning("split cache unreadable, rebuilding: %s", exc)
    return pd.DataFrame(columns=_CACHE_COLUMNS)


def _write_cache(cfg: Config, cache: pd.DataFrame) -> None:
    path = cfg.cache_dir / CACHE_NAME
    try:
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        cache.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("split cache not written (%s); it will be recomputed next time", exc)


def _metrics(cfg: Config, rows: pd.DataFrame, with_streams: set[str]) -> pd.DataFrame:
    cache = _read_cache(cfg)
    todo = [a for a in rows["activity_id"].unique()
            if a in with_streams and a not in set(cache["activity_id"])]
    if not todo:
        return cache
    fresh = []
    for activity_id in todo:
        distances = rows.loc[rows["activity_id"] == activity_id, "distance_m"].tolist()
        streams_df = activity_streams(activity_id, cfg=cfg)
        metrics = split_metrics(streams_df, distances) if len(streams_df) else pd.DataFrame()
        if metrics.empty:
            # Sentinel row so an activity without usable streams is not retried every call.
            metrics = pd.DataFrame({"split": [0], "avg_hr": [np.nan], "avg_cadence_spm": [np.nan]})
        metrics.insert(0, "activity_id", activity_id)
        fresh.append(metrics[_CACHE_COLUMNS])
    cache = pd.concat([cache, *fresh], ignore_index=True) if len(cache) else pd.concat(
        fresh, ignore_index=True)
    _write_cache(cfg, cache)
    return cache


def splits(since=None, *, cfg: Config | None = None) -> pd.DataFrame:
    """One row per metric km split of every run, with the run's categories attached."""
    cfg = cfg or load_config()
    with closing(open_db(cfg)) as conn:
        rows = pd.read_sql_query(_SQL, conn)
        with_streams = {r[0] for r in conn.execute(
            "SELECT DISTINCT activityId FROM ActivityStream WHERE streamType = 'heartrate'")}
    for column in ("distance_m", "duration_s", "elev_diff_m", "gap_s_km"):
        rows[column] = pd.to_numeric(rows[column], errors="coerce").astype("float64")

    parents = activities(RUN_SPORTS, since, cfg=cfg)[_PARENT]
    rows = rows[rows["activity_id"].isin(parents["activity_id"])].reset_index(drop=True)
    metrics = _metrics(cfg, rows, with_streams)

    df = rows.merge(metrics, on=["activity_id", "split"], how="left")
    df = df[df["distance_m"] >= MIN_SPLIT_M].copy()
    km = df["distance_m"] / 1000
    df["pace_min_km"] = df["duration_s"] / 60 / km
    df["gap_min_km"] = df.pop("gap_s_km") / 60
    df["grade_m_km"] = df["elev_diff_m"] / km
    df["grade_class"] = derive.grade_class(df["elev_diff_m"], df["distance_m"],
                                           cfg.grade_class_m_per_km)
    df = df.merge(parents, on="activity_id", how="left")
    return df[["activity_id", "split", "distance_m", "duration_s", "pace_min_km", "gap_min_km",
               "elev_diff_m", "grade_m_km", "grade_class", "avg_hr", "avg_cadence_spm", "date",
               "hour", "year", "sport", "surface", "session_type", "temp_c",
               "hilliness_m_km"]].reset_index(drop=True)
