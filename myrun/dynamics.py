"""Running dynamics from the Garmin feed: per activity and over time."""

from __future__ import annotations

import pandas as pd

from myrun.activities import activities as _load
from myrun.config import Config, load_config
from myrun.metric import Metric, clean
from myrun.trends import easy_runs

# column: (label, unit)
DYNAMICS: dict[str, tuple[str, str]] = {
    "ground_contact_ms": ("Ground contact", "ms"),
    "vertical_oscillation_cm": ("Vertical oscillation", "cm"),
    "vertical_ratio_pct": ("Vertical ratio", "pct"),
    "stride_length_m": ("Stride length", "metres"),
    "power_w": ("Power", "w"),
    "aerobic_te": ("Aerobic training effect", "te"),
}
BASELINE_DAYS = 90


def available(activities: pd.DataFrame) -> list[str]:
    """The dynamics columns that exist and hold at least one value."""
    return [c for c in DYNAMICS if c in activities.columns and activities[c].notna().any()]


def activity_dynamics(row: pd.Series, runs: pd.DataFrame, days: int = BASELINE_DAYS) -> list[Metric]:
    """One Metric per dynamics value this run has, against earlier runs on the same surface."""
    out = []
    surface = row.get("surface")
    earlier = runs[(runs["start"] < row["start"])
                   & (runs["start"] >= row["start"] - pd.Timedelta(days=days))]
    if surface is not None and not pd.isna(surface) and "surface" in runs.columns:
        earlier = earlier[earlier["surface"] == surface]
    for column, (label, unit) in DYNAMICS.items():
        value = clean(row.get(column))
        if value is None:
            continue
        history = earlier[column].dropna() if column in earlier.columns else pd.Series(dtype=float)
        if history.empty:
            previous, note = None, "no earlier runs to compare"
        else:
            previous = float(history.median())
            kind = f"{surface} " if isinstance(surface, str) else ""
            note = f"vs median of {len(history)} {kind}runs, {days} days"
        out.append(Metric(column, label, value, previous, unit, note=note))
    return out


def dynamics_trend(column: str, *, activities: pd.DataFrame | None = None,
                   cfg: Config | None = None) -> pd.DataFrame:
    """Monthly median of one dynamics column on easy runs, from the first month with data."""
    if column not in DYNAMICS:
        raise ValueError(f"column must be one of {', '.join(DYNAMICS)}; got {column!r}")
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    empty = pd.DataFrame(columns=["month", "value", "n_runs"])
    if column not in acts.columns:
        return empty
    easy = easy_runs(acts, cfg).dropna(subset=[column])
    if easy.empty:
        return empty
    easy = easy.assign(month=easy["date"].dt.to_period("M").dt.start_time)
    return easy.groupby("month", as_index=False).agg(value=(column, "median"),
                                                     n_runs=("activity_id", "count"))
