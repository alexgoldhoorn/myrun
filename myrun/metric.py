"""Metric: one headline number with its comparison, as cards and notebooks use it."""

from __future__ import annotations

import math
from dataclasses import dataclass

TONES = ("neutral", "good", "warn", "bad")


@dataclass(frozen=True)
class Metric:
    """One headline number: its value, the value to compare it with, and how to show it.

    `unit` is a short code that `fmt.metric_value` knows (km, m, pace, hours, bpm, score, ...).
    `tone` is neutral, good, warn or bad: whether the change is good news, which depends on
    the metric (a lower resting heart rate is good, lower HRV is not). `series` is a short
    history for the sparkline."""
    key: str
    label: str
    value: float | None
    previous: float | None
    unit: str
    series: tuple[float, ...] = ()
    tone: str = "neutral"
    note: str | None = None        # what `previous` is, or why there is no value
    detail: str | None = None      # short text beside the value, e.g. the load label

    @property
    def delta(self) -> float | None:
        """value minus previous; None when either is missing."""
        if self.value is None or self.previous is None:
            return None
        return self.value - self.previous


def clean(value) -> float | None:
    """A finite float, or None for anything missing."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
