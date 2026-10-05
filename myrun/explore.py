"""Grouping and column helpers for the Explore page (and for notebooks)."""

from __future__ import annotations

import pandas as pd

from myrun import derive

# display name -> (source column, name of the block-width argument or None for a plain category)
GROUPS: dict[str, tuple[str | None, str | None]] = {
    "(none)": (None, None),
    "Hour of day": ("hour", "hour_block"),
    "Temperature": ("temp_c", "temp_block"),
    "Distance": ("distance_km", "distance_band"),
    "Hilliness": ("hilliness_m_km", "hilliness_band"),
    "Surface": ("surface", None),
    "Climb or descent": ("grade_class", None),
    "Session type": ("session_type", None),
    "Sport": ("sport", None),
    "Year": ("year", None),
}
DEFAULT_BLOCKS = {"hour_block": 3, "temp_block": 5, "distance_band": 5, "hilliness_band": 10}
_NOT_METRICS = ("has_streams", "split", "garmin_activity_id")


def available_groups(df: pd.DataFrame) -> list[str]:
    """Groupings whose source column exists and holds at least one value."""
    out = []
    for name, (column, _) in GROUPS.items():
        if column is None or (column in df.columns and df[column].notna().any()):
            out.append(name)
    return out


def group_series(df: pd.DataFrame, group: str, **blocks) -> pd.Series | None:
    """The label of each row for the chosen grouping, or None for no grouping."""
    column, block = GROUPS[group]
    if column is None or column not in df.columns:
        return None
    if block is not None:
        width = blocks.get(block, DEFAULT_BLOCKS[block])
        return derive.bin_label(df[column], width)
    values = df[column]
    return pd.Series([None if pd.isna(v) else str(v) for v in values], index=df.index,
                     dtype="object")


def numeric_columns(df: pd.DataFrame) -> list[str]:
    """Columns usable as a chart axis: numeric, not a flag, with at least one value."""
    out = []
    for column in df.columns:
        if column in _NOT_METRICS or pd.api.types.is_bool_dtype(df[column]):
            continue
        if pd.api.types.is_numeric_dtype(df[column]) and df[column].notna().any():
            out.append(column)
    return out


def ordered(labels) -> list[str]:
    """Sort labels so that block labels ('5–10', '10–15') come in numeric order."""
    def key(label: str):
        try:
            head = label.split("–")[0] if not label.startswith("-") else "-" + label[1:].split("–")[0]
            return (0, float(head), label)
        except ValueError:
            return (1, 0.0, label)

    return sorted({str(v) for v in labels if v is not None and not pd.isna(v)}, key=key)
