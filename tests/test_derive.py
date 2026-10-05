import numpy as np
import pandas as pd
import pytest

from myrun import derive


def test_hilliness_is_nan_for_zero_distance():
    out = derive.hilliness(pd.Series([200.0, 50.0]), pd.Series([10.0, 0.0]))
    assert out[0] == 20.0
    assert np.isnan(out[1])


def test_surface():
    sport = pd.Series(["Run", "Run", "TrailRun", "Ride", "Run"])
    hill = pd.Series([4.0, 15.0, 40.0, 30.0, np.nan])
    assert derive.surface(sport, hill, 15.0).tolist() == ["road", "mixed", "trail", None, "road"]


def test_grade_class_is_per_km():
    elev = pd.Series([30, -30, 5, 10, 0])
    dist = pd.Series([1000, 1000, 1000, 400, 0])
    assert derive.grade_class(elev, dist, 20.0).tolist() == ["climb", "descent", "flat", "climb", None]


def test_bin_label():
    out = derive.bin_label(pd.Series([7.5, 12.0, 15.0, np.nan, -2.0]), 5)
    assert out.tolist() == ["5–10", "10–15", "15–20", None, "-5–0"]


@pytest.mark.parametrize("ratio, label", [
    (None, "no data"), (0.79, "low"), (0.8, "steady"), (1.3, "steady"),
    (1.31, "high"), (1.5, "high"), (1.51, "very high"),
])
def test_load_label(ratio, label):
    assert derive.load_label(ratio, (0.8, 1.3, 1.5)) == label
