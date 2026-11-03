"""Display formats: pace as minutes:seconds, durations, and matching axis ticks.

Pace is stored as decimal minutes per km (6.38), which nobody reads. These helpers
turn it into 6:23 for text, and give chart axes round tick positions with the same
labels, so the numbers stay numeric (and sortable) while the labels are readable.
"""

from __future__ import annotations

import math
import re

import pandas as pd

PACE_COLUMNS = ("pace_min_km", "gap_min_km", "median_pace_min_km")
MAX_TICKS = 6
_PACE_STEPS = (0.25, 0.5, 1.0, 2.0, 5.0)                 # minutes per km
_DURATION_STEPS = (60, 120, 300, 600, 900, 1800, 3600)    # seconds


LABELS = {
    "temp_c": "Temperature (°C)", "pace_min_km": "Pace (min/km)", "distance_km": "Distance (km)",
    "duration_h": "Duration (h)", "duration_min": "Duration (min)", "elevation_m": "Climb (m)",
    "cumulative_km": "Cumulative km", "day_of_year": "Day of year", "period": "Period",
    "avg_hr": "Avg HR (bpm)", "max_hr": "Max HR (bpm)", "elev_diff_m": "Climb (m)",
    "name": "Name", "date": "Date", "place": "Place", "type": "Type", "sport": "Sport",
    "year": "Year", "kind": "Kind", "lap": "Lap", "time": "Time", "pace": "Pace",
    "efficiency": "Efficiency (m/min/beat)", "month": "Month", "relative_effort": "Relative effort",
    "strava_db": "Strava DB", "wellness": "wellness", "plan": "plan", "race_log": "race log",
    "garmin_activities": "Garmin activities",
    # Explore axes and dynamics columns
    "speed_kmh": "Speed (km/h)", "gap_min_km": "Grade-adjusted pace (min/km)",
    "median_pace_min_km": "Median pace (min/km)", "cadence_spm": "Cadence (spm)",
    "garmin_cadence_spm": "Garmin cadence (spm)", "avg_cadence_spm": "Cadence (spm)",
    "feels_like_c": "Feels like (°C)", "humidity_pct": "Humidity (%)",
    "dew_point_c": "Dew point (°C)", "hour": "Hour of day (h)",
    "hilliness_m_km": "Hilliness (m/km)", "ground_contact_ms": "Ground contact (ms)",
    "vertical_oscillation_cm": "Vertical oscillation (cm)", "vertical_ratio_pct": "Vertical ratio (%)",
    "stride_length_m": "Stride length (m)", "power_w": "Power (W)",
    "aerobic_te": "Aerobic training effect", "anaerobic_te": "Anaerobic training effect",
    "garmin_load": "Garmin load", "vo2max": "VO2max", "rank_pct": "Rank percentile (%)",
    "official_time_s": "Official time (s)", "duration_s": "Duration (s)", "split": "Split (km)",
    "altitude_m": "Elevation (m)", "hr": "Heart rate (bpm)", "session_type": "Session type",
    "garmin_url": "Garmin", "strava_url": "Strava", "diploma_url": "Diploma",
    "easy_pace": "Easy pace (min/km)", "minutes": "Minutes", "run_km": "Running km",
    "run_minutes": "Running minutes", "m_per_beat": "m per heartbeat",
    "mean_hr": "Mean HR (bpm)", "share_minutes": "% of running minutes", "time_min": "Time (min)",
    "surface": "Surface", "grade_class": "Climb or descent",
}


def label(key: str) -> str:
    """A human label for a column or input name; unknown keys lose their underscores."""
    return LABELS.get(key, key.replace("_", " "))


SPORT_GROUPS = ("Run", "Trail run", "Walk", "Ride", "Other")
_SPORT_GROUP_OF = {"Run": "Run", "TrailRun": "Trail run", "Walk": "Walk", "Hike": "Walk",
                   "Ride": "Ride", "VirtualRide": "Ride", "EBikeRide": "Ride",
                   "GravelRide": "Ride", "MountainBikeRide": "Ride"}


def sport_group(sport) -> str:
    """The coarse group a Strava sport belongs to in the volume chart (one of SPORT_GROUPS)."""
    return _SPORT_GROUP_OF.get(sport, "Other")


def shoe_name(name: str) -> str:
    """Drop the short alias Strava gear names repeat at the end: 'X Wave Rider 28 Wave Rider 28'."""
    if not isinstance(name, str):
        return name
    tag = ""
    match = re.search(r"\s*(\[[^\]]*\])\s*$", name)
    if match:
        tag, name = " " + match.group(1), name[:match.start()]
    tokens = name.split()
    for k in range(len(tokens) // 2, 1, -1):
        tail, head = tokens[-k:], tokens[:-k]
        if tail == head[-k:] or _in_order(tail, head):
            return " ".join(head) + tag
    return name + tag


def _in_order(tail: list[str], head: list[str]) -> bool:
    """Each tail token equals, or is the '-' suffix of, a head token, in order."""
    position = 0
    for token in tail:
        for i in range(position, len(head)):
            if head[i] == token or head[i].endswith("-" + token):
                position = i + 1
                break
        else:
            return False
    return True


def day_summary(sports, distances_km) -> str:
    """Several activities in one cell: '3 walks · 4.9 km', '1 run, 2 walks · 13.6 km'."""
    counts: dict[str, int] = {}
    for sport in sports:
        word = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(sport)).lower()
        counts[word] = counts.get(word, 0) + 1
    parts = ", ".join(f"{n} {word}{'' if n == 1 else 's'}" for word, n in counts.items())
    total = sum(float(d) for d in distances_km if _number(d) is not None)
    return f"{parts} · {total:,.1f} km"


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
    "km": "{:,.1f} km", "m": "{:,.0f} m", "metres": "{:.2f} m", "ratio": "{:.2f}",
    "count": "{:.1f}", "score": "{:.0f}", "ms": "{:.0f} ms", "bpm": "{:.0f} bpm",
    "hours": "{:.1f} h", "cm": "{:.1f} cm", "pct": "{:.1f} %", "w": "{:.0f} W", "te": "{:.1f}",
    "share": "{:.0f} %", "weeks": "{:.0f} wk",
}
_DELTA_FORMATS = {
    "km": "{:+,.1f} km", "m": "{:+,.0f} m", "metres": "{:+.2f} m", "ratio": "{:+.2f}",
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
