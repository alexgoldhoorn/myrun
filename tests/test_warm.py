"""The warm-up: results are computed in the background, so the first visitor does not wait."""
import threading
from dataclasses import replace

import pytest

from myrun.ui import common, warm
from tests.fixture import write_plan


def _break_everything(monkeypatch):
    def boom(*args):
        raise AssertionError("computed again: the warm-up did not cover this call")

    for name in list(common.COMPUTE):
        monkeypatch.setitem(common.COMPUTE, name, boom)


def test_after_a_warm_up_the_pages_default_calls_are_cache_hits(cfg, tmp_path, monkeypatch):
    c = replace(cfg, plan_csv=write_plan(tmp_path / "plan.csv"))
    report = warm.warm(c)
    assert report["failed"] == []
    _break_everything(monkeypatch)
    for call in (("input_states",), ("plan",), ("headline",), ("weekly_load", 12),
                 ("weekly_runs", 12), ("plan_vs_actual",), ("efficiency",), ("volume", "month"),
                 ("best_efforts",), ("hr_settings",), ("intensity_weekly", 12)):
        common.cached(call[0], c, *call[1:])


def test_every_result_is_warmed_unless_it_needs_a_choice_from_the_page():
    warmed = {call[0] for call in warm.WARM}
    assert set(common.COMPUTE) - warmed == {"streams", "laps", "dynamics_trend"}


def test_one_failing_result_does_not_stop_the_rest(cfg, monkeypatch):
    def boom(cfg):
        raise RuntimeError("plan file exploded")

    monkeypatch.setitem(common.COMPUTE, "plan", boom)
    report = warm.warm(cfg)
    assert report["failed"] == ["plan"] and "headline" in report["warmed"]


def test_the_loop_warms_until_stopped_and_survives_a_bad_config(cfg):
    stop, seen = threading.Event(), []

    def load():
        seen.append(1)
        if len(seen) == 1:
            raise RuntimeError("config not readable yet")
        if len(seen) == 3:
            stop.set()
        return cfg

    warm.loop(load, stop, interval_s=0.01)
    assert len(seen) == 3


def test_the_command_line_is_handed_to_streamlit_unchanged():
    assert warm.streamlit_argv(["warm.py", "run", "app/Dashboard.py", "--server.port", "8501"]) == [
        "streamlit", "run", "app/Dashboard.py", "--server.port", "8501"]


def test_a_refreshing_warm_up_recomputes_the_timed_results_and_only_those(cfg, monkeypatch):
    warm.warm(cfg)
    computed = []
    for name in list(common.COMPUTE):
        real = common.COMPUTE[name]
        monkeypatch.setitem(common.COMPUTE, name,
                            lambda *a, name=name, real=real: computed.append(name) or real(*a))
    warm.warm(cfg)
    assert computed == []                                    # a plain warm-up: all hits
    warm.warm(cfg, refresh=True)
    assert sorted(computed) == sorted(common.CLOCKED)
