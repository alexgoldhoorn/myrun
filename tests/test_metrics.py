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
    numbers = metrics.headline(today=TODAY, cfg=cfg)
    fitness = by_key(numbers["fitness"] + numbers["volume"])
    assert [m.key for m in numbers["volume"]][-2:] == ["longest_run", "runs_per_week"]
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
    numbers = metrics.headline(today="2019-06-01", cfg=cfg)
    fitness = by_key(numbers["fitness"] + numbers["volume"])
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
                  (30, "easy", 10.0), (33, "strength", None), (40, "rest", None)])
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
                                  _plan([(d, "easy", None) for d in range(1, 10)]), NOW)
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
    assert [m.key for m in numbers["consistency"]] == ["plan_done", "run_streak"]
    assert "vo2max" not in [m.key for m in numbers["fitness"]]      # no Garmin input here
    assert [m.key for m in metrics.headline(today=TODAY, cfg=cfg)["consistency"]] == ["run_streak"]


# ---- third round: Garmin load, heat note, streak, calendar, race readiness, sleep detail ----

def test_garmin_load_card_uses_the_same_bands_as_the_strava_one(cfg):
    acts = _runs([(1, 8, 45, None, None, None), (3, 8, 45, None, None, None),
                  (10, 8, 45, None, None, None), (20, 8, 45, None, None, None)])
    acts["garmin_load"] = [100.0, 100.0, 50.0, 50.0]
    card = metrics.garmin_load_card(acts, NOW, cfg)
    assert card.key == "garmin_load_ratio" and card.unit == "ratio"
    assert card.value == pytest.approx(200 / (300 / 4))       # 2.67: far above the bands
    assert card.detail == "very high" and card.tone == "bad"
    assert metrics.garmin_load_card(acts.drop(columns="garmin_load"), NOW, cfg) is None


def _easy(rows):
    """rows: (days ago, pace, temperature)"""
    return pd.DataFrame({"date": [NOW - pd.Timedelta(days=d) for d, _, _ in rows],
                         "pace_min_km": [p for _, p, _ in rows], "temp_c": [c for _, _, c in rows]})


def test_a_slower_easy_pace_in_warmer_weather_is_not_coloured_as_lost_fitness():
    card = metrics.easy_pace_card(_easy([(2, 6.0, 24.0), (5, 6.0, 26.0), (35, 5.5, 14.0)]), (), NOW)
    assert card.value == 6.0 and card.previous == 5.5
    assert card.tone == "neutral"
    assert card.note == "slower, but 11 °C warmer than the previous 4 weeks"


def test_a_slower_easy_pace_in_the_same_weather_stays_red():
    card = metrics.easy_pace_card(_easy([(2, 6.0, 15.0), (35, 5.5, 14.0)]), (), NOW)
    assert card.tone == "bad" and card.note == "vs previous 4 weeks, easy road runs"


def test_a_faster_easy_pace_in_cooler_weather_is_not_coloured_as_gained_fitness():
    card = metrics.easy_pace_card(_easy([(2, 5.0, 8.0), (35, 5.5, 20.0)]), (), NOW)
    assert card.tone == "neutral"
    assert card.note == "faster, but 12 °C cooler than the previous 4 weeks"


def _days(days_ago):
    return _runs([(d, 5, 30, None, None, None) for d in days_ago])


def test_run_streak_counts_weeks_in_a_row_with_three_runs():
    # TODAY is a Monday: this week has one run so far and neither counts nor breaks the streak.
    runs = _days([0, 1, 2, 3, 8, 9, 10, 15, 16, 17, 22, 23])   # 3, 3, 3, then a week with 2
    card = metrics.streak_card(runs, NOW)
    assert (card.key, card.unit, card.value) == ("run_streak", "weeks", 3.0)
    assert card.note == "weeks in a row with 3 or more runs"
    assert card.detail == "1 this week"


