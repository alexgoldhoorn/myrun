import pytest

from myrun.config import ConfigError, load_config


def _write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return p


def test_minimal_config_gets_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, "strava_db: /data/strava.db\n"))
    assert str(cfg.strava_db) == "/data/strava.db"
    assert cfg.wellness_parquet is None
    assert cfg.load_bands == (0.8, 1.3, 1.5)
    assert cfg.mixed_hilliness_m_per_km == 15.0
    assert cfg.stale_hours == 36.0


def test_full_config_is_read(tmp_path):
    cfg = load_config(_write(tmp_path, """
strava_db: /data/strava.db
cache_dir: /tmp/c
inputs:
  wellness_parquet: /data/w.parquet
  plan_csv: /data/plan.csv
  race_log_csv: /data/races.csv
  garmin_activities_parquet: /data/g.parquet
race_log_columns: {name: "name ", date: date}
race_log_date_format: "%Y-%m-%d"
links:
  statistics_for_strava_url: http://localhost:8085/
hr:
  zone_upper_bounds: [120, 140, 155, 170]
  easy_band: [120, 145]
thresholds:
  mixed_hilliness_m_per_km: 12
  stale_hours: 48
"""))
    assert str(cfg.plan_csv) == "/data/plan.csv"
    assert cfg.race_log_columns == {"name": "name ", "date": "date"}
    assert cfg.sfs_url == "http://localhost:8085"
    assert cfg.hr_zone_upper_bounds == (120, 140, 155, 170)
    assert cfg.easy_hr_band == (120, 145)
    assert cfg.mixed_hilliness_m_per_km == 12.0
    assert cfg.stale_hours == 48.0


def test_missing_file_and_missing_strava_db(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")
    with pytest.raises(ConfigError, match="strava_db"):
        load_config(_write(tmp_path, "cache_dir: /tmp/c\n"))


@pytest.mark.parametrize("text, key", [
    ("strava_db: /d.db\nthreshholds: {stale_hours: 1}\n", "threshholds"),
    ("strava_db: /d.db\nthresholds: {stale_hrs: 1}\n", "stale_hrs"),
    ("strava_db: /d.db\ninputs: {plan: /p.csv}\n", "plan"),
])
def test_unknown_key_is_an_error_naming_the_key(tmp_path, text, key):
    with pytest.raises(ConfigError, match=key):
        load_config(_write(tmp_path, text))


def test_env_var_selects_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MYRUN_CONFIG", str(_write(tmp_path, "strava_db: /env.db\n")))
    assert str(load_config().strava_db) == "/env.db"
