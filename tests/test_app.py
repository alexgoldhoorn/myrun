"""Smoke tests: every page renders, in every input configuration, without an exception."""

import os
from datetime import date
from pathlib import Path

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from tests.fixture import (RACE_COLUMNS, build_fixture, write_garmin_csv, write_plan, write_races,
                           write_wellness)

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["Dashboard.py", "pages/1_Trends.py", "pages/2_Activity.py", "pages/3_Explore.py"]


def write_config(tmp_path, db, **inputs) -> Path:
    config = {"strava_db": str(db), "cache_dir": str(tmp_path / "cache"),
              "links": {"statistics_for_strava_url": "http://localhost:8085"}}
    if inputs:
        config["inputs"] = {k: str(v) for k, v in inputs.items()}
        config["race_log_columns"] = RACE_COLUMNS
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def run_page(page: str) -> AppTest:
    at = AppTest.from_file(str(ROOT / "app" / page), default_timeout=60)
    at.run()
    return at


def _text(at: AppTest) -> str:
    parts = []
    for kind in ("title", "header", "subheader", "markdown", "caption", "info", "warning", "error"):
        parts += [str(e.value) for e in getattr(at, kind)]
    return "\n".join(parts)


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    db = build_fixture(tmp_path / "strava.db", date.today())
    monkeypatch.setenv("MYRUN_CONFIG", str(write_config(tmp_path, db)))


@pytest.fixture
def everything(tmp_path, monkeypatch):
    today = date.today()
    db = build_fixture(tmp_path / "strava.db", today)
    config = write_config(
        tmp_path, db,
        wellness_parquet=write_wellness(tmp_path / "w.parquet", today),
        plan_csv=write_plan(tmp_path / "plan.csv", today),
        race_log_csv=write_races(tmp_path / "races.csv", today),
        garmin_activities=write_garmin_csv(tmp_path / "g.csv", today),
    )
    monkeypatch.setenv("MYRUN_CONFIG", str(config))


@pytest.fixture
def empty_db(tmp_path, monkeypatch):
    db = build_fixture(tmp_path / "strava.db", date.today(), empty=True)
    monkeypatch.setenv("MYRUN_CONFIG", str(write_config(tmp_path, db)))


@pytest.fixture
def broken_inputs(tmp_path, monkeypatch):
    db = build_fixture(tmp_path / "strava.db", date.today())
    junk = tmp_path / "junk.parquet"
    junk.write_bytes(b"nope")
    config = write_config(tmp_path, db, wellness_parquet=junk, plan_csv=tmp_path / "absent.csv",
                          garmin_activities=junk)
    monkeypatch.setenv("MYRUN_CONFIG", str(config))


@pytest.mark.parametrize("page", PAGES)
def test_renders_with_only_the_database(baseline, page):
    at = run_page(page)
    assert not at.exception
    assert not at.error


@pytest.mark.parametrize("page", PAGES)
def test_renders_with_every_optional_input(everything, page):
    at = run_page(page)
    assert not at.exception
    assert not at.warning


@pytest.mark.parametrize("page", PAGES)
def test_renders_with_an_empty_database(empty_db, page):
    at = run_page(page)
    assert not at.exception
    assert "No activities" in _text(at)


@pytest.mark.parametrize("page", PAGES)
def test_broken_optional_inputs_show_notices_not_exceptions(broken_inputs, page):
    at = run_page(page)
    assert not at.exception
    warnings = "\n".join(str(w.value) for w in at.warning)
    assert "plan" in warnings and "garmin_activities" in warnings


@pytest.mark.parametrize("page", PAGES)
def test_stale_database_shows_a_banner(baseline, page, tmp_path):
    import os
    import time

    old = time.time() - 40 * 3600
    os.utime(tmp_path / "strava.db", (old, old))
    at = run_page(page)
    assert not at.exception
    assert any("out of date" in str(e.value) for e in at.error)


@pytest.mark.parametrize("page", PAGES)
def test_stale_garmin_file_is_named_on_every_page(everything, page, tmp_path):
    import os
    import time

    old = time.time() - 200 * 3600
    os.utime(tmp_path / "g.csv", (old, old))
    at = run_page(page)
    assert not at.exception
    assert any("garmin_activities" in str(w.value) and "200" in str(w.value) for w in at.warning)


def test_stale_wellness_hides_recovery_values(everything, tmp_path):
    import os
    import time

    old = time.time() - 50 * 3600
    os.utime(tmp_path / "w.parquet", (old, old))
    at = run_page("Dashboard.py")
    assert not at.exception
    assert any("wellness" in str(w.value) for w in at.warning)
    assert "Values for" not in _text(at)


def test_missing_database_is_one_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MYRUN_CONFIG", str(write_config(tmp_path, tmp_path / "absent.db")))
    at = run_page("Dashboard.py")
    assert not at.exception
    assert len(at.error) == 1 and "not found" in at.error[0].value


def test_dashboard_content_baseline(baseline):
    text = _text(run_page("Dashboard.py"))
    for label in ("This week", "Last 4 weeks", "Year to date", "Load, 7 days vs 4 weeks",
                  "Easy pace", "Longest run, 4 weeks", "Runs per week", "Recent runs"):
        assert label in text
    assert "Next race" not in text and "Recovery" not in text       # hidden, not configured


