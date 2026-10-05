import dataclasses

import pandas as pd

from myrun.planmatch import plan_vs_actual
from tests.fixture import TODAY, write_plan


def test_week_without_a_plan_shows_actuals_only(cfg):
    week = plan_vs_actual("2026-09-28", today=TODAY, cfg=cfg)
    assert len(week) == 7
    assert week["date"].iloc[0] == pd.Timestamp("2026-09-28")
    assert week["planned"].isna().all()
    by_date = week.set_index("date")
    assert by_date.loc[pd.Timestamp("2026-10-02"), "actual"] == "Run 10.0 km"
    assert by_date.loc[pd.Timestamp("2026-10-03"), "actual"] == "WeightTraining 30 min"
    assert by_date.loc[pd.Timestamp("2026-10-01"), "actual"] is None      # deleted activity
    assert by_date.loc[pd.Timestamp("2026-10-04"), "actual_run_km"] == 7.2


def test_week_with_a_plan(cfg, tmp_path):
    c = dataclasses.replace(cfg, plan_csv=write_plan(tmp_path / "p.csv"))
    by_date = plan_vs_actual("2026-09-28", today=TODAY, cfg=c).set_index("date")
    assert by_date.loc[pd.Timestamp("2026-10-02"), "planned"] == "Intervals 10km"
    assert by_date.loc[pd.Timestamp("2026-10-02"), "planned_km"] == 10.0
    assert by_date.loc[pd.Timestamp("2026-10-04"), "planned_type"] == "easy"
    assert by_date.loc[pd.Timestamp("2026-09-29"), "planned"] is None


def test_default_week_is_the_current_one(cfg):
    week = plan_vs_actual(today=TODAY, cfg=cfg)
    assert week["date"].iloc[0] == pd.Timestamp("2026-10-05")
