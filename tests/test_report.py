from dataclasses import replace

import pytest

from myrun import report
from tests.fixture import TODAY, write_garmin_csv, write_plan, write_wellness


@pytest.fixture
def full(cfg, tmp_path):
    return replace(cfg, plan_csv=write_plan(tmp_path / "plan.csv"),
                   wellness_parquet=write_wellness(tmp_path / "w.parquet"),
                   garmin_activities=write_garmin_csv(tmp_path / "g.csv"))


def test_fitness_has_every_section(full):
    text = report.fitness(12, cfg=full, today=TODAY)
    assert text.startswith("FITNESS TREND")
    for heading in ("VO2max", "Aerobic efficiency", "Resting HR and HRV"):
        assert heading in text
    assert "easy band 125-148 bpm" in text


def test_fitness_without_inputs_says_so_instead_of_zero(cfg):
    text = report.fitness(12, cfg=cfg, today=TODAY)
    assert "no VO2max values" in text
    assert "Resting HR and HRV" in text and "unavailable" in text


def test_race_shows_the_next_race_and_the_weeks(full):
    text = report.race(4, cfg=full, today=TODAY)
    assert "2026-11-01 (27 days): Trail Race 23km, 23.0 km" in text
    assert "Build-up for Trail Race 23km" in text
    assert text.count("\n- 2026-") >= 4          # one line per week, plus the race
    assert "This week, plan against done:" in text


def test_race_without_a_plan(cfg):
    text = report.race(4, cfg=cfg, today=TODAY)
    assert "no training plan" in text
    assert "Last 4 weeks" in text


def test_dashboard_formats_pace_and_share(full):
    text = report.dashboard(cfg=full, today=TODAY)
    assert text.startswith("DASHBOARD")
    assert "/km" in text
    assert "pace" not in text.split("Easy pace:")[1].split("\n")[0].split("(")[0]


def test_status_lists_every_input(full):
    text = report.status(cfg=full)
    for name in ("strava_db", "wellness", "plan", "garmin_activities"):
        assert f"- {name}: " in text


def test_pace_rounds_up_to_the_next_minute():
    assert report._pace(5.999) == "6:00/km"
    assert report._pace(None) == "n/a"


def test_cli_rejects_out_of_range_arguments():
    with pytest.raises(SystemExit):
        report.main(["fitness", "--months", "0"])
