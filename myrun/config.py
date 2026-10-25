"""Configuration: one YAML file kept outside the repo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

DEFAULT_CONFIG = "~/dockers/myrun/config.yaml"
RUN_SPORTS = ("Run", "TrailRun")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    strava_db: Path
    cache_dir: Path = Path(os.path.expanduser("~/.cache/myrun"))
    wellness_parquet: Path | None = None
    plan_csv: Path | None = None
    race_log_csv: Path | None = None
    garmin_activities: Path | None = None
    race_log_columns: dict[str, str] = field(default_factory=dict)
    race_log_date_format: str = "%d/%m/%Y"
    wellness_columns: dict[str, str] = field(default_factory=dict)
    sfs_url: str | None = None
    max_hr: int | None = None                           # None: observed from recent runs
    hr_zone_upper_bounds: tuple[int, ...] | None = None  # None: calculated from max_hr
    easy_hr_band: tuple[int, int] | None = None          # None: calculated from max_hr
    hr_sensors: tuple[tuple[date, str], ...] = ()        # (in use from, name), oldest first
    hr_sensors_worn: str = "all"                        # "hard": only on hard runs, the rest is wrist HR
    mixed_hilliness_m_per_km: float | None = None        # None: surface is the sport type only
    efficiency_max_hilliness_m_per_km: float = 20.0
    grade_class_m_per_km: float = 20.0
    load_bands: tuple[float, float, float] = (0.8, 1.3, 1.5)
    stale_hours: float = 36.0
    garmin_join_tolerance_s: int = 120
    device_owned_from: dict[str, date] = field(default_factory=dict)  # device -> first day it was yours


_TOP = {"strava_db", "cache_dir", "inputs", "race_log_columns", "race_log_date_format", "wellness_columns", "links",
        "hr", "thresholds", "devices"}
_INPUTS = {"wellness_parquet", "plan_csv", "race_log_csv", "garmin_activities"}
_OLD_INPUTS = {"garmin_activities_parquet": "garmin_activities"}   # still accepted
_LINKS = {"statistics_for_strava_url"}
_HR = {"max_hr", "zone_upper_bounds", "easy_band", "sensors", "sensors_worn"}
_THRESHOLDS = {"mixed_hilliness_m_per_km", "efficiency_max_hilliness_m_per_km",
               "grade_class_m_per_km", "load_bands", "stale_hours", "garmin_join_tolerance_s"}

WELLNESS_FIELDS = ("date", "readiness", "sleep_hours", "sleep_seconds", "hrv_ms", "resting_hr",
                   "body_battery", "stress", "sleep_score", "deep_sleep_seconds",
                   "rem_sleep_seconds", "hrv_status")


def _path(value) -> Path | None:
    return Path(os.path.expanduser(str(value))) if value else None


def _section(raw: dict, name: str, allowed: set[str], source: Path) -> dict:
    section = raw.get(name) or {}
    if not isinstance(section, dict):
        raise ConfigError(f"{source}: '{name}' must be a mapping")
    unknown = sorted(set(section) - allowed)
    if unknown:
        raise ConfigError(f"{source}: unknown key(s) in '{name}': {', '.join(unknown)}")
    return section


def _sensors(items, source: Path) -> tuple[tuple[date, str], ...]:
    out = []
    for item in items if isinstance(items, list) else [items]:
        since = item.get("since") if isinstance(item, dict) else None
        if not isinstance(since, date) or not item.get("name"):
            raise ConfigError(f"{source}: each 'hr.sensors' entry needs since: YYYY-MM-DD and name")
        out.append((since, str(item["name"])))
    return tuple(sorted(out))


def _devices(items, source: Path) -> dict[str, date]:
    """Watches bought second hand: activities recorded on them before `owned_from` belong
    to the previous owner (they sync into the account when the watch is first paired)."""
    out = {}
    for item in items if isinstance(items, list) else [items]:
        owned = item.get("owned_from") if isinstance(item, dict) else None
        if not isinstance(owned, date) or not item.get("name"):
            raise ConfigError(f"{source}: each 'devices' entry needs name and owned_from: YYYY-MM-DD")
        out[str(item["name"])] = owned
    return out


def load_config(path: str | Path | None = None) -> Config:
    source = Path(os.path.expanduser(str(path or os.environ.get("MYRUN_CONFIG") or DEFAULT_CONFIG)))
    if not source.is_file():
        raise ConfigError(f"config file not found: {source}")
    raw = yaml.safe_load(source.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: the file must contain a mapping")
    unknown = sorted(set(raw) - _TOP)
    if unknown:
        raise ConfigError(f"{source}: unknown key(s): {', '.join(unknown)}")
    if not raw.get("strava_db"):
        raise ConfigError(f"{source}: 'strava_db' is required")

    inputs = _section(raw, "inputs", _INPUTS | set(_OLD_INPUTS), source)
    links = _section(raw, "links", _LINKS, source)
    hr = _section(raw, "hr", _HR, source)
    thresholds = _section(raw, "thresholds", _THRESHOLDS, source)

    kwargs: dict = {"strava_db": _path(raw["strava_db"])}
    if raw.get("cache_dir"):
        kwargs["cache_dir"] = _path(raw["cache_dir"])
    for old, new in _OLD_INPUTS.items():
        if inputs.get(old):
            if inputs.get(new):
                raise ConfigError(f"{source}: set '{new}' or '{old}' in 'inputs', not both")
            inputs = {**inputs, new: inputs[old]}
    for key in _INPUTS:
        kwargs[key] = _path(inputs.get(key))
    if raw.get("race_log_columns"):
        kwargs["race_log_columns"] = dict(raw["race_log_columns"])
    if raw.get("race_log_date_format"):
        kwargs["race_log_date_format"] = str(raw["race_log_date_format"])
    if raw.get("wellness_columns"):
        mapping = dict(raw["wellness_columns"])
        unknown = sorted(set(mapping) - set(WELLNESS_FIELDS))
        if unknown:
            raise ConfigError(f"{source}: unknown field(s) in 'wellness_columns': "
                              f"{', '.join(unknown)}; allowed: {', '.join(WELLNESS_FIELDS)}")
        kwargs["wellness_columns"] = mapping
    if links.get("statistics_for_strava_url"):
        kwargs["sfs_url"] = str(links["statistics_for_strava_url"]).rstrip("/")
    if hr.get("max_hr"):
        kwargs["max_hr"] = int(hr["max_hr"])
    if hr.get("zone_upper_bounds"):
        kwargs["hr_zone_upper_bounds"] = tuple(int(v) for v in hr["zone_upper_bounds"])
    if hr.get("easy_band"):
        low, high = hr["easy_band"]
        kwargs["easy_hr_band"] = (int(low), int(high))
    if hr.get("sensors"):
        kwargs["hr_sensors"] = _sensors(hr["sensors"], source)
    if hr.get("sensors_worn"):
        if hr["sensors_worn"] not in ("all", "hard"):
            raise ConfigError(f"{source}: 'hr.sensors_worn' must be 'all' or 'hard'")
        kwargs["hr_sensors_worn"] = hr["sensors_worn"]
    for key in _THRESHOLDS - {"load_bands", "garmin_join_tolerance_s"}:
        if thresholds.get(key) is not None:
            kwargs[key] = float(thresholds[key])
    if "load_bands" in thresholds:
        kwargs["load_bands"] = tuple(float(v) for v in thresholds["load_bands"])
    if "garmin_join_tolerance_s" in thresholds:
        kwargs["garmin_join_tolerance_s"] = int(thresholds["garmin_join_tolerance_s"])
    if raw.get("devices"):
        kwargs["device_owned_from"] = _devices(raw["devices"], source)
    return Config(**kwargs)
