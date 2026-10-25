from dataclasses import replace

import pandas as pd
import pytest

from myrun import bands, report
from myrun.activities import activities
from myrun.ui import charts
from tests.fixture import TODAY, write_garmin_csv


def test_pace_band_edges_go_to_the_slower_band():
    paces = pd.Series([4.2, 4.5, 4.99, 5.0, 5.75, 6.0, 7.0, 7.5, None])
    assert list(bands.pace_band(paces)) == [
        "<4:30", "4:30–5:00", "4:30–5:00", "5:00–5:30", "5:30–6:00", "6:00–7:00", ">7:00",
        ">7:00", None]


def test_hr_sensor_is_the_latest_one_in_use():
    from datetime import date
    dates = pd.Series(pd.to_datetime(["2020-06-01", "2021-01-01", "2023-05-01"]))
    sensors = ((date(2023, 4, 11), "strap 2"), (date(2020, 12, 30), "strap 1"))
    assert list(bands.hr_sensor(dates, sensors)) == [None, "strap 1", "strap 2"]


def test_gear_yearly_shares_per_watch_and_sensor():
    rows = _band_rows().assign(device=["Forerunner 945", "Forerunner 965", "Forerunner 945",
                                       "Forerunner 965"], hr_sensor=[None, "strap", "strap", "strap"])
    rows.loc[3, "excluded"] = "race"
    out = bands.gear_yearly(rows).set_index("year")
    assert list(out.index) == [2024] and out.loc[2024, "n_runs"] == 3
    assert out.loc[2024, "watches"]["Forerunner 945"] == pytest.approx(200 / 3)
    assert out.loc[2024, "sensors"] == pytest.approx({"strap": 200 / 3, "none set": 100 / 3})


@pytest.mark.parametrize("text, months", [("", None), ("9-10", (9, 10)), ("9,10", (9, 10)),
                                          ("11-2", (11, 12, 1, 2)), (" 3 ", (3,))])
def test_parse_season(text, months):
    assert bands.parse_season(text) == months


@pytest.mark.parametrize("text", ["13", "0-2", "sep", "9;10"])
def test_parse_season_rejects(text):
    with pytest.raises(ValueError):
        bands.parse_season(text)


def _runs(rows):
    return pd.DataFrame(rows, columns=["sport", "year", "hilliness_m_km"])


def test_trail_threshold_is_fitted_where_trail_runs_are_tagged():
    rows = [("Run", 2024, h) for h in range(0, 25)] + [("TrailRun", 2024, h) for h in range(35, 60)]
    value, source = bands.trail_threshold(_runs(rows))
    assert 25 <= value <= 35 and "fitted" in source


def test_trail_threshold_falls_back_without_enough_tagged_runs():
    value, source = bands.trail_threshold(_runs([("Run", 2020, 10), ("TrailRun", 2020, 40)]))
    assert value == bands.TRAIL_FALLBACK_M_PER_KM and "chosen" in source


def test_surfaces_trust_the_sport_and_fall_back_only_in_untagged_years():
    runs = _runs([("Run", 2020, 45), ("Run", 2020, 5), ("Run", 2024, 45), ("TrailRun", 2024, 10)])
    assert list(bands.surfaces(runs, 30)) == ["trail", "road", "road", "trail"]


def _laps(aid, laps):
    return pd.DataFrame([(aid, i, d, t, hr) for i, (d, t, hr) in enumerate(laps)],
                        columns=["activity_id", "lap", "distance_m", "duration_s", "hr"])


def _splits(aid, splits):
    return pd.DataFrame([(aid, i + 1, d, t, g) for i, (d, t, g) in enumerate(splits)],
                        columns=["activity_id", "split", "distance_m", "duration_s", "gap_s_km"])


def test_core_drops_warm_up_and_cool_down():
    laps = _laps("a", [(1000, 360, 110), (1000, 300, 140), (1000, 300, 150), (500, 200, 120)])
    splits = _splits("a", [(1000, 360, 360), (1000, 300, 300), (1000, 300, 290), (500, 200, 400)])
    row = bands.core_stats(laps, splits).set_index("activity_id").loc["a"]
    assert row.core_hr == pytest.approx(145)                 # laps 2 and 3 only
    assert row.gap_pace_min_km == pytest.approx(295 / 60)    # splits 2 and 3 only
    assert not row.workout_laps                              # 1 km auto-laps


def test_core_keeps_every_row_of_a_short_run_and_no_gap_means_none():
    laps = _laps("b", [(1000, 300, 130), (800, 240, 140)])
    splits = _splits("b", [(1000, 300, None), (800, 240, 300)])
    row = bands.core_stats(laps, splits).set_index("activity_id").loc["b"]
    assert row.core_hr == pytest.approx((130 * 300 + 140 * 240) / 540)
    assert pd.isna(row.gap_pace_min_km) and row.raw_pace_min_km == pytest.approx(5.0)


def test_workout_laps_with_spread_are_flagged():
    reps = [(2000, 660, 120)] + [(400, 90, 155), (400, 150, 135)] * 4 + [(1000, 330, 125)]
    row = bands.core_stats(_laps("c", reps), _splits("c", [(1000, 300, 300)] * 5)) \
        .set_index("activity_id").loc["c"]
    assert row.workout_laps and row.lap_cv > bands.MAX_LAP_CV


