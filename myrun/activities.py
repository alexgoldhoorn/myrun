"""activities() and runs(): one row per activity."""

from __future__ import annotations

from contextlib import closing

import pandas as pd

from myrun import derive
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.optional import enrich
from myrun.stravadb import open_db

# Strava reports cadence for these as one leg per minute.
CADENCE_DOUBLED = ("Run", "TrailRun", "Walk", "Hike")

_SQL = """
SELECT activityId AS activity_id,
       startDateTime AS start,
       sportType AS sport,
       name,
       distance AS distance_m,
       elevation AS elevation_m,
       averageSpeed AS speed_kmh,
       averageHeartRate AS avg_hr,
       maxHeartRate AS max_hr,
       averageCadence AS cadence,
       movingTimeInSeconds AS moving_s,
       workoutType AS workout_type,
       {device} AS device,
       COALESCE(streamsAreImported, 0) AS has_streams,
       CASE WHEN json_valid(data) THEN json_extract(data, '$.suffer_score') END AS relative_effort,
       CASE WHEN json_valid(weather) THEN json_extract(weather, '$.temperature_2m') END AS temp_c,
       CASE WHEN json_valid(weather) THEN json_extract(weather, '$.apparent_temperature') END
            AS feels_like_c,
       CASE WHEN json_valid(weather) THEN json_extract(weather, '$.relativehumidity_2m') END
            AS humidity_pct,
       CASE WHEN json_valid(weather) THEN json_extract(weather, '$.dewpoint_2m') END AS dew_point_c
FROM Activity
WHERE COALESCE(markedForDeletion, 0) != 1
ORDER BY startDateTime
"""

_NUMERIC = ("distance_m", "elevation_m", "speed_kmh", "avg_hr", "max_hr", "cadence", "moving_s",
            "relative_effort", "temp_c", "feels_like_c", "humidity_pct", "dew_point_c")


def activities(sports=None, since=None, *, cfg: Config | None = None) -> pd.DataFrame:
    """One row per activity of any sport, oldest first.

    `sports` is a list of Strava sport types to keep (`["Run", "Ride"]`); `since` is a date
    or date string. Activities marked for deletion in statistics-for-strava are left out.

    Columns: activity_id, start, date, hour (decimal), year, sport, name, distance_km,
    duration_min (moving time), pace_min_km, speed_kmh, elevation_m, hilliness_m_km, avg_hr,
    max_hr, cadence_spm, relative_effort (Strava's suffer score, NaN when absent), temp_c,
    feels_like_c, humidity_pct, dew_point_c, device, has_streams, workout_type (Strava's
    own, e.g. race or longRun), surface (road, trail or mixed, None for other sports),
    session_type (easy, tempo, ..., race; None when unknown) and race_name. When the Garmin
    input is set, its columns are added too.

    Cadence is doubled for Run, TrailRun, Walk and Hike because Strava stores one leg."""
    cfg = cfg or load_config()
    with closing(open_db(cfg)) as conn:
        has_device = any(r[1] == "deviceName" for r in conn.execute("PRAGMA table_info(Activity)"))
        # deviceName is optional: older statistics-for-strava databases do not have it
        df = pd.read_sql_query(_SQL.format(device="deviceName" if has_device else "NULL"), conn)

    for column in _NUMERIC:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype("float64")
    df["start"] = pd.to_datetime(df["start"])
    df["date"] = df["start"].dt.normalize()
    df["hour"] = df["start"].dt.hour + df["start"].dt.minute / 60
    df["year"] = df["start"].dt.year
    df["has_streams"] = df["has_streams"].astype(bool)
    for device, owned_from in cfg.device_owned_from.items():   # the previous owner's activities
        df = df[~((df["device"] == device) & (df["date"] < pd.Timestamp(owned_from)))]

    df["distance_km"] = df.pop("distance_m") / 1000
    df["duration_min"] = df.pop("moving_s") / 60
    has_distance = df["distance_km"] > 0
    df["pace_min_km"] = (df["duration_min"] / df["distance_km"]).where(has_distance)
    df["speed_kmh"] = df["speed_kmh"].where(has_distance)
    cadence = df.pop("cadence")
    df["cadence_spm"] = cadence.where(~df["sport"].isin(CADENCE_DOUBLED), cadence * 2)

    df["hilliness_m_km"] = derive.hilliness(df["elevation_m"], df["distance_km"])
    df["surface"] = derive.surface(df["sport"], df["hilliness_m_km"], cfg.mixed_hilliness_m_per_km)
    df = enrich(df, cfg)

    if sports is not None:
        df = df[df["sport"].isin(list(sports))]
    if since is not None:
        df = df[df["date"] >= pd.Timestamp(since).normalize()]
    return df.reset_index(drop=True)


def runs(since=None, *, cfg: Config | None = None) -> pd.DataFrame:
    """activities() restricted to running sports (Strava `Run` and `TrailRun`)."""
    return activities(RUN_SPORTS, since, cfg=cfg)
