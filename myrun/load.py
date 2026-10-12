"""Training load from Strava relative effort, across all sports."""

from __future__ import annotations

from datetime import date

import pandas as pd

from myrun import derive
from myrun.activities import activities as _load
from myrun.config import Config, load_config


def _today(today) -> pd.Timestamp:
    return pd.Timestamp(today if today is not None else date.today()).normalize()


def weekly_load(weeks: int = 12, *, activities: pd.DataFrame | None = None, today=None,
                cfg: Config | None = None) -> pd.DataFrame:
    """Relative effort per week (Monday start), oldest first, the current week last."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    now = _today(today)
    this_monday = now - pd.Timedelta(days=now.weekday())
    all_weeks = pd.date_range(this_monday - pd.Timedelta(weeks=weeks - 1), periods=weeks, freq="7D")
    df = acts[(acts["date"] >= all_weeks[0]) & (acts["date"] <= now)].copy()
    df["week_start"] = df["date"] - pd.to_timedelta(df["date"].dt.weekday, unit="D")
    df["missing"] = df["relative_effort"].isna()
    grouped = df.groupby("week_start").agg(
        effort=("relative_effort", "sum"),
        n_activities=("activity_id", "count"),
        n_missing_effort=("missing", "sum"),
    )
    out = grouped.reindex(all_weeks, fill_value=0).rename_axis("week_start").reset_index()
    return out.astype({"effort": "float64", "n_activities": "int64", "n_missing_effort": "int64"})


def load_status(*, activities: pd.DataFrame | None = None, today=None,
                cfg: Config | None = None, column: str = "relative_effort") -> dict:
    """Last 7 days against the weekly average of the last 28 days (which include them).

    `column` is the per-activity load: Strava's relative effort, or `garmin_load`."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    now = _today(today)
    last28 = acts[(acts["date"] > now - pd.Timedelta(days=28)) & (acts["date"] <= now)]
    last7 = last28[last28["date"] > now - pd.Timedelta(days=7)]
    sum7 = float(last7[column].sum())
    avg_week = float(last28[column].sum()) / 4
    ratio = sum7 / avg_week if avg_week > 0 else None
    return {
        "last7": sum7,
        "avg_week_28": avg_week,
        "ratio": ratio,
        "label": derive.load_label(ratio, cfg.load_bands),
        "n_missing": int(last28[column].isna().sum()),
    }