def test_band_runs_on_the_fixture_gives_a_reason_or_a_band(cfg):
    runs = bands.band_runs(cfg=cfg, today=TODAY)
    assert len(runs) and set(runs["surface_band"]) <= {"road", "trail"}
    kept = runs[runs["excluded"].isna()]
    assert kept["band"].notna().all() and kept["speed_per_beat"].gt(0).all()
    assert (runs.loc[runs["excluded"].notna(), "excluded"].isin(
        ["race", "intervals", "short", "no heart rate", "no grade-adjusted pace (hilly or trail)",
         "unsteady (workout laps)"])).all()


def _band_rows():
    return pd.DataFrame({
        "activity_id": list("abcd"), "date": pd.to_datetime(["2024-09-01", "2024-09-10",
                                                             "2024-03-01", "2025-09-05"]),
        "year": [2024, 2024, 2024, 2025], "month": pd.to_datetime(["2024-09-01"] * 2
                                                                   + ["2024-03-01", "2025-09-01"]),
        "surface_band": ["road"] * 4, "distance_km": [10.0, 8.0, 12.0, 10.0],
        "temp_c": [20.0, 22.0, 10.0, 21.0], "core_hr": [140.0, 144.0, 138.0, 132.0],
        "hr_pct_max": [80.0, 82.0, 79.0, 75.0], "pace_min_km": [5.2, 5.3, 5.4, 5.2],
        "band": ["5:00–5:30"] * 4, "speed_per_beat": [1.37, 1.31, 1.35, 1.46],
        "excluded": [None, None, None, None]})


def test_band_table_per_year_with_season_and_noisy_flag():
    table = bands.band_table(_band_rows(), "year", season=(9,))
    assert list(table["period"]) == [2024, 2025]
    first = table.iloc[0]
    assert first.n_runs == 2 and first.mean_hr == 142 and first.km == 18 and first.noisy
    assert bands.band_table(_band_rows(), "year").iloc[0].n_runs == 3


def test_band_table_rejects_other_periods():
    with pytest.raises(ValueError):
        bands.band_table(_band_rows(), "week")


def test_yearly_efficiency_weights_months_by_run_count(monkeypatch, cfg):
    monthly = pd.DataFrame({"month": pd.to_datetime(["2024-01-01", "2024-09-01", "2025-09-01"]),
                            "efficiency": [1.0, 2.0, 1.5], "n_runs": [1, 3, 2],
                            "median_pace_min_km": [6.0, 5.5, 5.8]})
    monkeypatch.setattr(bands, "aerobic_efficiency", lambda **kw: monthly)
    out = bands.yearly_efficiency(cfg=cfg).set_index("year")
    assert out.loc[2024, "efficiency"] == pytest.approx((1.0 + 6.0) / 4)
    assert bands.yearly_efficiency(cfg=cfg, season=(9,)).set_index("year") \
        .loc[2024, "efficiency"] == pytest.approx(2.0)


def test_intensity_yearly_shares_sum_to_100(cfg, tmp_path):
    acts = activities(cfg=replace(cfg, garmin_activities=write_garmin_csv(tmp_path / "g.csv")))
    out = bands.intensity_yearly(activities=acts)
    assert len(out)
    assert (out[["easy_pct", "steady_pct", "hard_pct"]].sum(axis=1).round(6) == 100).all()


def test_intensity_yearly_without_garmin_is_empty(cfg):
    assert bands.intensity_yearly(activities=activities(cfg=cfg)).empty


def test_report_by_band_has_every_section(cfg, tmp_path):
    full = replace(cfg, garmin_activities=write_garmin_csv(tmp_path / "g.csv"))
    text = report.fitness_by_band(12, cfg=full, today=TODAY, first_year=2020)
    assert text.startswith("FITNESS BY PACE BAND, 2020 to 2026, all months")
    assert "Watch and HR sensor per year" in text and "Forerunner 965" in text
    for heading in ("Road, per year", "Trail, per year", "Per month", "Aerobic efficiency per year",
                    "Intensity mix per year", "- runs: "):
        assert heading in text


def test_report_by_band_names_the_hr_sensor_when_configured(cfg):
    from datetime import date
    text = report.fitness_by_band(12, cfg=replace(cfg, hr_sensors=((date(2000, 1, 1), "strap 1"),)),
                                  today=TODAY, first_year=2020)
    assert "; HR strap 1 100 %" in text and "wrist HR" not in text
    text = report.fitness_by_band(12, cfg=replace(cfg, hr_sensors=((date(2000, 1, 1), "strap 1"),),
                                                  hr_sensors_worn="hard"),
                                  today=TODAY, first_year=2020)
    assert "worn on hard runs only" in text


def test_report_cli_by_band_and_bad_season(cfg, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(report, "fitness_by_band",
                        lambda months, **kw: seen.update(months=months, **kw) or "BANDS")
    assert report.main(["fitness", "--by-band", "--season", "9-10", "--from-year", "2021"]) == 0
    assert seen == {"months": 12, "first_year": 2021, "season": (9, 10)}
    assert capsys.readouterr().out.strip() == "BANDS"
    with pytest.raises(SystemExit):
        report.main(["fitness", "--by-band", "--season", "13"])


def test_charts_build():
    table = bands.band_table(_band_rows(), "year")
    assert len(charts.band_hr_lines(table, bands.PACE_BANDS).data) == 2
    eff = pd.DataFrame({"year": [2024, 2025], "efficiency": [1.3, 1.4], "n_runs": [10, 12],
                        "n_months": [8, 9]})
    assert len(charts.efficiency_year_bars(eff).data) == 1
    mix = pd.DataFrame({"year": [2024], "easy_pct": [20.0], "steady_pct": [50.0],
                        "hard_pct": [30.0]})
    assert len(charts.intensity_share_bars(mix).data) == 3
