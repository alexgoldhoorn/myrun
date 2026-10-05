"""Smoke tests: every page renders, in every input configuration, without an exception."""

from datetime import date
from pathlib import Path

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from tests.fixture import (RACE_COLUMNS, build_fixture, write_garmin, write_plan, write_races,
                           write_wellness)

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["Now.py"]


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
        garmin_activities_parquet=write_garmin(tmp_path / "g.parquet", today),
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
                          garmin_activities_parquet=junk)
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


def test_missing_database_is_one_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MYRUN_CONFIG", str(write_config(tmp_path, tmp_path / "absent.db")))
    at = run_page("Now.py")
    assert not at.exception
    assert len(at.error) == 1 and "not found" in at.error[0].value


def test_now_page_content_baseline(baseline):
    text = _text(run_page("Now.py"))
    assert "Load" in text and "Last 7 days" in text
    assert "Next race" not in text and "Recovery" not in text       # hidden, not configured


def test_now_page_content_with_inputs(everything):
    text = _text(run_page("Now.py"))
    assert "Next race" in text and "Trail Race 23km" in text
    assert "Recovery" in text


def test_now_page_names_a_broken_input(broken_inputs):
    at = run_page("Now.py")
    warnings = "\n".join(str(w.value) for w in at.warning)
    assert "wellness" in warnings and "plan" in warnings
