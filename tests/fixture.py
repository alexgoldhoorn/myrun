"""Synthetic statistics-for-strava database and optional-input files. No real data."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import zstandard

TODAY = date(2026, 10, 5)  # a Monday

STEADY, HILLY, TRAIL, RACE, GYM, NOEFFORT, DELETED, OLD = (f"activity-{n}" for n in range(1, 9))

# (days before today, hour, minute)
_WHEN = {
    STEADY: (1, 7, 30),
    HILLY: (3, 18, 30),
    TRAIL: (8, 9, 0),
    RACE: (15, 10, 30),
    GYM: (2, 19, 0),
    NOEFFORT: (10, 7, 0),
    DELETED: (4, 8, 0),
    OLD: (40, 7, 0),
}


def start_of(activity_id: str, today: date) -> datetime:
    days, hour, minute = _WHEN[activity_id]
    return datetime.combine(today - timedelta(days=days), time(hour, minute))


SCHEMA = """
CREATE TABLE Activity (activityId VARCHAR(255) PRIMARY KEY, startDateTime DATETIME, data CLOB,
  weather CLOB, sportType VARCHAR(255), name VARCHAR(255), distance INTEGER, elevation INTEGER,
  averageSpeed DOUBLE, averageHeartRate INTEGER, maxHeartRate INTEGER, averageCadence INTEGER,
  movingTimeInSeconds INTEGER, markedForDeletion BOOLEAN, workoutType VARCHAR(255),
  streamsAreImported BOOLEAN);
CREATE TABLE ActivityStream (activityId VARCHAR(255), streamType VARCHAR(255), createdOn DATETIME,
  dataSize INTEGER, data BLOB);
CREATE TABLE ActivitySplit (activityId VARCHAR(255), unitSystem VARCHAR(255), splitNumber INTEGER,
  distance INTEGER, elapsedTimeInSeconds INTEGER, movingTimeInSeconds INTEGER,
  elevationDifference INTEGER, averageSpeed DOUBLE, minAverageSpeed DOUBLE, maxAverageSpeed INTEGER,
  paceZone INTEGER, gapPaceInSecondsPerKm DOUBLE);
CREATE TABLE ActivityLap (lapId VARCHAR(255), activityId VARCHAR(255), lapNumber INTEGER,
  name VARCHAR(255), elapsedTimeInSeconds INTEGER, movingTimeInSeconds INTEGER, distance INTEGER,
  averageSpeed DOUBLE, maxSpeed DOUBLE, elevationDifference INTEGER, averageHeartRate INTEGER,
  minAverageSpeed DOUBLE, maxAverageSpeed DOUBLE);
CREATE TABLE ActivityBestEffort (activityId VARCHAR(255), distanceInMeter INTEGER,
  sportType VARCHAR(255), timeInSeconds INTEGER);
