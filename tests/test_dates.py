from datetime import date

import pandas as pd

from myrun import dates


def test_today_defaults_to_the_local_date_at_midnight():
    assert dates.today_ts() == pd.Timestamp(date.today())
    assert dates.today_ts().hour == 0


def test_today_accepts_a_date_or_a_timestamp_and_drops_the_time():
    assert dates.today_ts(date(2026, 10, 7)) == pd.Timestamp("2026-10-07")
    assert dates.today_ts(pd.Timestamp("2026-10-07 15:30")) == pd.Timestamp("2026-10-07")


def test_monday_of_every_weekday_is_that_weeks_monday():
    monday = pd.Timestamp("2026-10-05")
    for offset in range(7):
        assert dates.monday_of(monday + pd.Timedelta(days=offset)) == monday


def test_week_starts_maps_a_series_to_mondays():
    days = pd.Series(pd.to_datetime(["2026-10-04", "2026-10-05", "2026-10-11"]))
    assert list(dates.week_starts(days)) == list(pd.to_datetime(
        ["2026-09-28", "2026-10-05", "2026-10-05"]))


def test_week_range_ends_with_the_current_weeks_monday():
    weeks = dates.week_range(pd.Timestamp("2026-10-08"), 3)
    assert list(weeks) == list(pd.to_datetime(["2026-09-21", "2026-09-28", "2026-10-05"]))
    assert len(dates.week_range(pd.Timestamp("2026-10-08"), 12)) == 12
