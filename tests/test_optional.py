import dataclasses
import os
import time

import pandas as pd
import pytest

from myrun import optional
from myrun.activities import activities, runs
from tests.fixture import (HILLY, RACE, RACE_COLUMNS, STEADY, TODAY, TRAIL, write_garmin, write_garmin_csv,
                           write_plan, write_races, write_wellness)


def with_inputs(cfg, **kwargs):
    return dataclasses.replace(cfg, **kwargs)


def _age(path, hours):
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


# ---- states ---------------------------------------------------------------

def test_everything_off_by_default(cfg):
    states = optional.input_states(cfg, today=TODAY)
    assert states["strava_db"].status == "ok"
    assert [states[k].status for k in ("wellness", "plan", "race_log", "garmin_activities")] == [
        "off"] * 4
    assert optional.read_wellness(cfg)[0] is None


def test_wellness_ok_stale_missing_and_malformed(cfg, tmp_path):
    path = write_wellness(tmp_path / "w.parquet")
    c = with_inputs(cfg, wellness_parquet=path)
    df, state = optional.read_wellness(c)
    assert state.status == "ok" and len(df) == 30
    assert df["date"].max() == pd.Timestamp(TODAY)

    _age(path, 50)
    df, state = optional.read_wellness(c)
    assert state.status == "stale" and df is not None
    assert "50" in state.message and state.age_hours == pytest.approx(50, abs=0.1)

    df, state = optional.read_wellness(with_inputs(cfg, wellness_parquet=tmp_path / "gone.parquet"))
    assert state.status == "error" and df is None and "not found" in state.message

    bad = tmp_path / "bad.parquet"
    pd.DataFrame({"day": ["2026-10-01"], "readiness": [70]}).to_parquet(bad)
    df, state = optional.read_wellness(with_inputs(cfg, wellness_parquet=bad))
    assert state.status == "error" and df is None and "date" in state.message

    junk = tmp_path / "junk.parquet"
    junk.write_bytes(b"nope")
    assert optional.read_wellness(with_inputs(cfg, wellness_parquet=junk))[1].status == "error"


def test_plan_ok_stale_and_malformed(cfg, tmp_path):
    path = write_plan(tmp_path / "plan.csv")
    c = with_inputs(cfg, plan_csv=path)
    df, state = optional.read_plan(c, today=TODAY)
    assert state.status == "ok"
    assert df["type"].tolist() == ["intervals", "easy", "rest", "long", "race"]
    assert df["distance_km"].iloc[0] == 10.0 and pd.isna(df["distance_km"].iloc[2])

    df, state = optional.read_plan(c, today="2027-03-01")     # nothing planned that week
    assert state.status == "stale" and df is not None and "week" in state.message

    bad = tmp_path / "bad.csv"
    bad.write_text("date,session,type,distance_km\nnot-a-date,Easy,easy,5\n")
    df, state = optional.read_plan(with_inputs(cfg, plan_csv=bad), today=TODAY)
    assert state.status == "error" and df is None

    nocol = tmp_path / "nocol.csv"
    nocol.write_text("day,what\n2026-10-05,Easy\n")
    assert "date" in optional.read_plan(with_inputs(cfg, plan_csv=nocol), today=TODAY)[1].message


def test_races_with_column_mapping(cfg, tmp_path):
    c = with_inputs(cfg, race_log_csv=write_races(tmp_path / "r.csv"),
                    race_log_columns=RACE_COLUMNS)
    df, state = optional.read_races(c)
    assert state.status == "ok"
    row = df.iloc[0]
    assert row["name"] == "Test 10K"
    assert row["date"] == pd.Timestamp(TODAY) - pd.Timedelta(days=15)
    assert row["official_time_s"] == 2700
    assert row["rank_pct"] == pytest.approx(14.97)
    assert row["distance_km"] == 10.0

    wrong = with_inputs(c, race_log_columns={"name": "Name", "date": "date"})
    assert "Name" in optional.read_races(wrong)[1].message
    unmapped = with_inputs(c, race_log_columns={})
    assert optional.read_races(unmapped)[1].status == "error"


# ---- enrichment -----------------------------------------------------------

def _types(c):
    return activities(cfg=c).set_index("activity_id")["session_type"].to_dict()


def test_without_inputs_only_strava_workout_type_is_used(cfg):
    types = _types(cfg)
    assert types[RACE] == "race"
    assert types[STEADY] is None and types[HILLY] is None
    assert "ground_contact_ms" not in runs(cfg=cfg).columns
    assert "garmin_activity_id" not in runs(cfg=cfg).columns


