import pandas as pd
import pytest

from myrun.load import load_status, weekly_load
from tests.fixture import TODAY


def test_load_status(cfg):
    status = load_status(today=TODAY, cfg=cfg)
    assert status["last7"] == 135                 # 40 + 80 + 15; the deleted 500 is excluded
    assert status["avg_week_28"] == pytest.approx(345 / 4)
    assert status["ratio"] == pytest.approx(135 / (345 / 4))
    assert status["label"] == "very high"
    assert status["n_missing"] == 1               # one run without relative effort in 28 days


def test_load_status_without_history(cfg):
    status = load_status(today="2019-01-01", cfg=cfg)
    assert status["ratio"] is None
    assert status["label"] == "no data"
    assert status["last7"] == 0


def test_weekly_load(cfg):
    weekly = weekly_load(4, today=TODAY, cfg=cfg)
    assert weekly["week_start"].tolist() == list(pd.to_datetime(
        ["2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"]))
    assert weekly["effort"].tolist() == [90, 120, 135, 0]
    assert weekly["n_activities"].tolist() == [1, 2, 3, 0]
    assert weekly["n_missing_effort"].tolist() == [0, 1, 0, 0]
