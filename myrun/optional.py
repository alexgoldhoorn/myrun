"""Optional inputs: wellness, plan, race log, Garmin activities.

Each reader returns (frame, state). The frame is None when the input is not configured
("off") or cannot be used ("error"); it is present for "ok" and "stale". Pages decide
what to show from the state; nothing here raises for a bad file.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from myrun.config import RUN_SPORTS, Config, load_config
from myrun.stravadb import db_mtime

WELLNESS_COLUMNS = ("readiness", "sleep_hours", "hrv_ms", "resting_hr", "body_battery", "stress")
GARMIN_NUMERIC = ("ground_contact_ms", "vertical_oscillation_cm", "vertical_ratio_pct",
                  "stride_length_m", "garmin_cadence_spm", "power_w", "aerobic_te",
                  "anaerobic_te", "garmin_load", "vo2max")
GARMIN_COLUMNS = ("garmin_activity_id", "session_name", "session_type", *GARMIN_NUMERIC)
RACE_TEXT = ("name", "place", "type", "garmin_url", "strava_url", "diploma_url")
NON_RUN_PLAN_TYPES = ("rest", "strength")
SURFACES = ("road", "mixed", "trail")
_WORKOUT_TYPES = {"race": "race", "longRun": "long"}


def none_if_missing(values) -> pd.Series:
    """An object column holding None (never NaN) for missing values."""
    index = values.index if isinstance(values, pd.Series) else None
    return pd.Series([None if pd.isna(v) else v for v in values], index=index, dtype="object")


@dataclass(frozen=True)
class InputState:
    name: str
    status: str            # off | ok | stale | error
    age_hours: float | None = None
    message: str = ""


def _age_hours(path: Path, now: float | None) -> float:
    return ((now if now is not None else time.time()) - path.stat().st_mtime) / 3600


def _naive(values: pd.Series) -> pd.Series:
    """Drop a timezone, keeping the wall-clock time the file states."""
    return values.dt.tz_localize(None) if values.dt.tz is not None else values


def _off(name: str) -> tuple[None, InputState]:
    return None, InputState(name, "off")


def _error(name: str, message: str) -> tuple[None, InputState]:
    return None, InputState(name, "error", None, message)


def _file_state(name: str, path: Path, cfg: Config, now: float | None) -> InputState:
    age = _age_hours(path, now)
    if age > cfg.stale_hours:
        return InputState(name, "stale", age,
                          f"last updated {age:.0f} hours ago (limit {cfg.stale_hours:.0f})")
    return InputState(name, "ok", age)


def read_wellness(cfg: Config, now: float | None = None):
    name, path = "wellness", cfg.wellness_parquet
    if path is None:
        return _off(name)
    if not path.is_file():
        return _error(name, f"file not found: {path.name}")
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        return _error(name, f"cannot read {path.name}: {exc}")
    if cfg.wellness_columns:
        absent = [src for src in cfg.wellness_columns.values() if src not in df.columns]
        if absent:
            return _error(name, f"{path.name} lacks mapped column(s): "
                                f"{', '.join(map(repr, absent))}")
        df = pd.DataFrame({field: df[src] for field, src in cfg.wellness_columns.items()})
    if "sleep_seconds" in df.columns and "sleep_hours" not in df.columns:
        df["sleep_hours"] = pd.to_numeric(df["sleep_seconds"], errors="coerce") / 3600
    if "date" not in df.columns:
        return _error(name, f"{path.name} has no 'date' column")
    present = [c for c in WELLNESS_COLUMNS if c in df.columns]
    if not present:
        return _error(name, f"{path.name} has none of the expected columns: "
                            f"{', '.join(WELLNESS_COLUMNS)}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # pandas warns when no format is inferable
        dates = pd.to_datetime(df["date"], errors="coerce")
    df["date"] = _naive(dates).dt.normalize()
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if df.empty:
        return _error(name, f"{path.name} has no rows with a readable date")
    for column in present:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype("float64")
    return df, _file_state(name, path, cfg, now)


def read_plan(cfg: Config, today=None):
    name, path = "plan", cfg.plan_csv
    if path is None:
        return _off(name)
    if not path.is_file():
        return _error(name, f"file not found: {path.name}")
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception as exc:
        return _error(name, f"cannot read {path.name}: {exc}")
    missing = [c for c in ("date", "session", "type") if c not in df.columns]
    if missing:
        return _error(name, f"{path.name} lacks column(s): {', '.join(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"])
    if df.empty:
        return _error(name, f"{path.name} has no rows with a readable date")
    df["type"] = df["type"].fillna("").str.strip().str.lower()
    df["session"] = df["session"].fillna("").str.strip()
    distance = df["distance_km"] if "distance_km" in df.columns else pd.Series(pd.NA, df.index)
    df["distance_km"] = pd.to_numeric(distance, errors="coerce").astype("float64")
    df = df[["date", "session", "type", "distance_km"]].sort_values("date").reset_index(drop=True)

    now = pd.Timestamp(today if today is not None else date.today()).normalize()
    monday = now - pd.Timedelta(days=now.weekday())
    in_week = df["date"].between(monday, monday + pd.Timedelta(days=6))
    if not in_week.any():
        return df, InputState(name, "stale", None, "no sessions planned for the current week")
    return df, InputState(name, "ok")


def read_races(cfg: Config):
    name, path = "race_log", cfg.race_log_csv
    if path is None:
        return _off(name)
    if not path.is_file():
        return _error(name, f"file not found: {path.name}")
    mapping = cfg.race_log_columns
    if "name" not in mapping or "date" not in mapping:
        return _error(name, "race_log_columns must map at least 'name' and 'date'")
    try:
        raw = pd.read_csv(path, dtype=str)
    except Exception as exc:
        return _error(name, f"cannot read {path.name}: {exc}")
    absent = [src for src in mapping.values() if src not in raw.columns]
    if absent:
        return _error(name, f"{path.name} lacks mapped column(s): {', '.join(map(repr, absent))}")

    df = pd.DataFrame({field: raw[src].str.strip() for field, src in mapping.items()})
    df["date"] = pd.to_datetime(df["date"], format=cfg.race_log_date_format, errors="coerce")
    df = df.dropna(subset=["date"])
    if df.empty:
        return _error(name, f"no dates in {path.name} match {cfg.race_log_date_format!r}")
    for column in ("distance_km", "elevation_m"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce").astype("float64")
    if "rank_pct" in df:
        df["rank_pct"] = pd.to_numeric(df["rank_pct"].str.rstrip("%"), errors="coerce")
    if "official_time" in df:
        df["official_time_s"] = pd.to_timedelta(df.pop("official_time"),
                                                errors="coerce").dt.total_seconds()
    if "type" in df:
        df["type"] = df["type"].str.lower()
    return df.sort_values("date").reset_index(drop=True), InputState(name, "ok")


def read_garmin_activities(cfg: Config, now: float | None = None):
    name, path = "garmin_activities", cfg.garmin_activities
    if path is None:
        return _off(name)
    if not path.is_file():
        return _error(name, f"file not found: {path.name}")
    suffix = path.suffix.lower()
    if suffix not in (".csv", ".parquet"):
        return _error(name, f"{path.name} must be a .csv or .parquet file")
    try:
        df = pd.read_csv(path, dtype=str) if suffix == ".csv" else pd.read_parquet(path)
    except Exception as exc:
        return _error(name, f"cannot read {path.name}: {exc}")
    if "start" not in df.columns:
        return _error(name, f"{path.name} has no 'start' column")
    start = pd.to_datetime(df["start"], errors="coerce")
    if start.dt.tz is not None:
        return _error(name, f"'start' in {path.name} carries a timezone; it must be the local "
                            "wall-clock time without one, as Strava records it")
    df["start"] = start.astype("datetime64[ns]")
    for column in (*GARMIN_NUMERIC, "garmin_activity_id"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").astype("float64")
    for column in ("session_name", "session_type"):
        if column in df.columns:
            text = df[column].astype("string").str.strip()
            df[column] = none_if_missing(text.where(text != "", None))
    df = df.dropna(subset=["start"]).sort_values("start").reset_index(drop=True)
    return df, _file_state(name, path, cfg, now)


def input_states(cfg: Config, today=None, now: float | None = None) -> dict[str, InputState]:
    try:
        changed = db_mtime(cfg.strava_db).timestamp()
        age = ((now if now is not None else time.time()) - changed) / 3600
        if age > cfg.stale_hours:
            strava = InputState("strava_db", "stale", age,
                                f"the activity database was last updated {age:.0f} hours ago")
        else:
            strava = InputState("strava_db", "ok", age)
    except OSError as exc:
        strava = InputState("strava_db", "error", None, str(exc))
    return {
        "strava_db": strava,
        "wellness": read_wellness(cfg, now)[1],
        "plan": read_plan(cfg, today)[1],
        "race_log": read_races(cfg)[1],
        "garmin_activities": read_garmin_activities(cfg, now)[1],
    }


def input_status(*, cfg: Config | None = None) -> pd.DataFrame:
    """Age and state of every input, as a table."""
    states = input_states(cfg or load_config())
    return pd.DataFrame([asdict(s) for s in states.values()])


def enrich(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add session_type, race_name and (when available) Garmin columns to activities."""
    df = df.reset_index(drop=True).copy()
    df["session_type"] = None
    df["race_name"] = None
    if df.empty:
        return df
    is_run = df["sport"].isin(RUN_SPORTS)

    garmin, _ = read_garmin_activities(cfg)
    if garmin is not None and len(garmin):
        extra = [c for c in GARMIN_COLUMNS if c in garmin.columns]
        right = garmin[["start", *extra]].rename(columns={"session_type": "_garmin_type"})
        left = df[["activity_id", "start"]].copy()
        left["start"] = left["start"].astype("datetime64[ns]")
        matched = pd.merge_asof(
            left.sort_values("start"), right, on="start", direction="nearest",
            tolerance=pd.Timedelta(seconds=cfg.garmin_join_tolerance_s),
        ).drop(columns="start")
        df = df.merge(matched, on="activity_id", how="left")
        if "_garmin_type" in df:
            garmin_type = df.pop("_garmin_type")
            df["session_type"] = none_if_missing(garmin_type)

    plan, _ = read_plan(cfg)
    if plan is not None:
        by_date = (plan[~plan["type"].isin(NON_RUN_PLAN_TYPES) & (plan["type"] != "")]
                   .drop_duplicates("date").set_index("date")["type"])
        fill = is_run & df["session_type"].isna()
        df.loc[fill, "session_type"] = df.loc[fill, "date"].map(by_date)

    fill = is_run & df["session_type"].isna()
    df.loc[fill, "session_type"] = df.loc[fill, "workout_type"].map(_WORKOUT_TYPES)
    df["session_type"] = none_if_missing(df["session_type"])

    races, _ = read_races(cfg)
    if races is not None and "distance_km" in races:
        for race in races.itertuples(index=False):
            candidates = df[is_run & (df["date"] == race.date)]
            if candidates.empty or pd.isna(race.distance_km):
                continue
            gap = (candidates["distance_km"] - race.distance_km).abs()
            best = gap.idxmin()
            if gap[best] > 0.2 * race.distance_km:
                continue
            df.loc[best, "race_name"] = race.name
            df.loc[best, "session_type"] = "race"
            race_type = getattr(race, "type", None)
            if race_type in SURFACES:
                df.loc[best, "surface"] = race_type
    return df
