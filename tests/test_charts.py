import pandas as pd

from myrun.ui import charts


def test_load_bars_has_one_bar_per_week():
    weekly = pd.DataFrame({"week_start": pd.to_datetime(["2026-09-28", "2026-10-05"]),
                           "effort": [135.0, 0.0], "n_activities": [3, 0],
                           "n_missing_effort": [0, 0]})
    fig = charts.load_bars(weekly)
    assert len(fig.data) == 1 and list(fig.data[0].y) == [135.0, 0.0]


def test_sparkline_handles_empty_input():
    assert len(charts.sparkline(pd.Series([50.0, 52.0, 49.0])).data) == 1
    assert len(charts.sparkline(pd.Series([], dtype=float)).data) == 1
