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
PAGES = ["views/dashboard.py", "views/trends.py", "views/activity.py", "views/explore.py"]


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
    at = run_page("views/dashboard.py")
    assert not at.exception
    assert any("wellness" in str(w.value) for w in at.warning)
    assert "Values for" not in _text(at)


def test_missing_database_is_one_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MYRUN_CONFIG", str(write_config(tmp_path, tmp_path / "absent.db")))
    at = run_page("views/dashboard.py")
    assert not at.exception
    assert len(at.error) == 1 and "not found" in at.error[0].value


def test_dashboard_content_baseline(baseline):
    text = _text(run_page("views/dashboard.py"))
    for label in ("This week", "Last 4 weeks", "Year to date", "Load, 7 days vs 4 weeks",
                  "Easy pace", "Longest run, 4 weeks", "Runs per week", "Recent runs"):
        assert label in text
    assert "Next race" not in text and "Recovery" not in text       # hidden, not configured


def test_dashboard_content_with_inputs(everything):
    text = _text(run_page("views/dashboard.py"))
    assert "Next race" in text and "Trail Race 23km" in text
    assert "Recovery" in text and "Readiness" in text and "Values for" in text
    assert "connect.garmin.com" not in text                        # links live in the table


def test_dashboard_names_a_broken_input(broken_inputs):
    at = run_page("views/dashboard.py")
    warnings = "\n".join(str(w.value) for w in at.warning)
    assert "wellness" in warnings and "plan" in warnings


def test_dashboard_opens_a_run_on_the_activity_page(baseline):
    at = run_page("views/dashboard.py")
    assert not at.exception and len(at.dataframe) >= 2             # this week, recent runs


def test_trends_page_content(everything):
    text = _text(run_page("views/trends.py"))
    for heading in ("Aerobic efficiency", "Volume", "Best efforts", "Races", "Wellness",
                    "Like for like, year on year", "heart rate by pace band",
                    "Training mix per year"):
        assert heading in text


def test_trends_page_hides_optional_sections(baseline):
    text = _text(run_page("views/trends.py"))
    assert "Aerobic efficiency" in text
    assert "Races" not in text and "Wellness" not in text


def test_activity_page_shows_the_newest_activity_with_streams(baseline):
    at = run_page("views/activity.py")
    text = _text(at)
    assert "HR drift" in text and "Time in HR zones" in text and "Laps" in text
    assert 'class="mr-link" href="https://www.strava.com/activities/1"' in _text(at)


def test_activity_page_handles_an_activity_without_stream_data(baseline):
    at = run_page("views/activity.py")
    options = at.selectbox[0].options
    target = next(o for o in options if "5.0 km" in o)        # the run with no stream rows
    at.selectbox[0].select(target).run()
    assert not at.exception
    assert "no stream data" in _text(at)


def test_explore_page_per_km_level(baseline):
    at = run_page("views/explore.py")
    at.radio[0].set_value("per km").run()
    assert not at.exception
    group = next(s for s in at.selectbox if s.label == "Group by")
    assert "Climb or descent" in group.options


def test_explore_page_offers_dynamics_only_with_the_garmin_input(baseline):
    y = next(s for s in run_page("views/explore.py").selectbox if s.label == "Y")
    assert "Ground contact (ms)" not in y.options


def test_explore_page_offers_dynamics_with_the_garmin_input(everything):
    y = next(s for s in run_page("views/explore.py").selectbox if s.label == "Y")
    assert "Ground contact (ms)" in y.options


def test_pages_say_where_the_hr_zones_come_from(baseline):
    assert "observed" in _text(run_page("views/activity.py"))
    assert "observed" in _text(run_page("views/trends.py"))


def test_activity_page_shows_pace_as_minutes_and_seconds(baseline):
    at = run_page("views/activity.py")
    assert ('<div class="mr-label">Pace</div><div class="mr-value">5:33 /km</div>'
            in _text(at))                                  # 40 min over 7.2 km


def test_activity_page_shows_running_dynamics_with_the_feed(everything):
    at = run_page("views/activity.py")
    assert "Running dynamics" in _text(at)
    assert "Ground contact" in _text(at) and "250 ms" in _text(at)
    assert "connect.garmin.com/modern/activity/111" in _text(at)


def test_activity_page_hides_running_dynamics_without_the_feed(baseline):
    assert "Running dynamics" not in _text(run_page("views/activity.py"))


def test_trends_page_shows_running_dynamics_with_the_feed(everything):
    assert "Running dynamics" in _text(run_page("views/trends.py"))