def test_run_streak_includes_the_current_week_once_it_qualifies():
    wednesday = NOW + pd.Timedelta(days=2)
    runs = _days([0, 1, 2, 3])                                  # relative to Monday: Mon + 3 last week
    runs = pd.concat([runs, runs.assign(date=[wednesday, wednesday - pd.Timedelta(days=1),
                                               wednesday - pd.Timedelta(days=1), wednesday])],
                     ignore_index=True)
    assert metrics.streak_card(runs, wednesday).value == 2.0     # this week (3+) and last week (3)
    assert metrics.streak_card(_days([40]), NOW).value == 0.0


def test_training_days_cover_whole_weeks_and_leave_the_future_blank():
    acts = _runs([(0, 5, 30, None, None, None), (0, 0, 20, None, None, None),
                  (8, 5, 45, None, None, None)])
    days = metrics.training_days(2, activities=acts, today=TODAY)
    assert list(days.columns) == ["date", "minutes", "activities"] and len(days) == 14
    assert days["date"].iloc[0] == NOW - pd.Timedelta(days=7)    # Monday of last week
    by_date = days.set_index("date")["minutes"]
    assert by_date[NOW] == 50.0 and by_date[NOW - pd.Timedelta(days=6)] == 0.0
    assert pd.isna(by_date[NOW + pd.Timedelta(days=1)])          # tomorrow has not happened


def _race_runs():
    rows = [(d, 10, 60, None, None, None) for d in (3, 10, 17, 24, 31, 38, 45, 52)]   # build-up now
    rows += [(5, 24, 150, None, None, None)]                                          # long run
    rows += [(100, 21, 110, None, None, None)]                                        # previous race
    rows += [(100 + 20 + d, 8, 50, None, None, None) for d in (3, 10, 17)]            # its build-up
    runs = _runs(rows)
    runs["session_type"] = None
    runs["race_name"] = None
    runs.loc[9, ["session_type", "race_name"]] = ["race", "Spring Half <1>"]
    return runs


def test_race_readiness_compares_the_build_up_with_the_same_point_before_the_last_similar_race():
    plan = pd.DataFrame({"date": [NOW + pd.Timedelta(days=20)], "type": ["race"],
                         "session": ["Autumn Half"], "distance_km": [21.1]})
    ready = metrics.race_readiness(_race_runs(), plan, NOW)
    assert ready["race"] == "Autumn Half" and ready["days_to_go"] == 20
    assert ready["km"] == pytest.approx(104.0) and ready["longest_km"] == pytest.approx(24.0)
    assert ready["previous"]["name"] == "Spring Half <1>"
    assert ready["previous"]["km"] == pytest.approx(24.0)       # three 8 km runs, same point
    assert ready["previous"]["longest_km"] == pytest.approx(8.0)


def test_race_readiness_without_a_similar_earlier_race_or_without_a_race():
    marathon = pd.DataFrame({"date": [NOW + pd.Timedelta(days=20)], "type": ["race"],
                             "session": ["Marathon"], "distance_km": [42.2]})
    assert metrics.race_readiness(_race_runs(), marathon, NOW)["previous"] is None
    none = pd.DataFrame({"date": [NOW - pd.Timedelta(days=2)], "type": ["race"],
                         "session": ["Past"], "distance_km": [10.0]})
    assert metrics.race_readiness(_race_runs(), none, NOW) is None
    assert metrics.race_readiness(_race_runs(), None, NOW) is None


def test_sleep_and_hrv_cards_carry_garmin_detail(cfg, tmp_path):
    path = tmp_path / "w.parquet"
    dates = pd.date_range(end=pd.Timestamp(TODAY), periods=30)
    pd.DataFrame({"date": dates, "sleep_hours": 7.0, "hrv_ms": 50.0, "sleep_score": 82.0,
                  "deep_sleep_seconds": 4320.0, "rem_sleep_seconds": 5400.0,
                  "hrv_status": ["BALANCED"] * 29 + ["UNBALANCED"]}).to_parquet(path)
    recovery = by_key(metrics.headline(today=TODAY, cfg=replace(cfg, wellness_parquet=path))["recovery"])
    assert list(recovery) == ["hrv_ms", "sleep_hours"]
    assert recovery["sleep_hours"].detail == "score 82, deep 1.2 h, REM 1.5 h"
    assert recovery["hrv_ms"].detail == "unbalanced"


