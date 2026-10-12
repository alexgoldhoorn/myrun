import pandas as pd
import plotly.graph_objects as go

from myrun.ui import charts, theme


def test_style_sets_margins_and_optional_height():
    fig = theme.style(go.Figure(), height=300)
    assert fig.layout.height == 300
    assert fig.layout.margin.to_plotly_json() == theme.MARGIN
    assert theme.style(go.Figure()).layout.height is None


def test_css_has_a_class_per_tone_in_light_and_dark():
    for css_class in theme.TONE_CLASS.values():
        assert f".{css_class}" in theme.CSS
    assert "prefers-color-scheme: dark" in theme.CSS


def _has_own_colour(fig) -> bool:
    for trace in fig.data:
        data = trace.to_plotly_json()
        if (data.get("marker") or {}).get("color") or (data.get("line") or {}).get("color"):
            return True
    return False


def test_builders_use_the_theme_and_set_no_colours():
    weekly = pd.DataFrame({"week_start": pd.to_datetime(["2026-09-28", "2026-10-05"]),
                           "effort": [135.0, 0.0]})
    zones = pd.DataFrame({"zone": [1, 2], "seconds": [600, 300], "pct": [66.0, 34.0]})
    trend = pd.DataFrame({"month": pd.to_datetime(["2026-09-01"]), "value": [250.0]})
    points = pd.DataFrame({"temp_c": [10.0, 20.0, 15.0], "pace_min_km": [5.5, 6.0, 5.8]})
    figures = [charts.load_bars(weekly), charts.zone_bar(zones),
               charts.trend_line(trend, "month", "value", "Ground contact"),
               charts.explore_figure(points, "temp_c", "pace_min_km")]
    for fig in figures:
        assert fig.layout.margin.to_plotly_json() == theme.MARGIN
        assert not _has_own_colour(fig)
