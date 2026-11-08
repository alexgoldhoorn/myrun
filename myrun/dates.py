"""Calendar helpers shared by the library: "today", the Monday of a week, a run of weeks.

"Today" is the local date of the process (the container's TZ), because the activities'
dates are local too. Every function that takes a `today` argument resolves it here, so
there is one place to change if that ever has to be a configured timezone."""

from __future__ import annotations

from datetime import date

import pandas as pd


def today_ts(today=None) -> pd.Timestamp:
    """`today` (anything pandas reads as a date) or the local date now, at midnight."""
    return pd.Timestamp(today if today is not None else date.today()).normalize()


def monday_of(day: pd.Timestamp) -> pd.Timestamp:
    """The Monday of the week `day` falls in."""
    return day - pd.Timedelta(days=day.weekday())


def week_starts(dates: pd.Series) -> pd.Series:
    """The Monday of each date in a datetime Series."""
    return dates - pd.to_timedelta(dates.dt.weekday, unit="D")


def week_range(now: pd.Timestamp, weeks: int) -> pd.DatetimeIndex:
    """The Mondays of the `weeks` weeks ending with the week of `now`, oldest first."""
    return pd.date_range(monday_of(now) - pd.Timedelta(weeks=weeks - 1), periods=weeks, freq="7D")


def between(df: pd.DataFrame, first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    """Rows whose `date` falls in first..last, both days included."""
    return df[(df["date"] >= first) & (df["date"] <= last)]


def last_days(df: pd.DataFrame, end: pd.Timestamp, days: int = 28) -> pd.DataFrame:
    """Rows whose `date` falls in the `days` days up to and including `end`."""
    return df[(df["date"] > end - pd.Timedelta(days=days)) & (df["date"] <= end)]
