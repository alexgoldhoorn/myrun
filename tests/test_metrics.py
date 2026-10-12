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


# ---- second round of cards: VO2max, intensity split, plan adherence, more recovery ----

def _runs(rows):
    """rows: (days ago, km, minutes, vo2max, aerobic TE, anaerobic TE)"""
    return pd.DataFrame({
        "activity_id": [f"r{i}" for i in range(len(rows))],
        "sport": "Run",
        "date": [pd.Timestamp(TODAY) - pd.Timedelta(days=r[0]) for r in rows],
        "distance_km": [float(r[1]) for r in rows],
        "duration_min": [float(r[2]) for r in rows],
        "vo2max": [r[3] for r in rows],
        "aerobic_te": [r[4] for r in rows],
        "anaerobic_te": [r[5] for r in rows],
    })


NOW = pd.Timestamp(TODAY)


def test_vo2max_is_the_latest_value_against_four_weeks_ago():
    runs = _runs([(40, 8, 45, 50.0, 2.5, 0.0), (30, 8, 45, 51.0, 2.5, 0.0),
                  (10, 8, 45, None, 2.5, 0.0), (3, 8, 45, 52.0, 2.5, 0.0),
                  (1, 8, 45, None, 2.5, 0.0)])
    card = metrics.vo2max_card(runs, NOW)
    assert (card.key, card.label, card.unit) == ("vo2max", "VO2max", "score")
    assert card.value == 52.0 and card.previous == 51.0
    assert card.tone == "good" and card.note == "Garmin estimate, vs 4 weeks ago"
    assert card.series == (50.0, 51.0, 52.0)


def test_vo2max_without_a_recent_value_says_why_and_without_the_column_is_absent():
    old = _runs([(40, 8, 45, 50.0, 2.5, 0.0), (2, 8, 45, None, 2.5, 0.0)])
    card = metrics.vo2max_card(old, NOW)
    assert card.value is None and card.note == "no VO2max value in the last 4 weeks"
    assert metrics.vo2max_card(old.drop(columns="vo2max"), NOW) is None


def test_intensity_split_by_training_effect():
    runs = _runs([(2, 10, 60, None, 2.5, 0.0),        # easy
                  (5, 6, 30, None, 3.2, 0.5),         # steady: aerobic effect 3 or more
                  (9, 3, 10, None, 2.0, 2.5),         # hard: anaerobic effect 2 or more
                  (12, 5, 99, None, None, None),      # no training effect: left out
                  (35, 10, 50, None, 2.0, 0.0), (40, 10, 50, None, 4.5, 0.0)])
    card = metrics.intensity_card(runs, NOW)
    assert (card.key, card.unit) == ("easy_share", "share")
    assert card.value == pytest.approx(60.0) and card.previous == pytest.approx(50.0)
    assert card.detail == "30 % steady, 10 % hard"
    assert card.note == "of running time, vs previous 4 weeks"
    assert card.tone == "neutral"
    assert metrics.intensity_card(runs.drop(columns="aerobic_te"), NOW) is None
    assert metrics.intensity_card(runs[runs["date"] < NOW - pd.Timedelta(days=30)], NOW).value is None


def test_intensity_weekly_table():
    runs = _runs([(0, 10, 60, None, 2.5, 0.0), (0, 6, 30, None, 3.2, 0.5), (7, 3, 10, None, 2.0, 2.5)])
    weekly = metrics.intensity_weekly(4, activities=runs, today=TODAY)
    assert list(weekly.columns) == ["week_start", "easy_min", "steady_min", "hard_min"]
    assert len(weekly) == 4
    assert weekly.iloc[-1][["easy_min", "steady_min", "hard_min"]].tolist() == [60.0, 30.0, 0.0]
    assert weekly.iloc[-2]["hard_min"] == 10.0


def _plan(rows):
    return pd.DataFrame({"date": [NOW - pd.Timedelta(days=d) for d, _, _ in rows],
                         "type": [t for _, t, _ in rows],
                         "distance_km": [km for _, _, km in rows]})


def test_plan_adherence_is_done_over_planned_through_yesterday():
    plan = _plan([(0, "easy", 99.0),                  # today: not due yet
                  (2, "easy", 10.0), (5, "long", 20.0), (9, "rest", None), (20, "tempo", 10.0),
                  (30, "easy", 10.0), (33, "strength", None)])
    runs = _runs([(0, 5, 30, None, None, None), (2, 10, 60, None, None, None),
                  (5, 15, 90, None, None, None), (21, 5, 30, None, None, None),
                  (30, 12, 70, None, None, None)])
    card = metrics.adherence_card(runs, plan, NOW)
    assert (card.key, card.unit) == ("plan_done", "share")
    assert card.value == pytest.approx(75.0)          # 30 of 40 km
    assert card.previous == pytest.approx(120.0)      # 12 of 10 km
    assert card.detail == "30.0 of 40.0 km"
    assert card.note == "last 4 weeks to yesterday, vs the 4 before"


def test_plan_adherence_without_planned_distances_says_why():
    card = metrics.adherence_card(_runs([(2, 10, 60, None, None, None)]),
                                  _plan([(2, "easy", None)]), NOW)
    assert card.value is None and card.note == "no planned distances in the last 4 weeks"
    assert metrics.adherence_card(_runs([]), None, NOW) is None


def test_body_battery_and_stress_join_the_recovery_row(cfg, tmp_path):
    path = tmp_path / "w.parquet"
    dates = pd.date_range(end=pd.Timestamp(TODAY), periods=30)
    pd.DataFrame({"date": dates, "readiness": 70.0, "body_battery": [80.0] * 29 + [60.0],
                  "stress": [30.0] * 29 + [40.0]}).to_parquet(path)
    recovery = by_key(metrics.headline(today=TODAY, cfg=replace(cfg, wellness_parquet=path))["recovery"])
    assert list(recovery) == ["readiness", "body_battery", "stress"]
    assert recovery["body_battery"].label == "Body battery" and recovery["body_battery"].tone == "bad"
    assert recovery["stress"].label == "Stress" and recovery["stress"].tone == "bad"   # higher is worse


def test_headline_places_the_new_cards(cfg, tmp_path):
    c = replace(cfg, plan_csv=write_plan(tmp_path / "plan.csv"))
    numbers = metrics.headline(today=TODAY, cfg=c)
    assert [m.key for m in numbers["volume"]][-1] == "plan_done"
    assert "vo2max" not in [m.key for m in numbers["fitness"]]      # no Garmin input here
    assert "plan_done" not in [m.key for m in metrics.headline(today=TODAY, cfg=cfg)["volume"]]
