import pandas as pd

from myrun import dynamics, runs
from tests.fixture import HILLY, STEADY, write_garmin_csv


def _runs(cfg, tmp_path):
    from dataclasses import replace
    return runs(cfg=replace(cfg, garmin_activities=write_garmin_csv(tmp_path / "g.csv")))


def test_only_present_dynamics_become_cards(cfg, tmp_path):
    df = _runs(cfg, tmp_path)
    row = df.set_index("activity_id").loc[STEADY]
    cards = dynamics.activity_dynamics(row, df)
    assert [c.key for c in cards] == ["ground_contact_ms", "vertical_oscillation_cm",
                                      "vertical_ratio_pct", "stride_length_m", "power_w",
                                      "aerobic_te"]
    contact = cards[0]
    assert contact.value == 250.0 and contact.unit == "ms"
    assert contact.previous is None                    # no earlier run has the value
    assert contact.note == "no earlier runs to compare"


def test_a_run_without_garmin_data_has_no_cards(cfg, tmp_path):
    df = _runs(cfg, tmp_path)
    assert dynamics.activity_dynamics(df.set_index("activity_id").loc[HILLY], df) == []


def test_without_the_garmin_input_there_are_no_cards(cfg):
    df = runs(cfg=cfg)
    assert dynamics.activity_dynamics(df.iloc[0], df) == []
    assert dynamics.available(df) == []


def test_previous_is_the_median_of_earlier_runs_on_the_same_surface():
    frame = pd.DataFrame({
        "activity_id": ["a", "b", "c", "d"],
        "start": pd.to_datetime(["2026-09-01", "2026-09-10", "2026-09-20", "2026-10-01"]),
        "surface": ["road", "trail", "road", "road"],
        "ground_contact_ms": [240.0, 300.0, 260.0, 250.0],
    })
    card = dynamics.activity_dynamics(frame.iloc[3], frame)[0]
    assert card.previous == 250.0                      # median of the two earlier road runs
    assert card.note == "vs median of 2 road runs, 90 days"


def test_trend_starts_at_the_first_month_with_data(cfg, tmp_path):
    df = _runs(cfg, tmp_path)
    trend = dynamics.dynamics_trend("ground_contact_ms", activities=df, cfg=cfg)
    assert list(trend.columns) == ["month", "value", "n_runs"]
    assert trend["value"].tolist() == [250.0] and trend["n_runs"].tolist() == [1]
    assert dynamics.available(df)[0] == "ground_contact_ms"


def test_an_activity_that_is_not_a_run_has_no_cards():
    frame = pd.DataFrame({
        "activity_id": ["a", "b"],
        "start": pd.to_datetime(["2026-09-01", "2026-09-10"]),
        "sport": ["Run", "Ride"],
        "surface": ["road", "road"],
        "power_w": [300.0, 180.0],
        "aerobic_te": [3.0, 2.5],
    })
    assert dynamics.activity_dynamics(frame.iloc[1], frame) == []
    assert [c.key for c in dynamics.activity_dynamics(frame.iloc[0], frame)] == ["power_w",
                                                                               "aerobic_te"]


def test_the_note_for_a_single_earlier_run_is_singular():
    frame = pd.DataFrame({
        "activity_id": ["a", "b"], "start": pd.to_datetime(["2026-09-20", "2026-10-01"]),
        "surface": ["road", "road"], "ground_contact_ms": [240.0, 250.0],
    })
    assert dynamics.activity_dynamics(frame.iloc[1], frame)[0].note == "vs median of 1 road run, 90 days"