def test_dashboard_content_with_inputs(everything):
    text = _text(run_page("Dashboard.py"))
    assert "Next race" in text and "Trail Race 23km" in text
    assert "Recovery" in text and "Readiness" in text and "Values for" in text
    assert "connect.garmin.com" not in text                        # links live in the table


def test_dashboard_names_a_broken_input(broken_inputs):
    at = run_page("Dashboard.py")
    warnings = "\n".join(str(w.value) for w in at.warning)
    assert "wellness" in warnings and "plan" in warnings


def test_dashboard_opens_a_run_on_the_activity_page(baseline):
    at = run_page("Dashboard.py")
    assert not at.exception and len(at.dataframe) >= 2             # this week, recent runs


def test_trends_page_content(everything):
    text = _text(run_page("pages/1_Trends.py"))
    for heading in ("Aerobic efficiency", "Volume", "Best efforts", "Races", "Wellness"):
        assert heading in text


def test_trends_page_hides_optional_sections(baseline):
    text = _text(run_page("pages/1_Trends.py"))
    assert "Aerobic efficiency" in text
    assert "Races" not in text and "Wellness" not in text


def test_activity_page_shows_the_newest_activity_with_streams(baseline):
    at = run_page("pages/2_Activity.py")
    text = _text(at)
    assert "HR drift" in text and "Time in HR zones" in text and "Laps" in text
    assert any("strava.com/activities/1" in str(b.url) for b in at.get("link_button"))


def test_activity_page_handles_an_activity_without_stream_data(baseline):
    at = run_page("pages/2_Activity.py")
    options = at.selectbox[0].options
    target = next(o for o in options if "5.0 km" in o)        # the run with no stream rows
    at.selectbox[0].select(target).run()
    assert not at.exception
    assert "no stream data" in _text(at)


def test_explore_page_per_km_level(baseline):
    at = run_page("pages/3_Explore.py")
    at.radio[0].set_value("per km").run()
    assert not at.exception
    group = next(s for s in at.selectbox if s.label == "Group by")
    assert "Climb or descent" in group.options


def test_explore_page_offers_dynamics_only_with_the_garmin_input(baseline):
    y = next(s for s in run_page("pages/3_Explore.py").selectbox if s.label == "Y")
    assert "ground_contact_ms" not in y.options


def test_explore_page_offers_dynamics_with_the_garmin_input(everything):
    y = next(s for s in run_page("pages/3_Explore.py").selectbox if s.label == "Y")
    assert "ground_contact_ms" in y.options


def test_pages_say_where_the_hr_zones_come_from(baseline):
    assert "observed" in _text(run_page("pages/2_Activity.py"))
    assert "observed" in _text(run_page("pages/1_Trends.py"))


def test_activity_page_shows_pace_as_minutes_and_seconds(baseline):
    at = run_page("pages/2_Activity.py")
    paces = [m.value for m in at.metric if m.label == "Pace"]
    assert paces == ["5:33 /km"]                          # 40 min over 7.2 km


def test_activity_page_shows_running_dynamics_with_the_feed(everything):
    at = run_page("pages/2_Activity.py")
    assert "Running dynamics" in _text(at)
    assert "Ground contact" in _text(at) and "250 ms" in _text(at)
    assert any("connect.garmin.com/modern/activity/111" in str(b.url)
               for b in at.get("link_button"))


def test_activity_page_hides_running_dynamics_without_the_feed(baseline):
    assert "Running dynamics" not in _text(run_page("pages/2_Activity.py"))


def test_trends_page_shows_running_dynamics_with_the_feed(everything):
    assert "Running dynamics" in _text(run_page("pages/1_Trends.py"))


def test_trends_page_hides_running_dynamics_without_the_feed(baseline):
    assert "Running dynamics" not in _text(run_page("pages/1_Trends.py"))


def test_dashboard_shows_a_changed_plan_without_a_restart(everything, tmp_path):
    assert "Trail Race 23km" in _text(run_page("Dashboard.py"))
    plan = tmp_path / "plan.csv"
    plan.write_text(plan.read_text().replace("Trail Race 23km", "Night Race 30km"))
    stamp = plan.stat().st_mtime + 60
    os.utime(plan, (stamp, stamp))
    text = _text(run_page("Dashboard.py"))
    assert "Night Race 30km" in text and "Trail Race 23km" not in text


def test_dashboard_shows_the_second_round_of_cards(everything):
    text = _text(run_page("Dashboard.py"))
    for label in ("Plan done", "Easy share", "VO2max"):
        assert label in text


def test_dashboard_hides_cards_whose_input_is_not_configured(baseline):
    text = _text(run_page("Dashboard.py"))
    for label in ("Plan done", "Easy share", "VO2max"):
        assert label not in text


def test_trends_page_shows_vo2max_and_intensity_with_the_feed(everything):
    text = _text(run_page("pages/1_Trends.py"))
    assert "VO2max" in text and "Intensity" in text


def test_trends_page_hides_vo2max_and_intensity_without_the_feed(baseline):
    text = _text(run_page("pages/1_Trends.py"))
    assert "VO2max" not in text and "Intensity" not in text
