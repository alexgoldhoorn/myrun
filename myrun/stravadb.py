"""Read-only access to a statistics-for-strava SQLite database."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import zstandard

from myrun.config import Config

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

REQUIRED: dict[str, tuple[str, ...]] = {
    "Activity": ("activityId", "startDateTime", "data", "weather", "sportType", "name", "distance",
                 "elevation", "averageSpeed", "averageHeartRate", "maxHeartRate", "averageCadence",
                 "movingTimeInSeconds", "markedForDeletion", "workoutType"),
    "ActivityStream": ("activityId", "streamType", "data"),
    "ActivitySplit": ("activityId", "unitSystem", "splitNumber", "distance",
                      "movingTimeInSeconds", "elevationDifference", "gapPaceInSecondsPerKm"),
    "ActivityLap": ("activityId", "lapNumber", "name", "movingTimeInSeconds", "distance",
                    "elevationDifference", "averageHeartRate"),
    "ActivityBestEffort": ("activityId", "distanceInMeter", "sportType", "timeInSeconds"),
}


class StravaDbError(Exception):
    pass


def open_db(cfg: Config) -> sqlite3.Connection:
    """Open the database read-only and verify the tables and columns this app reads."""
    path = Path(cfg.strava_db)
    if not path.is_file():
        raise StravaDbError(f"statistics-for-strava database not found: {path}")
    try:
        conn = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)
        for table, columns in REQUIRED.items():
            have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not have:
                raise StravaDbError(f"{path}: table {table} is missing")
            missing = [c for c in columns if c not in have]
            if missing:
                raise StravaDbError(f"{path}: table {table} lacks column(s) {', '.join(missing)}")
        # "streams imported": Activity.streamsAreImported before dreeve v5.5.0, an
        # ActivityScan table (type 'streams') from v5.5.0 on. One of the two must exist.
        activity = {row[1] for row in conn.execute("PRAGMA table_info(Activity)")}
        scan = {row[1] for row in conn.execute("PRAGMA table_info(ActivityScan)")}
        if "streamsAreImported" not in activity and not {"activityId", "type"} <= scan:
            raise StravaDbError(f"{path}: neither Activity.streamsAreImported nor an "
                                "ActivityScan table (statistics-for-strava/dreeve schema changed)")
    except sqlite3.Error as exc:
        raise StravaDbError(f"{path}: cannot read database ({exc})") from exc
    return conn


def decode_blob(data: bytes | None) -> Any:
    """Decode a stream or metric blob: zstd-compressed JSON, or plain JSON."""
    if data is None:
        return None
    try:
        if data[:4] == ZSTD_MAGIC:
            data = zstandard.ZstdDecompressor().decompressobj().decompress(data)
        return json.loads(data)
    except (zstandard.ZstdError, UnicodeDecodeError) as exc:
        raise ValueError(f"undecodable blob: {exc}") from exc


def db_mtime(path: Path) -> datetime:
    """Last change of the database. In WAL mode recent writes are in the -wal file."""
    path = Path(path)
    times = [path.stat().st_mtime]
    wal = path.with_name(path.name + "-wal")
    if wal.exists():
        times.append(wal.stat().st_mtime)
    return datetime.fromtimestamp(max(times))
