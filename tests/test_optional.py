import dataclasses
import os
import time

import pandas as pd
import pytest

from myrun import optional
from myrun.activities import activities, runs
from tests.fixture import (HILLY, RACE, RACE_COLUMNS, STEADY, TODAY, TRAIL, write_garmin,
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
    c = with_inputs(cfg, garmin_activities_parquet=write_garmin(tmp_path / "g.parquet"))
    df = runs(cfg=c).set_index("activity_id")
    assert df.loc[STEADY, "garmin_activity_id"] == 111        # 30 s apart: matched
    assert df.loc[STEADY, "ground_contact_ms"] == 250.0
    assert df.loc[STEADY, "session_type"] == "tempo"
    assert pd.isna(df.loc[HILLY, "garmin_activity_id"])       # 10 min apart: not matched
    assert pd.isna(df.loc[HILLY, "ground_contact_ms"])
    assert len(df) == 6                                       # the join never adds rows


def test_session_type_precedence(cfg, tmp_path):
    c = with_inputs(cfg, plan_csv=write_plan(tmp_path / "p.csv"),
                    garmin_activities_parquet=write_garmin(tmp_path / "g.parquet"))
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
    c = with_inputs(cfg, garmin_activities_parquet=junk, plan_csv=tmp_path / "absent.csv")
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
