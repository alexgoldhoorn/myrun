from myrun.metric import Metric
from myrun.ui import cards


def test_card_shows_value_change_note_and_trend():
    html = cards.card_html(Metric("km_4w", "Last 4 weeks", 47.2, 10.0, "km", (1.0, 3.0, 2.0),
                                  note="vs previous 4 weeks"))
    assert "Last 4 weeks" in html and "47.2 km" in html
    assert "+37.2 km" in html and "vs previous 4 weeks" in html
    assert "<polyline" in html and "mr-neutral" in html


def test_card_without_a_value_shows_na_and_the_reason_and_no_change():
    html = cards.card_html(Metric("easy_pace", "Easy pace", None, 5.0, "pace",
                                  note="no easy road runs in the last 4 weeks"))
    assert "n/a" in html and "no easy road runs" in html
    assert "s /km" not in html and "<polyline" not in html


def test_tone_and_detail():
    html = cards.card_html(Metric("load_ratio", "Load", 1.57, 1.1, "ratio", tone="bad",
                                  detail="very high"))
    assert "mr-bad" in html and "very high" in html and "1.57" in html


def test_text_from_data_is_escaped():
    html = cards.card_html(Metric("x", "<b>Race & run</b>", 1.0, None, "km",
                                  note="<script>alert(1)</script>", detail="a<b"))
    assert "<script>" not in html and "<b>Race" not in html
    assert "&lt;script&gt;" in html and "Race &amp; run" in html and "a&lt;b" in html
    strip = cards.strip_html([("Next race", "Trail <Race> & more")])
    assert "Trail &lt;Race&gt; &amp; more" in strip


def test_sparkline_needs_two_points_and_survives_a_flat_series():
    assert cards.sparkline_svg(()) == "" and cards.sparkline_svg((5.0,)) == ""
    flat = cards.sparkline_svg((3.0, 3.0, 3.0))
    assert flat.count(",") == 3 and "nan" not in flat.lower()


def test_row_wraps_every_card():
    html = cards.row_html([Metric("a", "A", 1.0, None, "km"), Metric("b", "B", 2.0, None, "km")])
    assert html.startswith('<div class="mr-row">') and html.count('class="mr-card"') == 2


def test_calendar_is_one_square_per_day_with_escaped_tooltips_and_blank_future_days():
    import pandas as pd
    days = pd.DataFrame({"date": pd.date_range("2026-09-28", periods=14),
                         "minutes": [0.0, 30.0, 95.0] + [0.0] * 8 + [float("nan")] * 3})
    html = cards.calendar_html(days)
    assert html.count('class="mr-day') == 14
    assert html.count("mr-day-future") == 3 and html.count("mr-day-0") == 9
    assert 'title="Tue 29 Sep: 30 min"' in html and "mr-day-3" in html     # 95 min: top level
    assert cards.calendar_html(days.iloc[0:0]) == ""


def test_readiness_strip_escapes_names():
    html = cards.readiness_html({"race": "Autumn <Half>", "days_to_go": 20, "weeks": 8, "km": 104.0,
                                 "longest_km": 24.0,
                                 "previous": {"name": "Spring & Half", "date": __import__("pandas").Timestamp("2026-06-27"),
                                              "km": 24.0, "longest_km": 8.0}})
    assert "Autumn &lt;Half&gt;" in html and "Spring &amp; Half" in html
    assert "104 km" in html and "longest 24 km" in html and "<Half>" not in html
    assert cards.readiness_html(None) == ""
