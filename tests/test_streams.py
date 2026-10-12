import numpy as np
import pandas as pd
import pytest

from myrun import streams
from tests.fixture import GYM, NOEFFORT, RACE, STEADY


def test_streams_shape_and_units(cfg):
    s = streams.activity_streams(STEADY, cfg=cfg)
    assert list(s.columns) == streams.COLUMNS
    assert len(s) == 2400
    assert s["hr"].iloc[0] == 140 and s["hr"].iloc[-1] == 147
    assert s["cadence_spm"].iloc[0] == 170
    assert s["pace_min_km"].iloc[0] == pytest.approx(1000 / 3.0 / 60)
    assert s["distance_m"].iloc[-1] == pytest.approx(7197.0)


def test_no_streams_gives_an_empty_frame(cfg):
    for activity_id in (NOEFFORT, GYM, "activity-does-not-exist"):
        s = streams.activity_streams(activity_id, cfg=cfg)
        assert s.empty
        assert list(s.columns) == streams.COLUMNS


def test_a_stream_of_the_wrong_length_is_dropped_not_fatal(cfg):
    s = streams.activity_streams(RACE, cfg=cfg)
    assert len(s) == 10
    assert s["hr"].tolist() == [165] * 10
    assert s["speed_ms"].isna().all()
    assert s["pace_min_km"].isna().all()
    assert streams.hr_drift(RACE, cfg=cfg) is None


def test_zone_seconds(cfg):
    zones = streams.hr_zones(STEADY, cfg=cfg)     # default bounds 125, 145, 160, 172
    assert zones["zone"].tolist() == [1, 2, 3, 4, 5]
    assert zones["seconds"].tolist() == [0, 1200, 1200, 0, 0]
    assert zones["pct"].tolist() == [0, 50, 50, 0, 0]
    assert zones["lower"].tolist() == [0, 126, 146, 161, 173]


def test_zone_seconds_ignores_pauses_and_zero_hr():
    s = pd.DataFrame({"time_s": [0, 1, 2, 600, 601], "hr": [130, 130, 0, 150, 150]})
    zones = streams.zone_seconds(s, (125, 145, 160, 172))
    # the 598 s gap after t=2 is capped at 10 s, and that sample has no HR anyway
    assert zones.set_index("zone")["seconds"].to_dict() == {1: 0, 2: 2, 3: 2, 4: 0, 5: 0}


def test_zone_seconds_with_no_hr_is_all_zero():
    empty = pd.DataFrame(columns=streams.COLUMNS)
    zones = streams.zone_seconds(empty, (125, 145, 160, 172))
    assert zones["seconds"].tolist() == [0, 0, 0, 0, 0]
    assert zones["pct"].tolist() == [0, 0, 0, 0, 0]


def test_drift(cfg):
    assert streams.hr_drift(STEADY, cfg=cfg) == pytest.approx((1 - 140 / 147) * 100)


def test_drift_needs_thirty_minutes():
    n = 1000
    s = pd.DataFrame({"time_s": range(n), "hr": [140] * n, "speed_ms": [3.0] * n,
                      "moving": [True] * n})
    assert streams.drift_pct(s) is None
    assert streams.drift_pct(s, min_minutes=10) == pytest.approx(0.0)


def test_laps(cfg):
    laps = streams.activity_laps(STEADY, cfg=cfg)
    assert laps["lap"].tolist() == [1, 2]
    assert laps["avg_hr"].tolist() == [140, 147]
    assert laps["distance_km"].tolist() == [3.6, 3.6]
    assert laps["pace_min_km"].iloc[0] == pytest.approx(1200 / 60 / 3.6)
    assert streams.activity_laps(GYM, cfg=cfg).empty


def test_hr_zones_without_any_heart_rate_settings_is_empty(tmp_path):
    from myrun.config import Config
    from tests.fixture import TODAY, build_fixture

    cfg = Config(strava_db=build_fixture(tmp_path / "e.db", TODAY, empty=True),
                 cache_dir=tmp_path / "c")
    assert streams.hr_zones("activity-1", cfg=cfg).empty
