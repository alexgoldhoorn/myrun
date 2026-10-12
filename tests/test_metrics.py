from dataclasses import replace

import pandas as pd
import pytest

from myrun import activities, metrics
from tests.fixture import TODAY, write_plan, write_wellness


def by_key(cards):
    return {c.key: c for c in cards}


def test_four_week_cards(cfg):
    volume = by_key(metrics.headline(today=TODAY, cfg=cfg)["volume"])
    assert volume["km_4w"].value == pytest.approx(47.2)       # 7.2 + 10 + 15 + 10 + 5
    assert volume["km_4w"].previous == pytest.approx(10.0)
    assert volume["km_4w"].note == "vs previous 4 weeks"
    assert volume["km_4w"].tone == "neutral"                  # more volume is not "good"
    assert volume["elevation_4w"].value == pytest.approx(890)
    assert volume["elevation_4w"].previous == pytest.approx(40)
    assert volume["km_ytd"].value == pytest.approx(57.2)
    assert volume["km_ytd"].previous == pytest.approx(0.0)
    assert len(volume["km_4w"].series) == 12


def test_this_week_compares_the_same_weekdays(cfg):
    friday = "2026-10-02"
    week = by_key(metrics.headline(today=friday, cfg=cfg)["volume"])["km_week"]
    assert week.value == pytest.approx(10.0)                  # Mon 28 Sep to Fri 2 Oct
    assert week.previous == pytest.approx(5.0)                # Mon 21 to Fri 25 Sep
    assert week.note == "vs same days last week"


def test_a_monday_with_no_run_yet_is_zero_not_missing(cfg):
    week = by_key(metrics.headline(today=TODAY, cfg=cfg)["volume"])["km_week"]
    assert week.value == 0.0 and week.previous == 0.0


def test_year_to_date_on_new_years_day_and_leap_day(cfg):
    acts = activities(cfg=cfg)
    first = by_key(metrics.headline(activities=acts, today="2027-01-01", cfg=cfg)["volume"])
    assert first["km_ytd"].value == 0.0
    assert first["km_ytd"].previous == 0.0                    # 1 Jan 2026 alone
    leap = by_key(metrics.headline(activities=acts, today="2028-02-29", cfg=cfg)["volume"])
    assert leap["km_ytd"].value == 0.0 and leap["km_ytd"].previous == 0.0


def test_fitness_cards(cfg):
    fitness = by_key(metrics.headline(today=TODAY, cfg=cfg)["fitness"])
    assert fitness["load_ratio"].value == pytest.approx(135 / (345 / 4))
    assert fitness["load_ratio"].detail == "very high" and fitness["load_ratio"].tone == "bad"
    assert fitness["longest_run"].value == pytest.approx(15.0)
    assert fitness["longest_run"].previous == pytest.approx(10.0)
    assert fitness["runs_per_week"].value == pytest.approx(1.25)
    assert fitness["runs_per_week"].previous == pytest.approx(0.25)
    easy = fitness["easy_pace"]
    assert easy.value == pytest.approx(40 / 7.2)              # the one easy run in 28 days
    assert easy.previous == pytest.approx(5.0)                # the one in the 28 before
    assert easy.unit == "pace" and easy.tone == "bad"         # slower at the same effort
    assert easy.detail == "1 run"


def test_easy_pace_without_qualifying_runs_says_why(cfg):
    fitness = by_key(metrics.headline(today="2019-06-01", cfg=cfg)["fitness"])
    assert fitness["easy_pace"].value is None
    assert fitness["easy_pace"].note == "no easy road runs in the last 4 weeks"
    assert fitness["load_ratio"].value is None and fitness["load_ratio"].detail == "no data"
    assert fitness["longest_run"].value is None


def test_recovery_is_empty_without_the_wellness_input(cfg):
    assert metrics.headline(today=TODAY, cfg=cfg)["recovery"] == []


