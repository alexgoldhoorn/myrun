import numpy as np
import pandas as pd
import pytest

from myrun.activities import activities, runs
from myrun.config import Config
from tests.fixture import DELETED, GYM, HILLY, NOEFFORT, STEADY, TODAY, TRAIL, build_fixture


def _row(df, activity_id):
    return df.set_index("activity_id").loc[activity_id]


def test_deleted_activities_are_excluded(cfg):
    df = activities(cfg=cfg)
    assert len(df) == 7
    assert DELETED not in set(df["activity_id"])


def test_units_and_derived_columns(cfg):
    row = _row(activities(cfg=cfg), STEADY)
    assert row["distance_km"] == pytest.approx(7.2)
    assert row["duration_min"] == pytest.approx(40.0)
    assert row["pace_min_km"] == pytest.approx(40 / 7.2)
    assert row["speed_kmh"] == pytest.approx(10.8)
    assert row["cadence_spm"] == 170
    assert row["relative_effort"] == 40
    assert row["temp_c"] == 12.0
    assert row["feels_like_c"] == 11.0
    assert row["hour"] == 7.5
    assert row["date"] == pd.Timestamp(TODAY) - pd.Timedelta(days=1)
    assert row["hilliness_m_km"] == pytest.approx(30 / 7.2)
    assert row["surface"] == "road"
    assert bool(row["has_streams"]) is True


def test_surface_classes(cfg):
    df = activities(cfg=cfg)
    assert _row(df, HILLY)["surface"] == "mixed"
    assert _row(df, TRAIL)["surface"] == "trail"
    assert _row(df, GYM)["surface"] is None


def test_zero_distance_and_missing_values_do_not_produce_inf(cfg):
    df = activities(cfg=cfg)
    gym = _row(df, GYM)
    assert np.isnan(gym["pace_min_km"])
    assert np.isnan(gym["hilliness_m_km"])
    assert np.isnan(gym["temp_c"])          # weather is ''
    assert gym["cadence_spm"] == 85         # not doubled for a non-running sport
    bare = _row(df, NOEFFORT)
    assert np.isnan(bare["relative_effort"])
    assert np.isnan(bare["avg_hr"])
    assert np.isnan(bare["temp_c"])         # weather is '[]'
    numeric = df.select_dtypes("number")
    assert not np.isinf(numeric.to_numpy(dtype=float)).any()


def test_runs_and_filters(cfg):
    assert set(runs(cfg=cfg)["sport"]) == {"Run", "TrailRun"}
    assert len(runs(cfg=cfg)) == 6
    recent = activities(since=pd.Timestamp(TODAY) - pd.Timedelta(days=3), cfg=cfg)
    assert set(recent["activity_id"]) == {STEADY, HILLY, GYM}
    assert activities(sports=["TrailRun"], cfg=cfg)["activity_id"].tolist() == [TRAIL]


def test_sorted_by_start(cfg):
    assert activities(cfg=cfg)["start"].is_monotonic_increasing


def test_empty_database(tmp_path):
    cfg = Config(strava_db=build_fixture(tmp_path / "e.db", TODAY, empty=True),
                 cache_dir=tmp_path / "c")
    df = activities(cfg=cfg)
    assert df.empty
    assert {"activity_id", "date", "distance_km", "surface", "session_type"} <= set(df.columns)