def test_garmin_join_by_start_time(cfg, tmp_path):
    c = with_inputs(cfg, garmin_activities=write_garmin(tmp_path / "g.parquet"))
    df = runs(cfg=c).set_index("activity_id")
    assert df.loc[STEADY, "garmin_activity_id"] == 111        # 30 s apart: matched
    assert df.loc[STEADY, "ground_contact_ms"] == 250.0
    assert df.loc[STEADY, "session_type"] == "tempo"
    assert pd.isna(df.loc[HILLY, "garmin_activity_id"])       # 10 min apart: not matched
    assert pd.isna(df.loc[HILLY, "ground_contact_ms"])
    assert len(df) == 6                                       # the join never adds rows


def test_session_type_precedence(cfg, tmp_path):
    c = with_inputs(cfg, plan_csv=write_plan(tmp_path / "p.csv"),
                    garmin_activities=write_garmin(tmp_path / "g.parquet"))
    types = _types(c)
    assert types[STEADY] == "tempo"         # Garmin wins over the plan's "easy"
    assert types[HILLY] == "intervals"      # from the plan, by date
    assert types[RACE] == "race"            # from Strava's workout type
    assert types[TRAIL] is None


def test_race_log_sets_surface_and_name(cfg, tmp_path):
    c = with_inputs(cfg, race_log_csv=write_races(tmp_path / "r.csv"),
                    race_log_columns=RACE_COLUMNS)
    row = activities(cfg=c).set_index("activity_id").loc[RACE]
    assert row["surface"] == "mixed"        # hilliness alone would say road
    assert row["race_name"] == "Test 10K"
    assert row["session_type"] == "race"


def test_a_broken_optional_file_does_not_break_activities(cfg, tmp_path):
    junk = tmp_path / "junk.parquet"
    junk.write_bytes(b"nope")
    c = with_inputs(cfg, garmin_activities=junk, plan_csv=tmp_path / "absent.csv")
    assert len(activities(cfg=c)) == 7


def test_input_status_table(cfg):
    table = optional.input_status(cfg=cfg)
    assert table["name"].tolist() == ["strava_db", "wellness", "plan", "race_log",
                                      "garmin_activities"]
    assert table["status"].tolist() == ["ok", "off", "off", "off", "off"]


def test_strava_db_goes_stale(cfg):
    _age(cfg.strava_db, 40)
    state = optional.input_states(cfg, today=TODAY)["strava_db"]
    assert state.status == "stale" and "40" in state.message


def _wellness_file(tmp_path, frame):
    path = tmp_path / "custom.parquet"
    frame.to_parquet(path)
    return path


def test_wellness_with_no_readable_dates_is_an_error(cfg, tmp_path):
    path = _wellness_file(tmp_path, pd.DataFrame({"date": ["soon", "later"], "readiness": [70, 71]}))
    df, state = optional.read_wellness(with_inputs(cfg, wellness_parquet=path))
    assert df is None and state.status == "error" and "date" in state.message


def test_wellness_without_any_known_metric_is_an_error_naming_them(cfg, tmp_path):
    path = _wellness_file(tmp_path, pd.DataFrame({"date": ["2026-10-01"], "steps": [8000]}))
    df, state = optional.read_wellness(with_inputs(cfg, wellness_parquet=path))
    assert df is None and state.status == "error"
    assert "readiness" in state.message and "hrv_ms" in state.message


def test_wellness_is_normalised(cfg, tmp_path):
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-10-01 22:00", "2026-10-02 22:00"]).tz_localize("Europe/Madrid"),
        "readiness": ["70", "n/a"],
    })
    df, state = optional.read_wellness(with_inputs(cfg, wellness_parquet=_wellness_file(tmp_path, frame)))
    assert state.status == "ok"
    assert df["date"].tolist() == list(pd.to_datetime(["2026-10-01", "2026-10-02"]))
    assert df["date"].dt.tz is None
    assert df["readiness"].iloc[0] == 70.0 and pd.isna(df["readiness"].iloc[1])
    assert df["readiness"].mean() == 70.0


def test_garmin_start_with_a_timezone_is_an_error(cfg, tmp_path):
    path = tmp_path / "tz.parquet"
    pd.DataFrame({"start": pd.to_datetime(["2026-10-04 05:30"]).tz_localize("UTC"),
                  "garmin_activity_id": [1]}).to_parquet(path)
    df, state = optional.read_garmin_activities(with_inputs(cfg, garmin_activities=path))
    assert df is None and state.status == "error" and "timezone" in state.message


