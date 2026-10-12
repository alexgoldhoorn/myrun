import pytest

from myrun.config import Config
from tests.fixture import TODAY, build_fixture


@pytest.fixture
def db_path(tmp_path):
    return build_fixture(tmp_path / "strava.db", TODAY)


@pytest.fixture
def cfg(tmp_path, db_path):
    return Config(strava_db=db_path, cache_dir=tmp_path / "cache",
                  hr_zone_upper_bounds=(125, 145, 160, 172), easy_hr_band=(125, 148))
