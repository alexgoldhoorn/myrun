import dataclasses

import pandas as pd
import pytest

from myrun import hr
from myrun.activities import activities
from myrun.config import Config
from tests.fixture import TODAY, build_fixture


@pytest.fixture
def bare(db_path, tmp_path):
    """A config with no HR values at all, as a new user would have."""
    return Config(strava_db=db_path, cache_dir=tmp_path / "cache")


def test_zones_are_calculated_from_the_observed_maximum(bare):
    settings = hr.hr_settings(bare, today=TODAY)
    # per-run maxima in the last 12 months: 146, 150, 156, 158, 171
    assert settings.max_hr == 171
    assert settings.zone_upper_bounds == (103, 120, 137, 154)     # 60/70/80/90 % of 171
    assert settings.easy_band == (111, 137)                       # 65 to 80 %
    assert "observed" in settings.source and "171" in settings.source


def test_a_configured_maximum_overrides_the_observed_one(bare):
    settings = hr.hr_settings(dataclasses.replace(bare, max_hr=180), today=TODAY)
    assert settings.max_hr == 180
    assert settings.zone_upper_bounds == (108, 126, 144, 162)
    assert "set in the config" in settings.source


def test_configured_zones_and_band_win_over_any_calculation(bare):
    cfg = dataclasses.replace(bare, max_hr=180, hr_zone_upper_bounds=(125, 145, 160, 172),
                              easy_hr_band=(125, 148))
    settings = hr.hr_settings(cfg, today=TODAY)
    assert settings.zone_upper_bounds == (125, 145, 160, 172)
    assert settings.easy_band == (125, 148)
    assert "set in the config" in settings.source


def test_one_spike_does_not_set_the_maximum():
    days = pd.date_range("2026-01-01", periods=300)
    acts = pd.DataFrame({"date": days, "sport": "Run", "max_hr": [170.0] * 299 + [230.0]})
    assert hr.observed_max_hr(acts, today="2026-10-28") == 170


def test_old_runs_are_used_only_when_the_last_year_is_too_thin():
    acts = pd.DataFrame({"date": pd.to_datetime(["2020-01-01"] * 6 + ["2026-09-01"]),
                         "sport": "Run", "max_hr": [190.0] * 6 + [150.0]})
    assert hr.observed_max_hr(acts, today="2026-10-01") == 190


def test_no_heart_rate_data_gives_no_zones(tmp_path):
    cfg = Config(strava_db=build_fixture(tmp_path / "e.db", TODAY, empty=True),
                 cache_dir=tmp_path / "c")
    settings = hr.hr_settings(cfg, today=TODAY)
    assert settings.zone_upper_bounds is None and settings.easy_band is None
    assert "no heart-rate data" in settings.source
    assert activities(cfg=cfg).empty
