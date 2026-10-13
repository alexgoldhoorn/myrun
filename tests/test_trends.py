import pandas as pd
import pytest

from myrun import trends
from myrun.activities import activities, runs
from tests.fixture import OLD, RACE, STEADY


def test_volume_by_year(cfg):
    vol = trends.volume("year", cfg=cfg).set_index("sport")
    assert vol.loc["Run", "distance_km"] == pytest.approx(42.2)
    assert vol.loc["Run", "n"] == 5
    assert vol.loc["TrailRun", "elevation_m"] == 600
    assert vol.loc["WeightTraining", "duration_h"] == pytest.approx(0.5)
    assert vol.loc["Run", "period"] == pd.Timestamp("2026-01-01")


def test_volume_rejects_an_unknown_period(cfg):
    with pytest.raises(ValueError, match="by"):
        trends.volume("decade", cfg=cfg)


def test_year_over_year(cfg):
    yoy = trends.year_over_year(activities(("Run", "TrailRun"), cfg=cfg))
    assert yoy["year"].unique().tolist() == ["2026"]
    assert yoy["cumulative_km"].iloc[-1] == pytest.approx(57.2)
    assert yoy["cumulative_km"].is_monotonic_increasing


def test_best_efforts_and_records(cfg):
    five = trends.best_efforts(cfg=cfg).query("distance_m == 5000").set_index("activity_id")
    assert five.loc[OLD, "is_record"]
    assert five.loc[RACE, "is_record"]
    assert not five.loc[STEADY, "is_record"]
    assert five.loc[RACE, "pace_min_km"] == pytest.approx(1330 / 60 / 5)
    assert set(trends.best_efforts(cfg=cfg)["distance_m"]) == {1000, 5000, 10000}


def test_aerobic_efficiency(cfg):
    eff = trends.aerobic_efficiency(cfg=cfg).set_index("month")
    # Only OLD (August) and STEADY (October) qualify: the race is above the easy band,
    # the hilly run is too hilly, the trail run is not sport Run, one run has no HR.
    assert list(eff.index) == [pd.Timestamp("2026-08-01"), pd.Timestamp("2026-10-01")]
    assert eff.loc[pd.Timestamp("2026-08-01"), "efficiency"] == pytest.approx(200 / 140)
    assert eff.loc[pd.Timestamp("2026-10-01"), "efficiency"] == pytest.approx(180 / 144)
    assert eff["n_runs"].tolist() == [1, 1]


def test_best_efforts_ignore_other_sports(cfg):
    ten = trends.best_efforts(cfg=cfg).query("distance_m == 10000")
    assert ten["time_s"].tolist() == [2700]          # the 1100 s ride effort is not a run
    assert ten["is_record"].tolist() == [True]


def test_easy_runs_is_the_efficiency_filter(cfg):
    easy = trends.easy_runs(runs(cfg=cfg), cfg)
    assert sorted(easy["activity_id"]) == sorted([STEADY, OLD])     # in band, flat, long enough


def test_shoes_table_and_a_database_without_gear(cfg):
    assert trends.shoes(cfg=cfg).empty                         # the fixture has no Gear table
    import sqlite3
    conn = sqlite3.connect(cfg.strava_db)
    conn.executescript("""
        CREATE TABLE Gear (gearId VARCHAR(255), name VARCHAR(255), isRetired BOOLEAN);
        ALTER TABLE Activity ADD COLUMN gearId VARCHAR(255);
        INSERT INTO Gear VALUES ('g1', 'Road <shoe>', 0), ('g2', 'Old pair', 1), ('g3', 'Bike', 0);
    """)
    conn.execute("UPDATE Activity SET gearId = 'g1' WHERE activityId IN (?, ?)", (STEADY, OLD))
    conn.execute("UPDATE Activity SET gearId = 'g2' WHERE activityId = ?", (RACE,))
    conn.commit()
    conn.close()
    shoes = trends.shoes(cfg=cfg)
    assert list(shoes.columns) == ["name", "km", "runs", "last_used", "retired"]
    assert shoes["name"].tolist() == ["Road <shoe>", "Old pair"]          # in use first; no bike
    assert shoes["km"].tolist() == pytest.approx([17.2, 10.0]) and shoes["runs"].tolist() == [2, 1]
    assert shoes["retired"].tolist() == [False, True]


def test_shoe_status_has_a_check_band_before_the_limit():
    assert [trends.shoe_status(km, False) for km in (699, 700, 999, 1000)] == [
        "", "check (700 km)", "check (700 km)", "over 1000 km"]
    assert trends.shoe_status(1200, True) == "retired"
