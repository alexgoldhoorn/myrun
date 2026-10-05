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


def _streams(n=100, hr=140):
    return pd.DataFrame({
        "time_s": range(n), "distance_m": [3.0 * i for i in range(n)], "hr": [hr] * n,
        "speed_ms": [3.0] * n, "pace_min_km": [5.5] * n, "altitude_m": [50.0] * n,
        "cadence_spm": [170] * n, "grade_pct": [0.0] * n, "moving": [True] * n,
    })


def test_stream_figure_one_row_per_available_metric():
    fig = charts.stream_figure(_streams())
    assert len(fig.data) == 4                           # hr, pace, altitude, cadence
    partial = _streams()
    partial["pace_min_km"] = float("nan")
    partial["cadence_spm"] = float("nan")
    assert len(charts.stream_figure(partial).data) == 2


def test_stream_figure_x_axis_and_overlay():
    by_time = charts.stream_figure(_streams(), x="time")
    assert by_time.data[0].x[-1] == 99 / 60             # minutes
    by_distance = charts.stream_figure(_streams(), x="distance")
    assert by_distance.data[0].x[-1] == 3.0 * 99 / 1000  # km
    both = charts.stream_figure(_streams(), overlay=_streams(hr=150))
    assert len(both.data) == 8


def test_stream_figure_with_no_data_is_an_empty_figure():
    assert len(charts.stream_figure(pd.DataFrame(columns=_streams().columns)).data) == 0


def test_zone_bar():
    zones = pd.DataFrame({"zone": [1, 2], "lower": [0, 126], "upper": [125.0, float("nan")],
                          "seconds": [600.0, 1200.0], "pct": [33.3, 66.7]})
    fig = charts.zone_bar(zones)
    assert list(fig.data[0].x) == [10.0, 20.0]          # minutes
