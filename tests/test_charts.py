import pandas as pd

from myrun.ui import charts


def test_load_bars_has_one_bar_per_week():
    weekly = pd.DataFrame({"week_start": pd.to_datetime(["2026-09-28", "2026-10-05"]),
                           "effort": [135.0, 0.0], "n_activities": [3, 0],
                           "n_missing_effort": [0, 0]})
    fig = charts.load_bars(weekly)
    assert len(fig.data) == 1 and list(fig.data[0].y) == [135.0, 0.0]


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


def test_explore_figure_scatter_with_trend_per_group():
    df = pd.DataFrame({"temp_c": [5.0, 10.0, 15.0, 20.0, 6.0, 11.0, 16.0],
                       "pace_min_km": [5.0, 5.1, 5.3, 5.6, 6.0, 6.2, 6.5]})
    group = pd.Series(["road"] * 4 + ["trail"] * 3)
    fig = charts.explore_figure(df, "temp_c", "pace_min_km", group)
    assert len(fig.data) == 4                              # points and a line, per group
    assert len(charts.explore_figure(df, "temp_c", "pace_min_km").data) == 2


def test_explore_figure_no_trend_line_for_too_few_points():
    df = pd.DataFrame({"x": [1.0, 2.0], "y": [1.0, 2.0]})
    assert len(charts.explore_figure(df, "x", "y").data) == 1


def test_explore_figure_box_for_a_category():
    df = pd.DataFrame({"surface": ["road", "road", "trail"], "avg_hr": [140, 145, 155]})
    fig = charts.explore_figure(df, "surface", "avg_hr")
    assert fig.data[0].type == "box"


def test_explore_figure_ignores_rows_with_missing_values():
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, None], "y": [1.0, None, 3.0, 4.0]})
    assert list(charts.explore_figure(df, "x", "y").data[0].x) == [1.0, 3.0]


def test_pace_is_shown_as_minutes_and_seconds():
    fig = charts.stream_figure(_streams())
    pace = fig.data[1]                                   # hr, pace, altitude, cadence
    assert pace.text[0] == "5:30"
    assert "%{text}" in pace.hovertemplate
    assert "5:30" in list(fig.layout.yaxis2.ticktext)
    assert fig.layout.yaxis.ticktext is None             # the HR axis is left alone


def test_explore_formats_a_pace_axis_and_nothing_else():
    df = pd.DataFrame({"temp_c": [5.0, 10.0, 15.0, 20.0],
                       "pace_min_km": [5.0, 5.25, 5.5, 6.0]})
    fig = charts.explore_figure(df, "temp_c", "pace_min_km")
    assert "5:30" in list(fig.layout.yaxis.ticktext)
    assert fig.layout.xaxis.ticktext is None
    flipped = charts.explore_figure(df, "pace_min_km", "temp_c")
    assert "5:30" in list(flipped.layout.xaxis.ticktext)


def test_weekly_km_bars_adds_the_plan_only_when_there_is_one():
    weekly = pd.DataFrame({"week_start": pd.to_datetime(["2026-09-28", "2026-10-05"]),
                           "run_km": [17.2, 0.0], "planned_km": [float("nan"), float("nan")]})
    assert len(charts.weekly_km_bars(weekly).data) == 1
    weekly["planned_km"] = [20.0, 25.0]
    assert [t.name for t in charts.weekly_km_bars(weekly).data] == ["done", "planned"]


def test_intensity_bars_stack_three_named_series_without_own_colours():
    weekly = pd.DataFrame({"week_start": pd.to_datetime(["2026-09-28", "2026-10-05"]),
                           "easy_min": [120.0, 60.0], "steady_min": [30.0, 0.0],
                           "hard_min": [10.0, 20.0]})
    fig = charts.intensity_bars(weekly)
    assert [t.name for t in fig.data] == ["easy", "steady", "hard"]
    assert fig.layout.barmode == "stack"
    assert all(t.marker.color is None for t in fig.data)
