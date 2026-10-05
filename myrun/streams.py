"""Per-activity detail: streams, HR zones, HR drift, laps."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import closing

import numpy as np
import pandas as pd

from myrun.activities import CADENCE_DOUBLED
from myrun.config import Config, load_config
from myrun.stravadb import decode_blob, open_db

COLUMNS = ["time_s", "distance_m", "hr", "speed_ms", "pace_min_km", "altitude_m", "cadence_spm",
           "grade_pct", "moving"]

_STREAMS = {"time": "time_s", "distance": "distance_m", "heartrate": "hr",
            "velocity_smooth": "speed_ms", "altitude": "altitude_m", "cadence": "cadence_spm",
            "grade_smooth": "grade_pct", "moving": "moving"}

MAX_SAMPLE_GAP_S = 10  # a longer gap between samples is a pause, not time in a zone


def activity_streams(activity_id: str, *, cfg: Config | None = None) -> pd.DataFrame:
    """Sample-by-sample series for one activity. Empty when it has no usable streams."""
    cfg = cfg or load_config()
    arrays: dict[str, list] = {}
    with closing(open_db(cfg)) as conn:
        rows = conn.execute(
            "SELECT streamType, CAST(data AS BLOB) FROM ActivityStream WHERE activityId = ?",
            (activity_id,),
        ).fetchall()
        sport = conn.execute(
            "SELECT sportType FROM Activity WHERE activityId = ?", (activity_id,)
        ).fetchone()
    for stream_type, blob in rows:
        column = _STREAMS.get(stream_type)
        if column is None:
            continue
        try:
            values = decode_blob(blob)
        except ValueError:
            continue
        if isinstance(values, list) and values:
            arrays[column] = values

    time = arrays.get("time_s")
    if not time:
        return pd.DataFrame(columns=COLUMNS)
    # A stream whose length differs from the time axis cannot be aligned; leave it out.
    df = pd.DataFrame({c: v for c, v in arrays.items() if len(v) == len(time)})
    if "cadence_spm" in df and sport and sport[0] in CADENCE_DOUBLED:
        df["cadence_spm"] = df["cadence_spm"] * 2
    if "speed_ms" in df:
        speed = df["speed_ms"].astype(float)
        df["pace_min_km"] = (1000 / speed.where(speed >= 0.5) / 60)
    return df.reindex(columns=COLUMNS)


def zone_seconds(streams_df: pd.DataFrame, upper_bounds: Sequence[int]) -> pd.DataFrame:
    """Seconds and share of time in each HR zone. Zone n ends at upper_bounds[n-1] inclusive."""
    bounds = [int(b) for b in upper_bounds]
    zones = pd.DataFrame({
        "zone": range(1, len(bounds) + 2),
        "lower": [0] + [b + 1 for b in bounds],
        "upper": [float(b) for b in bounds] + [float("nan")],
    })
    seconds = pd.Series(0.0, index=zones["zone"])
    if len(streams_df):
        time = pd.to_numeric(streams_df["time_s"], errors="coerce")
        hr = pd.to_numeric(streams_df["hr"], errors="coerce")
        step = time.diff().shift(-1)
        step = step.fillna(step.median() if step.notna().any() else 1.0).clip(upper=MAX_SAMPLE_GAP_S)
        valid = hr > 0
        if valid.any():
            zone = np.searchsorted(bounds, hr[valid].to_numpy(), side="left") + 1
            seconds = seconds.add(step[valid].groupby(zone).sum(), fill_value=0.0)
    zones["seconds"] = seconds.reindex(zones["zone"]).to_numpy()
    total = zones["seconds"].sum()
    zones["pct"] = zones["seconds"] / total * 100 if total else 0.0
    return zones


def drift_pct(streams_df: pd.DataFrame, min_minutes: float = 30) -> float | None:
    """Change in speed-per-heartbeat from the first to the second half, in percent.

    Positive means the second half cost more heartbeats for the same speed.
    """
    if streams_df.empty:
        return None
    s = streams_df[["time_s", "hr", "speed_ms", "moving"]].copy()
    moving = s["moving"].map(lambda v: True if pd.isna(v) else bool(v))
    s["hr"] = pd.to_numeric(s["hr"], errors="coerce")
    s["speed_ms"] = pd.to_numeric(s["speed_ms"], errors="coerce")
    s = s[moving & (s["hr"] > 0) & (s["speed_ms"] > 0)]
    if s.empty:
        return None
    first_t, last_t = float(s["time_s"].min()), float(s["time_s"].max())
    if last_t - first_t < min_minutes * 60:
        return None
    middle = (first_t + last_t) / 2
    early, late = s[s["time_s"] <= middle], s[s["time_s"] > middle]
    if early.empty or late.empty:
        return None
    ef_early = early["speed_ms"].mean() / early["hr"].mean()
    ef_late = late["speed_ms"].mean() / late["hr"].mean()
    return float((ef_early - ef_late) / ef_early * 100)


def hr_zones(activity_id: str, *, cfg: Config | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    return zone_seconds(activity_streams(activity_id, cfg=cfg), cfg.hr_zone_upper_bounds)


def hr_drift(activity_id: str, *, cfg: Config | None = None) -> float | None:
    cfg = cfg or load_config()
    return drift_pct(activity_streams(activity_id, cfg=cfg))


def activity_laps(activity_id: str, *, cfg: Config | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    with closing(open_db(cfg)) as conn:
        laps = pd.read_sql_query(
            """SELECT lapNumber AS lap, name, distance AS distance_m,
                      movingTimeInSeconds AS duration_s, averageHeartRate AS avg_hr,
                      elevationDifference AS elev_diff_m
               FROM ActivityLap WHERE activityId = ? ORDER BY lapNumber""",
            conn, params=(activity_id,),
        )
    laps["distance_km"] = pd.to_numeric(laps.pop("distance_m"), errors="coerce") / 1000
    laps["pace_min_km"] = (laps["duration_s"] / 60 / laps["distance_km"]).where(
        laps["distance_km"] > 0)
    return laps[["lap", "name", "distance_km", "duration_s", "pace_min_km", "avg_hr",
                 "elev_diff_m"]]