def test_wellness_column_mapping(cfg, tmp_path):
    frame = pd.DataFrame({"local_date": ["2026-10-04", "2026-10-05"],
                          "readiness_score": [70.0, 81.0], "hrv_last_night_ms": [48.0, 52.0],
                          "resting_hr": [47.0, 46.0], "sleep_s": [27000.0, 25200.0],
                          "steps": [9000, 12000]})
    mapping = {"date": "local_date", "readiness": "readiness_score",
               "hrv_ms": "hrv_last_night_ms", "resting_hr": "resting_hr",
               "sleep_seconds": "sleep_s"}
    c = with_inputs(cfg, wellness_parquet=_wellness_file(tmp_path, frame),
                    wellness_columns=mapping)
    df, state = optional.read_wellness(c)
    assert state.status == "ok"
    assert df["date"].tolist() == list(pd.to_datetime(["2026-10-04", "2026-10-05"]))
    assert df["readiness"].tolist() == [70.0, 81.0]
    assert df["hrv_ms"].tolist() == [48.0, 52.0]
    assert df["sleep_hours"].tolist() == [7.5, 7.0]


def test_wellness_mapping_naming_an_absent_column_is_an_error(cfg, tmp_path):
    frame = pd.DataFrame({"local_date": ["2026-10-05"], "readiness_score": [70.0]})
    c = with_inputs(cfg, wellness_parquet=_wellness_file(tmp_path, frame),
                    wellness_columns={"date": "local_date", "hrv_ms": "hrv_nightly"})
    df, state = optional.read_wellness(c)
    assert df is None and state.status == "error" and "hrv_nightly" in state.message


def test_garmin_csv_is_read_like_parquet(cfg, tmp_path):
    c = with_inputs(cfg, garmin_activities=write_garmin_csv(tmp_path / "g.csv"))
    df = runs(cfg=c).set_index("activity_id")
    assert df.loc[STEADY, "garmin_activity_id"] == 111
    assert df.loc[STEADY, "session_name"] == "Tempo 7km"
    assert df.loc[STEADY, "session_type"] == "tempo"
    assert df.loc[STEADY, "power_w"] == 340.0
    assert df.loc[STEADY, "vertical_ratio_pct"] == 8.8
    assert pd.isna(df.loc[HILLY, "garmin_activity_id"])       # 10 min apart: not matched


def test_garmin_values_that_are_not_numbers_become_missing(cfg, tmp_path):
    c = with_inputs(cfg, garmin_activities=write_garmin_csv(tmp_path / "g.csv"))
    df, state = optional.read_garmin_activities(c)
    assert state.status == "ok"
    junk = df.set_index("garmin_activity_id").loc[222]        # rows are sorted by start
    assert pd.isna(junk["ground_contact_ms"])                 # "--" in the file
    assert pd.isna(junk["power_w"])                           # blank in the file
    assert df["ground_contact_ms"].dtype == "float64"
    assert junk["session_type"] is None or pd.isna(junk["session_type"])


def test_garmin_file_with_an_unknown_suffix_is_an_error(cfg, tmp_path):
    path = tmp_path / "g.txt"
    path.write_text("start\n")
    df, state = optional.read_garmin_activities(with_inputs(cfg, garmin_activities=path))
    assert df is None and state.status == "error" and ".csv or .parquet" in state.message


def test_a_garmin_file_with_a_header_and_no_readable_rows_is_an_error(cfg, tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("start,garmin_activity_id,session_name\nnot a date,1,x\n")
    df, state = optional.read_garmin_activities(with_inputs(cfg, garmin_activities=path))
    assert df is None and state.status == "error" and "no rows" in state.message


def test_plan_carries_surface_and_climb_when_the_file_has_them(cfg, tmp_path):
    path = tmp_path / "plan.csv"
    path.write_text("date,session,type,distance_km,surface,elevation_m\n"
                    f"{TODAY},Hill race,race,20,Trail,900\n")
    plan, _ = optional.read_plan(with_inputs(cfg, plan_csv=path), today=TODAY)
    assert plan.loc[0, "surface"] == "trail" and plan.loc[0, "elevation_m"] == 900.0
    path.write_text(f"date,session,type\n{TODAY},Easy,easy\n")
    plan, _ = optional.read_plan(with_inputs(cfg, plan_csv=path), today=TODAY)
    assert plan.loc[0, "surface"] is None and pd.isna(plan.loc[0, "elevation_m"])