"""


def _z(values) -> bytes:
    return zstandard.ZstdCompressor().compress(json.dumps(values).encode())


def _weather(temp: float) -> str:
    return json.dumps(
        {
            "temperature_2m": temp,
            "apparent_temperature": temp - 1,
            "relativehumidity_2m": 70,
            "dewpoint_2m": temp - 5,
        }
    )


def _activity(conn, aid, today, sport, dist, elev, moving, hr, effort, *, weather=None,
              workout=None, deleted=0, streams=0):
    data = {} if effort is None else {"suffer_score": effort}
    speed = dist / moving * 3.6 if moving and dist else 0
    conn.execute(
        "INSERT INTO Activity VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (aid, start_of(aid, today).strftime("%Y-%m-%d %H:%M:%S"), json.dumps(data), weather,
         sport, "Morning Run", dist, elev, speed, hr, None if hr is None else hr + 6, 85,
         moving, deleted, workout, streams),
    )


def _stream(conn, aid, stream_type, values):
    conn.execute(
        "INSERT INTO ActivityStream VALUES (?,?,?,?,?)",
        (aid, stream_type, "2026-01-01 00:00:00", len(values), _z(values)),
    )


def build_fixture(path: Path, today: date = TODAY, empty: bool = False) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    if empty:
        conn.commit()
        conn.close()
        return path

    #          id        sport            dist   elev moving  hr   effort
    _activity(conn, STEADY, today, "Run", 7200, 30, 2400, 144, 40, weather=_weather(12.0), streams=1)
    _activity(conn, HILLY, today, "Run", 10000, 200, 3600, 150, 80, weather=_weather(22.0))
    _activity(conn, TRAIL, today, "TrailRun", 15000, 600, 6000, 152, 120, weather=_weather(18.0))
    _activity(conn, RACE, today, "Run", 10000, 50, 2700, 165, 90, weather=_weather(9.0),
              workout="race", streams=1)
    _activity(conn, GYM, today, "WeightTraining", 0, 0, 1800, 100, 15, weather="")
    _activity(conn, NOEFFORT, today, "Run", 5000, 10, 1500, None, None, weather="[]", streams=1)
    _activity(conn, DELETED, today, "Run", 8000, 20, 2400, 140, 500, deleted=1)
    _activity(conn, OLD, today, "Run", 10000, 40, 3000, 140, 50, weather=_weather(15.0))

    # STEADY: 40 minutes at 3.0 m/s, HR 140 in the first half and 147 in the second.
    n = 2400
    _stream(conn, STEADY, "time", list(range(n)))
    _stream(conn, STEADY, "distance", [3.0 * i for i in range(n)])
    _stream(conn, STEADY, "heartrate", [140 if i < 1200 else 147 for i in range(n)])
    _stream(conn, STEADY, "velocity_smooth", [3.0] * n)
    _stream(conn, STEADY, "altitude", [50.0] * n)
    _stream(conn, STEADY, "cadence", [85] * n)
    _stream(conn, STEADY, "grade_smooth", [0.0] * n)
    _stream(conn, STEADY, "moving", [True] * n)
    # RACE: a short, broken set. velocity_smooth has the wrong length on purpose.
    _stream(conn, RACE, "time", list(range(10)))
    _stream(conn, RACE, "heartrate", [165] * 10)
    _stream(conn, RACE, "velocity_smooth", [3.7] * 7)
    # NOEFFORT: streamsAreImported = 1 but no stream rows at all.

    elev = [30, -30, 0, 5, -5, 0, 0, 0]
    dist = [1000] * 7 + [200]
    moving = [333] * 7 + [67]
    for i in range(8):
        conn.execute(
            "INSERT INTO ActivitySplit VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (STEADY, "metric", i + 1, dist[i], moving[i], moving[i], elev[i], 3.0, 3.0, 3, 2, 333.0),
        )
    for i in range(4):
        conn.execute(
            "INSERT INTO ActivitySplit VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (STEADY, "imperial", i + 1, 1609, 536, 536, 0, 3.0, 3.0, 3, 2, 333.0),
        )
    for lap, hr in ((1, 140), (2, 147)):
        conn.execute(
            "INSERT INTO ActivityLap VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"lap-{lap}", STEADY, lap, f"Lap {lap}", 1200, 1200, 3600, 3.0, 3.2, 0, hr, 3.0, 3.2),
        )
    efforts = [(STEADY, 1000, 333), (STEADY, 5000, 1667), (RACE, 1000, 250), (RACE, 5000, 1330),
               (RACE, 10000, 2700), (OLD, 5000, 1500)]
    conn.executemany("INSERT INTO ActivityBestEffort VALUES (?,?,'Run',?)", efforts)
    conn.commit()
    conn.close()
    return path


# ---- optional input files -------------------------------------------------

RACE_COLUMNS = {
    "name": "name ",
    "date": "date",
    "type": "type",
    "distance_km": "distance (km)",
    "official_time": "official time",
    "rank_pct": "Rank % (all)",
    "garmin_url": "Garmin URL",
}


def write_wellness(path: Path, today: date = TODAY, days: int = 30) -> Path:
    dates = pd.date_range(end=pd.Timestamp(today), periods=days)
    pd.DataFrame(
        {"date": dates, "readiness": 70.0, "sleep_hours": 7.0, "hrv_ms": 50.0, "resting_hr": 48.0}
    ).to_parquet(path)
    return path


def write_plan(path: Path, today: date = TODAY) -> Path:
    def d(offset):
        return (today + timedelta(days=offset)).isoformat()

    rows = [
        (d(-3), "Intervals 10km", "intervals", "10"),
        (d(-1), "Easy Run 7km", "easy", "7"),
        (d(0), "Rest", "rest", ""),
        (d(2), "Long Run 18km", "long", "18"),
        (d(27), "Trail Race 23km", "race", "23"),
    ]
    lines = ["date,session,type,distance_km"] + [",".join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


def write_races(path: Path, today: date = TODAY) -> Path:
    day = today - timedelta(days=15)
    path.write_text(
        "name ,date,type,distance (km),official time,Rank % (all),Garmin URL\n"
        f"Test 10K,{day.day}/{day.month}/{day.year},mixed,10,00:45:00,14.97%,"
        "https://connect.garmin.com/modern/activity/1\n"
    )
    return path


def write_garmin(path: Path, today: date = TODAY) -> Path:
    pd.DataFrame(
        {
            "start": [start_of(STEADY, today) + timedelta(seconds=30),
                      start_of(HILLY, today) + timedelta(minutes=10)],
            "garmin_activity_id": [111, 222],
            "session_name": ["Tempo 7km", "Somewhere else"],
            "session_type": ["tempo", "long"],
            "ground_contact_ms": [250.0, 260.0],
            "vertical_oscillation_cm": [8.5, 9.0],
            "stride_length_m": [1.10, 1.05],
        }
    ).to_parquet(path)
    return path
