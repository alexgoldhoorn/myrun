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