def _kind_runs(surface, km, climb):
    runs = _runs([(100, km, 110, None, None, None), (3, 10, 60, None, None, None)])
    runs["surface"] = [surface, "road"]
    runs["elevation_m"] = [float(climb), 20.0]
    runs["session_type"] = ["race", None]
    runs["race_name"] = ["Earlier", None]
    return runs


def _race_plan(session, km, **extra):
    return pd.DataFrame({"date": [NOW + pd.Timedelta(days=20)], "type": ["race"],
                         "session": [session], "distance_km": [km], **extra})


def test_a_road_race_is_only_compared_with_a_road_race_of_nearly_the_same_distance():
    assert metrics.race_readiness(_kind_runs("road", 21.0, 80), _race_plan("Half", 21.1), NOW)["previous"]
    assert metrics.race_readiness(_kind_runs("road", 19.0, 80), _race_plan("Half", 21.1), NOW)["previous"] is None
    assert metrics.race_readiness(_kind_runs("trail", 21.0, 80), _race_plan("Half", 21.1), NOW)["previous"] is None
    hilly = _race_plan("Half", 21.1, elevation_m=[50.0])        # climb known: must be within 100 m
    assert metrics.race_readiness(_kind_runs("road", 21.0, 300), hilly, NOW)["previous"] is None


def test_a_trail_race_allows_a_quarter_of_difference_in_distance_and_climb():
    trail = _race_plan("Coast Trail", 20.0, elevation_m=[1000.0])
    assert metrics.race_readiness(_kind_runs("trail", 24.0, 800), trail, NOW)["previous"]
    assert metrics.race_readiness(_kind_runs("trail", 24.0, 400), trail, NOW)["previous"] is None
    assert metrics.race_readiness(_kind_runs("road", 20.0, 900), trail, NOW)["previous"] is None
    named = _race_plan("Forest Trail 20", 20.0)                 # no surface column: the name says trail
    assert metrics.race_readiness(_kind_runs("mixed", 23.0, 500), named, NOW)["previous"]
    stated = _race_plan("Hill race", 20.0, surface=["trail"])
    assert metrics.race_readiness(_kind_runs("trail", 23.0, 500), stated, NOW)["previous"]


def test_the_build_up_window_grows_with_the_race_distance():
    assert [metrics.build_weeks(km) for km in (5, 10, 21.1, 42.2, None)] == [6, 6, 8, 12, 8]
    assert metrics.race_readiness(_kind_runs("road", 10, 20), _race_plan("10k", 10.0), NOW)["weeks"] == 6


# ---- review findings ----

def test_plan_done_counts_only_the_days_the_plan_covers():
    runs = _runs([(d, 5, 30, None, None, None) for d in range(1, 29)])       # 5 km every day
    plan = _plan([(d, "easy", 5) for d in range(1, 8)])                      # plan starts a week ago
    card = metrics.adherence_card(runs, plan, NOW)
    assert card.value == pytest.approx(100.0) and card.detail == "35.0 of 35.0 km"
    assert card.note == "the 7 days the plan covers, to yesterday" and card.previous is None


def test_plan_done_leaves_out_days_whose_session_has_no_distance():
    runs = _runs([(d, 5, 30, None, None, None) for d in range(1, 29)])
    plan = _plan([(d, "easy", 5 if d % 2 else None) for d in range(1, 29)])  # every other one by time
    assert metrics.adherence_card(runs, plan, NOW).value == pytest.approx(100.0)


