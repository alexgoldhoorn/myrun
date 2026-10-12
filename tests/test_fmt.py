import math

import pandas as pd
import pytest

from myrun import fmt


@pytest.mark.parametrize("value, text", [
    (6.38, "6:23"), (5.0, "5:00"), (4.456806, "4:27"), (5.999, "6:00"), (12.5, "12:30"),
    (None, "n/a"), (float("nan"), "n/a"), (pd.NA, "n/a"), (0, "n/a"), (float("inf"), "n/a"),
])
def test_pace(value, text):
    assert fmt.pace(value) == text


@pytest.mark.parametrize("seconds, text", [
    (2682, "44:42"), (59, "0:59"), (3600, "1:00:00"), (5025.4, "1:23:45"), (None, "n/a"),
    (float("nan"), "n/a"),
])
def test_duration(seconds, text):
    assert fmt.duration(seconds) == text


def test_pace_ticks_are_round_and_few():
    vals, text = fmt.pace_ticks(pd.Series([4.4, 5.1, 6.4]))
    assert text == ["4:30", "5:00", "5:30", "6:00"]
    assert vals == [4.5, 5.0, 5.5, 6.0]
    vals, text = fmt.pace_ticks(pd.Series([4.0, 14.0]))          # a wide range gets wider steps
    assert len(vals) <= 8 and text[0].endswith(":00")
    assert fmt.pace_ticks(pd.Series([], dtype=float)) == ([], [])
    assert fmt.pace_ticks(pd.Series([math.nan])) == ([], [])
    assert fmt.pace_ticks(pd.Series([5.2, 5.2])) == ([5.25], ["5:15"]) or fmt.pace_ticks(
        pd.Series([5.2, 5.2]))[1]          # a flat series still gets at least one label


def test_duration_ticks():
    vals, text = fmt.duration_ticks(pd.Series([1330, 1500, 1667]))
    assert text[0] == "23:00" and all(v % 60 == 0 for v in vals) and len(vals) <= 8


def test_metric_value_and_delta():
    assert fmt.metric_value(47.25, "km") == "47.2 km"
    assert fmt.metric_value(1890, "m") == "1,890 m"
    assert fmt.metric_value(1.014, "metres") == "1.01 m"
    assert fmt.metric_value(5.556, "pace") == "5:33 /km"
    assert fmt.metric_value(1.566, "ratio") == "1.57"
    assert fmt.metric_value(7.25, "hours") == "7.2 h"
    assert fmt.metric_value(None, "km") == "n/a"
    assert fmt.metric_value(float("nan"), "bpm") == "n/a"
    assert fmt.metric_delta(5.0, "km") == "+5.0 km"
    assert fmt.metric_delta(-0.1, "pace") == "-6 s /km"
    assert fmt.metric_delta(None, "km") == ""
