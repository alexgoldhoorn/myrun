"""Display formats: pace as minutes:seconds, durations, and matching axis ticks.

Pace is stored as decimal minutes per km (6.38), which nobody reads. These helpers
turn it into 6:23 for text, and give chart axes round tick positions with the same
labels, so the numbers stay numeric (and sortable) while the labels are readable.
"""

from __future__ import annotations

import math

import pandas as pd

PACE_COLUMNS = ("pace_min_km", "gap_min_km", "median_pace_min_km")
MAX_TICKS = 6
_PACE_STEPS = (0.25, 0.5, 1.0, 2.0, 5.0)                 # minutes per km
_DURATION_STEPS = (60, 120, 300, 600, 900, 1800, 3600)    # seconds


def _number(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def pace(min_per_km) -> str:
    """6.38 -> '6:23'. 'n/a' for a missing, zero or infinite pace."""
    value = _number(min_per_km)
    if not value or value <= 0:
        return "n/a"
    seconds = int(round(value * 60))
    return f"{seconds // 60}:{seconds % 60:02d}"


def duration(seconds) -> str:
    """2682 -> '44:42', 5025 -> '1:23:45'."""
    value = _number(seconds)
    if value is None or value < 0:
        return "n/a"
    total = int(round(value))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _ticks(values, steps) -> list[float]:
    numbers = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    numbers = numbers[(numbers > 0) & (numbers != float("inf"))]
    if numbers.empty:
        return []
    low, high = float(numbers.min()), float(numbers.max())
    for step in steps:
        first = math.ceil(low / step - 1e-9) * step
        count = int(math.floor((high - first) / step + 1e-9)) + 1 if high >= first else 0
        if 0 < count <= MAX_TICKS:
            return [round(first + i * step, 6) for i in range(count)]
    if high - low < steps[0]:        # a flat series: one label at the nearest round value
        return [round(round(low / steps[0]) * steps[0], 6)]
    step = steps[-1]
    first = math.ceil(low / step) * step
    return [first + i * step for i in range(MAX_TICKS)]


def pace_ticks(values) -> tuple[list[float], list[str]]:
    """Round tick positions for a pace axis, and their m:ss labels."""
    ticks = _ticks(values, _PACE_STEPS)
    return ticks, [pace(t) for t in ticks]


def duration_ticks(values) -> tuple[list[float], list[str]]:
    """Round tick positions for a duration axis in seconds, and their labels."""
    ticks = _ticks(values, _DURATION_STEPS)
    return ticks, [duration(t) for t in ticks]


_VALUE_FORMATS = {
    "km": "{:.1f} km", "m": "{:,.0f} m", "metres": "{:.2f} m", "ratio": "{:.2f}",
    "count": "{:.1f}", "score": "{:.0f}", "ms": "{:.0f} ms", "bpm": "{:.0f} bpm",
    "hours": "{:.1f} h", "cm": "{:.1f} cm", "pct": "{:.1f} %", "w": "{:.0f} W", "te": "{:.1f}",
    "share": "{:.0f} %", "weeks": "{:.0f} wk",
}
_DELTA_FORMATS = {
    "km": "{:+.1f} km", "m": "{:+,.0f} m", "metres": "{:+.2f} m", "ratio": "{:+.2f}",
    "count": "{:+.1f}", "score": "{:+.0f}", "ms": "{:+.0f} ms", "bpm": "{:+.0f} bpm",
    "hours": "{:+.1f} h", "cm": "{:+.1f} cm", "pct": "{:+.1f} %", "w": "{:+.0f} W",
    "te": "{:+.1f}", "share": "{:+.0f} pts", "weeks": "{:+.0f} wk",
}


def metric_value(value, unit: str) -> str:
    """A headline value with its unit; 'n/a' when missing."""
    number = _number(value)
    if number is None:
        return "n/a"
    if unit == "pace":
        text = pace(number)
        return text if text == "n/a" else f"{text} /km"
    return _VALUE_FORMATS[unit].format(number)


def metric_delta(delta, unit: str) -> str:
    """A signed change in the unit of the value; '' when there is none."""
    number = _number(delta)
    if number is None:
        return ""
    if unit == "pace":
        return f"{number * 60:+.0f} s /km"
    return _DELTA_FORMATS[unit].format(number)
