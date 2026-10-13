"""The pages' result cache: computed once, and again as soon as an input changes."""
import os
from dataclasses import replace

import pandas as pd
import pytest
import streamlit as st

from myrun import metrics
from myrun.ui import common
from tests.fixture import (RACE_COLUMNS, STEADY, TODAY, write_garmin_csv, write_plan, write_races,
                           write_wellness)


@pytest.fixture
def counted(monkeypatch):
    calls = []

    def compute(cfg, *args):
        calls.append(args)
        return {"n": len(calls)}

    monkeypatch.setitem(common.COMPUTE, "probe", compute)
    return calls


def _touch(path, seconds):
    stamp = path.stat().st_mtime + seconds
    os.utime(path, (stamp, stamp))


def test_a_result_is_computed_once_per_input_state(cfg, tmp_path, counted):
    c = replace(cfg, plan_csv=write_plan(tmp_path / "plan.csv"),
                wellness_parquet=write_wellness(tmp_path / "w.parquet"))
    assert common.cached("probe", c) == {"n": 1}
    assert common.cached("probe", c) == {"n": 1}
    assert len(counted) == 1


@pytest.mark.parametrize("field", ["plan_csv", "wellness_parquet", "strava_db", "race_log_csv",
                                   "garmin_activities"])
def test_a_changed_input_file_recomputes(cfg, tmp_path, counted, field):
    c = replace(cfg, plan_csv=write_plan(tmp_path / "plan.csv"),
                wellness_parquet=write_wellness(tmp_path / "w.parquet"),
                race_log_csv=write_races(tmp_path / "races.csv"),
                garmin_activities=write_garmin_csv(tmp_path / "garmin.csv"))
    common.cached("probe", c)
    _touch(getattr(c, field), 60)
    assert common.cached("probe", c) == {"n": 2}


def test_a_new_day_recomputes(cfg, counted, monkeypatch):
    common.cached("probe", cfg)
    monkeypatch.setattr(common, "_today", lambda: pd.Timestamp(TODAY) + pd.Timedelta(days=1))
    assert common.cached("probe", cfg) == {"n": 2}


def test_arguments_are_part_of_the_key(cfg, counted):
    assert common.cached("probe", cfg, "week") == {"n": 1}
    assert common.cached("probe", cfg, "month") == {"n": 2}
    assert common.cached("probe", cfg, "week") == {"n": 1}


def test_the_cached_headline_is_the_library_headline(cfg):
    assert common.cached("headline", cfg) == metrics.headline(cfg=cfg)


def test_an_unknown_name_is_an_error(cfg):
    with pytest.raises(KeyError):
        common.cached("nope", cfg)


def test_a_figure_is_built_once_per_name_and_arguments(cfg):
    import plotly.graph_objects as go
    built = []

    def build(title):
        built.append(title)
        return go.Figure(layout={"title": {"text": title}})

    first = common.figure("probe-figure", cfg, lambda: build("a"), "a")
    again = common.figure("probe-figure", cfg, lambda: build("a"), "a")
    other = common.figure("probe-figure", cfg, lambda: build("b"), "b")
    assert built == ["a", "b"]
    assert first.layout.title.text == again.layout.title.text == "a"
    assert other.layout.title.text == "b"


def test_only_results_that_read_the_clock_expire(cfg, counted, monkeypatch):
    """Staleness is judged against the clock, so those results are refreshed on a timer;
    everything else lives until an input file or the day changes."""
    assert common.CLOCKED <= set(common.COMPUTE)
    assert {"input_states", "wellness", "headline"} <= common.CLOCKED
    used = []
    monkeypatch.setattr(common, "_cached_clocked", lambda *a: used.append("clocked"))
    monkeypatch.setattr(common, "_cached", lambda *a: used.append("plain"))
    common.cached("probe", cfg)
    common.cached("headline", cfg)
    assert used == ["plain", "clocked"]


def test_a_timed_result_expires_and_the_rest_do_not(cfg, counted, monkeypatch):
    from streamlit.runtime.caching import cache_utils
    clock = [1000.0]
    monkeypatch.setattr(cache_utils, "TTLCACHE_TIMER", lambda: clock[0])
    st.cache_data.clear()                # a cache picks its clock up when it is created
    monkeypatch.setattr(common, "CLOCKED", common.CLOCKED | {"probe"})
    assert common.cached("probe", cfg) == {"n": 1}
    clock[0] += common.CACHE_TTL_S - 1
    assert common.cached("probe", cfg) == {"n": 1}
    clock[0] += 2
    assert common.cached("probe", cfg) == {"n": 2}
    monkeypatch.setattr(common, "CLOCKED", frozenset())
    assert common.cached("probe", cfg, "untimed") == {"n": 3}
    clock[0] += 10 * common.CACHE_TTL_S
    assert common.cached("probe", cfg, "untimed") == {"n": 3}
    st.cache_data.clear()                # leave no cache on the fake clock behind


def test_the_per_activity_results_are_the_library_results(cfg):
    from myrun import dynamics, streams
    from myrun.config import RUN_SPORTS
    acts = common.load_activities(cfg)
    row = acts.set_index("activity_id").loc[STEADY]
    assert common.cached("activity_dynamics", cfg, STEADY) == dynamics.activity_dynamics(
        row, acts[acts["sport"].isin(RUN_SPORTS)])
    assert common.cached("drift", cfg, STEADY) == streams.drift_pct(
        streams.activity_streams(STEADY, cfg=cfg))


def test_the_race_table_gets_its_garmin_links_from_the_cache(cfg, tmp_path):
    from myrun import links, optional
    c = replace(cfg, race_log_csv=write_races(tmp_path / "races.csv"),
                race_log_columns=RACE_COLUMNS,
                garmin_activities=write_garmin_csv(tmp_path / "garmin.csv"))
    linked = common.cached("races_linked", c)
    expected = links.fill_race_garmin_urls(optional.read_races(c)[0], common.load_activities(c))
    pd.testing.assert_frame_equal(linked, expected)
    assert common.cached("races_linked", cfg) is None          # no race log configured
