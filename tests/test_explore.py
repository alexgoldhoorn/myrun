import numpy as np
import pandas as pd

from myrun import explore


def _df():
    return pd.DataFrame({
        "hour": [7.5, 18.5, 12.0], "temp_c": [12.0, 22.0, np.nan],
        "distance_km": [7.2, 10.0, 15.0], "hilliness_m_km": [4.0, 20.0, 40.0],
        "surface": ["road", "mixed", "trail"], "session_type": [None, None, None],
        "year": [2026, 2026, 2025], "sport": ["Run", "Run", "TrailRun"],
        "has_streams": [True, False, True], "name": ["a", "b", "c"],
    })


def test_group_series_blocks():
    df = _df()
    assert explore.group_series(df, "Hour of day").tolist() == ["6–9", "18–21", "12–15"]
    assert explore.group_series(df, "Hour of day", hour_block=6).tolist() == [
        "6–12", "18–24", "12–18"]
    assert explore.group_series(df, "Temperature").tolist() == ["10–15", "20–25", None]
    assert explore.group_series(df, "Distance").tolist() == ["5–10", "10–15", "15–20"]
    assert explore.group_series(df, "Surface").tolist() == ["road", "mixed", "trail"]
    assert explore.group_series(df, "Year").tolist() == ["2026", "2026", "2025"]
    assert explore.group_series(df, "(none)") is None


def test_available_groups_skips_missing_and_empty_columns():
    groups = explore.available_groups(_df())
    assert groups[0] == "(none)"
    assert "Surface" in groups and "Hour of day" in groups
    assert "Session type" not in groups          # all None
    assert "Climb or descent" not in groups      # no grade_class column at run level


def test_numeric_columns_excludes_flags_and_text():
    assert explore.numeric_columns(_df()) == ["hour", "temp_c", "distance_km", "hilliness_m_km",
                                              "year"]


def test_ordered_is_numeric_aware():
    assert explore.ordered(["10–15", "5–10", "road", None, "-5–0"]) == [
        "-5–0", "5–10", "10–15", "road"]
