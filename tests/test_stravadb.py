import json
import sqlite3

import pytest
import zstandard

from myrun.config import Config
from myrun.stravadb import StravaDbError, db_mtime, decode_blob, open_db


def test_open_db_is_read_only(cfg):
    conn = open_db(cfg)
    assert conn.execute("SELECT COUNT(*) FROM Activity").fetchone()[0] == 8
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM Activity")
    conn.close()


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(StravaDbError, match="not found"):
        open_db(Config(strava_db=tmp_path / "absent.db"))


def test_schema_check_names_the_missing_column(tmp_path):
    p = tmp_path / "old.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE Activity (activityId TEXT, startDateTime TEXT)")
    conn.commit()
    conn.close()
    with pytest.raises(StravaDbError, match="Activity.*data"):
        open_db(Config(strava_db=p))


def test_schema_check_names_the_missing_table(tmp_path, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE ActivityLap")
    conn.commit()
    conn.close()
    with pytest.raises(StravaDbError, match="ActivityLap"):
        open_db(Config(strava_db=db_path))


def test_decode_blob():
    packed = zstandard.ZstdCompressor().compress(json.dumps([1, 2, 3]).encode())
    assert decode_blob(packed) == [1, 2, 3]
    assert decode_blob(b"[4, 5]") == [4, 5]
    assert decode_blob(None) is None
    with pytest.raises(ValueError):
        decode_blob(b"\x28\xb5\x2f\xfdgarbage")
    with pytest.raises(ValueError):
        decode_blob(b"not json")


def test_db_mtime_uses_the_wal_when_newer(tmp_path, db_path):
    import os

    wal = db_path.with_name(db_path.name + "-wal")
    wal.write_bytes(b"")
    os.utime(db_path, (1_000_000, 1_000_000))
    os.utime(wal, (2_000_000, 2_000_000))
    assert db_mtime(db_path).timestamp() == 2_000_000


def test_dreeve_55_schema_without_streams_column_opens(cfg, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE ActivityScan (activityId TEXT, type TEXT, subjectId TEXT)")
    conn.execute("ALTER TABLE Activity DROP COLUMN streamsAreImported")
    conn.commit()
    conn.close()
    open_db(cfg).close()


def test_neither_streams_column_nor_activityscan_is_a_clear_error(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("ALTER TABLE Activity DROP COLUMN streamsAreImported")
    conn.commit()
    conn.close()
    with pytest.raises(StravaDbError, match="ActivityScan"):
        open_db(Config(strava_db=db_path))
