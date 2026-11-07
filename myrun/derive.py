"""Pure derivation rules. No I/O. Thresholds are passed in."""

from __future__ import annotations

import numpy as np
import pandas as pd


def hilliness(elevation_m: pd.Series, distance_km: pd.Series) -> pd.Series:
    """Metres climbed per km. NaN when there is no distance."""
    return (elevation_m / distance_km).where(distance_km > 0)


def surface(sport: pd.Series, hilliness_m_km: pd.Series,
            mixed_threshold: float | None) -> pd.Series:
    """road / trail from the sport type, None for non-running sports.

    With a threshold, a Run that climbs at least that many metres per km is "mixed".
    """
    out = pd.Series([None] * len(sport), index=sport.index, dtype="object")
    run = sport == "Run"
    out[run] = "road"
    if mixed_threshold is not None:
        out[run & (hilliness_m_km >= mixed_threshold)] = "mixed"
    out[sport == "TrailRun"] = "trail"
    return out


def grade_class(elev_diff_m: pd.Series, distance_m: pd.Series, threshold: float) -> pd.Series:
    """climb / flat / descent from the elevation change normalised to one km."""
    per_km = (elev_diff_m / distance_m * 1000).where(distance_m > 0)
    out = pd.Series(["flat"] * len(per_km), index=per_km.index, dtype="object")
    out[per_km > threshold] = "climb"
    out[per_km < -threshold] = "descent"
    out[per_km.isna()] = None
    return out


def bin_label(values: pd.Series, width: float) -> pd.Series:
    """Label each value with its block, e.g. 12 with width 5 gives '10–15'."""
    lower = np.floor(values.astype(float) / width) * width
    labels = [None if pd.isna(v) else f"{v:g}–{v + width:g}" for v in lower]
    return pd.Series(labels, index=values.index, dtype="object")


def load_label(ratio: float | None, bands: tuple[float, float, float]) -> str:
    """Name a load ratio (last 7 days over the weekly average of the last 28).

    `bands` is (low, high, very_high), the config's `thresholds.load_bands`: below `low` is
    "low", up to `high` "steady", up to `very_high` "high", above that "very high"."""
    if ratio is None:
        return "no data"
    low, high, very_high = bands
    if ratio < low:
        return "low"
    if ratio <= high:
        return "steady"
    if ratio <= very_high:
        return "high"
    return "very high"