def test_plan_done_is_not_given_for_a_plan_that_ended_or_only_just_started():
    runs = _runs([(d, 5, 30, None, None, None) for d in range(1, 29)])
    for days in (range(1, 4), range(25, 40)):                                # 3 days; ended 25 days ago
        card = metrics.adherence_card(runs, _plan([(d, "easy", 5) for d in days]), NOW)
        assert card.value is None and card.note == "the plan covers under a week of the last 4"


def test_garmin_load_is_not_given_while_the_feed_is_days_behind(cfg):
    acts = _runs([(d, 8, 45, None, None, None) for d in range(0, 28)])
    acts["garmin_load"] = 100.0
    assert metrics.garmin_load_card(acts, NOW, cfg).value == pytest.approx(1.0)
    acts.loc[acts["date"] >= NOW, "garmin_load"] = None                      # today: the feed runs tomorrow
    assert metrics.garmin_load_card(acts, NOW, cfg).value is not None
    acts.loc[acts["date"] >= NOW - pd.Timedelta(days=3), "garmin_load"] = None
    card = metrics.garmin_load_card(acts, NOW, cfg)
    assert card.value is None and card.detail is None and card.tone == "neutral"
    assert card.note == "the Garmin feed is behind: 4 recent activities have no load yet"


# ---- review minors ----

def test_vo2max_is_not_compared_with_a_value_older_than_eight_weeks():
    old = metrics.vo2max_card(_runs([(700, 8, 45, 58.0, 2.5, 0.0), (3, 8, 45, 52.0, 2.5, 0.0)]), NOW)
    assert old.value == 52.0 and old.previous is None and old.tone == "neutral"
    assert old.note == "Garmin estimate; no value from 4 to 8 weeks ago to compare"
    near = metrics.vo2max_card(_runs([(40, 8, 45, 50.0, 2.5, 0.0), (3, 8, 45, 52.0, 2.5, 0.0)]), NOW)
    assert near.previous == 50.0 and near.note == "Garmin estimate, vs 4 weeks ago"


def test_on_race_day_neither_build_up_window_holds_a_race():
    runs = _runs([(0, 21, 110, None, None, None), (3, 10, 60, None, None, None),
                  (100, 21, 110, None, None, None), (103, 8, 50, None, None, None)])
    runs["session_type"] = ["race", None, "race", None]
    runs["race_name"] = [None, None, "Earlier", None]
    plan = pd.DataFrame({"date": [NOW], "type": ["race"], "session": ["Half"], "distance_km": [21.1]})
    ready = metrics.race_readiness(runs, plan, NOW)
    assert ready["days_to_go"] == 0
    assert (ready["km"], ready["longest_km"]) == (10.0, 10.0)
    assert (ready["previous"]["km"], ready["previous"]["longest_km"]) == (8.0, 8.0)


def test_a_hilly_road_race_counts_as_an_earlier_road_race():
    assert metrics.race_readiness(_kind_runs("mixed", 21.0, 80), _race_plan("Half", 21.1), NOW)["previous"]


def test_weeks_with_runs_but_no_training_effect_are_missing_not_zero():
    runs = _runs([(0, 10, 60, None, 2.5, 0.0), (7, 8, 45, None, None, None)])
    weekly = metrics.intensity_weekly(3, activities=runs, today=TODAY)
    assert weekly.iloc[-1]["easy_min"] == 60.0
    assert weekly.iloc[-2][["easy_min", "steady_min", "hard_min"]].isna().all()     # ran, not rated
    assert weekly.iloc[-3][["easy_min", "steady_min", "hard_min"]].tolist() == [0.0, 0.0, 0.0]


def test_a_day_with_an_activity_of_unknown_length_is_not_a_rest_day():
    acts = _runs([(0, 5, float("nan"), None, None, None), (1, 5, 30, None, None, None)])
    days = metrics.training_days(1, activities=acts, today=TODAY).set_index("date")
    assert days.loc[NOW, "activities"] == 1 and days.loc[NOW, "minutes"] == 0.0
    assert days.loc[NOW + pd.Timedelta(days=1), "activities"] == 0
