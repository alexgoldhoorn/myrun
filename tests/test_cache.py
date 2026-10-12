"""The pages' result cache: computed once, and again as soon as an input changes."""
import os
from dataclasses import replace

import pandas as pd
import pytest

from myrun import metrics
from myrun.ui import common
from tests.fixture import TODAY, write_plan, write_wellness


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


@pytest.mark.parametrize("field", ["plan_csv", "wellness_parquet", "strava_db"])
def test_a_changed_input_file_recomputes(cfg, tmp_path, counted, field):
    c = replace(cfg, plan_csv=write_plan(tmp_path / "plan.csv"),
                wellness_parquet=write_wellness(tmp_path / "w.parquet"))
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