def test_trends_page_hides_running_dynamics_without_the_feed(baseline):
    assert "Running dynamics" not in _text(run_page("views/trends.py"))


def test_dashboard_shows_a_changed_plan_without_a_restart(everything, tmp_path):
    assert "Trail Race 23km" in _text(run_page("views/dashboard.py"))
    plan = tmp_path / "plan.csv"
    plan.write_text(plan.read_text().replace("Trail Race 23km", "Night Race 30km"))
    stamp = plan.stat().st_mtime + 60
    os.utime(plan, (stamp, stamp))
    text = _text(run_page("views/dashboard.py"))
    assert "Night Race 30km" in text and "Trail Race 23km" not in text


def test_dashboard_shows_the_second_round_of_cards(everything):
    text = _text(run_page("views/dashboard.py"))
    for label in ("Plan done", "Easy share", "VO2max"):
        assert label in text


def test_dashboard_hides_cards_whose_input_is_not_configured(baseline):
    text = _text(run_page("views/dashboard.py"))
    for label in ("Plan done", "Easy share", "VO2max"):
        assert label not in text


def test_trends_page_shows_vo2max_and_intensity_with_the_feed(everything):
    text = _text(run_page("views/trends.py"))
    assert "VO2max" in text and "Intensity" in text


def test_trends_page_hides_vo2max_and_intensity_without_the_feed(baseline):
    text = _text(run_page("views/trends.py"))
    assert "VO2max" not in text and "Intensity" not in text


def test_dashboard_third_round_sections(everything):
    text = _text(run_page("views/dashboard.py"))
    for label in ("Weeks in a row", "Garmin load", "Easy pace", "Last 12 weeks, by week.", "Training days",
                  "Race build-up"):
        assert label in text


def test_dashboard_third_round_without_optional_inputs(baseline):
    text = _text(run_page("views/dashboard.py"))
    assert "Weeks in a row" in text and "Training days" in text
    assert "Garmin load" not in text and "Race build-up" not in text


def test_explore_builds_its_chart_once_per_choice(baseline, monkeypatch):
    from myrun.ui import charts
    built, real = [], charts.explore_figure

    def counting(*args, **kwargs):
        built.append(args[1:3])
        return real(*args, **kwargs)

    monkeypatch.setattr(charts, "explore_figure", counting)
    at = run_page("views/explore.py")
    at.run()                                         # a rerun with the same choices
    assert not at.exception and len(built) == 1
    at.selectbox[1].set_value("distance_km").run()   # another Y axis is another chart
    assert not at.exception and len(built) == 2
    assert "rows have both values" in _text(at)


def test_entrypoint_routes_to_the_dashboard(baseline):
    at = run_page("Dashboard.py")
    assert not at.exception
    assert "Dashboard" in [t.value for t in at.title]
    # AppTest exposes no page_link element; each renders as an unknown element in the phone nav row
    nav = next(e for e in at.main if getattr(e, "key", None) == "mr-phone-nav")
    assert len(nav.children) == 4


def test_activity_picker_names_the_session_and_the_date(baseline):
    options = run_page("views/activity.py").selectbox[0].options
    assert options and all(" · " in o and o.endswith(" km") for o in options)
    assert not any(o[:4].isdigit() for o in options)            # no ISO timestamp first


def test_activity_laps_count_from_one(baseline):
    at = run_page("views/activity.py")
    laps = next(d.value for d in at.dataframe if "lap" in d.value.columns)
    assert laps["lap"].min() == 1


def test_footer_uses_human_input_names(baseline):
    text = _text(run_page("views/dashboard.py"))
    assert "Strava DB: ok" in text and "strava_db" not in text


def test_dashboard_puts_the_row_hint_above_the_recent_runs(baseline):
    at = run_page("views/dashboard.py")
    captions = [c.value for c in at.caption]
    assert "Select a row to open it on the Activity page." in captions


def test_activity_laps_numbered_from_zero_display_from_one(baseline, monkeypatch):
    import pandas as pd
    from myrun import streams
    monkeypatch.setattr(streams, "activity_laps", lambda activity_id, cfg=None: pd.DataFrame({
        "lap": [0, 1], "name": ["a", "b"], "distance_km": [1.0, 1.0], "duration_s": [300, 310],
        "pace_min_km": [5.0, 5.2], "avg_hr": [140, 145], "elev_diff_m": [1.0, 2.0]}))
    at = run_page("views/activity.py")
    laps = next(d.value for d in at.dataframe if "lap" in d.value.columns)
    assert laps["lap"].tolist() == [1, 2]