def test_recovery_cards(cfg, tmp_path):
    c = replace(cfg, wellness_parquet=write_wellness(tmp_path / "w.parquet"))
    recovery = by_key(metrics.headline(today=TODAY, cfg=c)["recovery"])
    assert list(recovery) == ["readiness", "hrv_ms", "resting_hr", "sleep_hours"]
    assert recovery["readiness"].value == 70.0 and recovery["readiness"].previous == 70.0
    assert recovery["readiness"].tone == "neutral"
    assert recovery["sleep_hours"].unit == "hours"
    assert len(recovery["hrv_ms"].series) == 14


def test_recovery_direction_sets_the_tone(cfg, tmp_path):
    path = tmp_path / "w.parquet"
    dates = pd.date_range(end=pd.Timestamp(TODAY), periods=30)
    pd.DataFrame({"date": dates, "readiness": [70.0] * 29 + [40.0], "hrv_ms": [50.0] * 29 + [65.0],
                  "resting_hr": [48.0] * 29 + [58.0], "sleep_hours": 7.0}).to_parquet(path)
    recovery = by_key(metrics.headline(today=TODAY, cfg=replace(cfg, wellness_parquet=path))["recovery"])
    assert recovery["readiness"].tone == "bad"
    assert recovery["hrv_ms"].tone == "good"
    assert recovery["resting_hr"].tone == "bad"               # higher resting HR is worse
    assert recovery["sleep_hours"].tone == "neutral"


def test_old_or_stale_wellness_gives_no_values_and_a_reason(cfg, tmp_path):
    path = write_wellness(tmp_path / "w.parquet", today=pd.Timestamp(TODAY) - pd.Timedelta(days=5))
    recovery = metrics.headline(today=TODAY, cfg=replace(cfg, wellness_parquet=path))["recovery"]
    assert all(c.value is None for c in recovery)
    assert recovery[0].note == "newest value is from Wed 30 Sep"
    import os
    import time
    fresh = write_wellness(tmp_path / "w2.parquet")
    old = time.time() - 50 * 3600
    os.utime(fresh, (old, old))
    stale = metrics.headline(today=TODAY, cfg=replace(cfg, wellness_parquet=fresh))["recovery"]
    assert all(c.value is None for c in stale) and "50 hours" in stale[0].note


def test_weekly_runs_with_and_without_a_plan(cfg, tmp_path):
    weekly = metrics.weekly_runs(4, today=TODAY, cfg=cfg)
    assert weekly["week_start"].tolist() == list(pd.to_datetime(
        ["2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"]))
    assert weekly["run_km"].tolist() == pytest.approx([10.0, 20.0, 17.2, 0.0])
    assert weekly["longest_km"].tolist() == pytest.approx([10.0, 15.0, 10.0, 0.0])
    assert weekly["n_runs"].tolist() == [1, 2, 2, 0]
    assert weekly["planned_km"].isna().all()
    planned = metrics.weekly_runs(4, today=TODAY,
                                  cfg=replace(cfg, plan_csv=write_plan(tmp_path / "plan.csv")))
    assert planned["planned_km"].notna().iloc[-1]             # the fixture plans the current week


def test_a_blank_in_todays_wellness_row_falls_back_to_yesterday(cfg, tmp_path):
    path = tmp_path / "w.parquet"
    dates = pd.date_range(end=pd.Timestamp(TODAY), periods=30)
    pd.DataFrame({"date": dates, "readiness": [70.0] * 28 + [64.0, None],
                  "hrv_ms": [50.0] * 28 + [None, None], "resting_hr": [48.0] * 30,
                  "sleep_hours": 7.0}).to_parquet(path)
    recovery = by_key(metrics.headline(today=TODAY, cfg=replace(cfg, wellness_parquet=path))["recovery"])
    assert recovery["readiness"].value == 64.0                 # yesterday's, today's is blank
    assert recovery["readiness"].note == "Sun 04 Oct, vs 4-week average"
    assert recovery["hrv_ms"].value is None                    # nothing today or yesterday
    assert recovery["hrv_ms"].note == "no value since Sat 03 Oct"
    assert recovery["resting_hr"].note == "vs 4-week average"
