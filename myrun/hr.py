"""Heart-rate zones and the easy-run band: set in the config, or calculated.

Order of precedence, for the zones and for the easy band independently:
1. the explicit values in the config (hr.zone_upper_bounds, hr.easy_band);
2. percentages of hr.max_hr from the config;
3. percentages of the maximum heart rate observed in recent runs.

The percentages are the common five-zone split of maximum heart rate (the default on
most watches). They are a starting point, not a lab test: set your own values in the
config when you know them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from myrun.config import RUN_SPORTS, Config

ZONE_FRACTIONS = (0.60, 0.70, 0.80, 0.90)   # upper edge of zones 1 to 4
EASY_FRACTIONS = (0.65, 0.80)
OBSERVED_DAYS = 365
OBSERVED_QUANTILE = 0.995                   # ignores the odd sensor spike
MIN_OBSERVED_RUNS = 5


@dataclass(frozen=True)
class HrSettings:
    max_hr: int | None
    zone_upper_bounds: tuple[int, ...] | None
    easy_band: tuple[int, int] | None
    source: str                              # one line, shown on the pages


def observed_max_hr(activities: pd.DataFrame, today=None) -> int | None:
    """Highest heart rate reached in runs of the last 12 months, spikes excluded."""
    if activities.empty:
        return None
    runs = activities[activities["sport"].isin(RUN_SPORTS)].dropna(subset=["max_hr"])
    now = pd.Timestamp(today if today is not None else date.today()).normalize()
    recent = runs[runs["date"] > now - pd.Timedelta(days=OBSERVED_DAYS)]
    pool = recent if len(recent) >= MIN_OBSERVED_RUNS else runs
    if pool.empty:
        return None
    return int(round(pool["max_hr"].quantile(OBSERVED_QUANTILE)))


def hr_settings(cfg: Config, activities: pd.DataFrame | None = None, today=None) -> HrSettings:
    """Resolve the zones and easy band in use, and say where they come from."""
    zones, easy = cfg.hr_zone_upper_bounds, cfg.easy_hr_band
    if zones is not None and easy is not None:
        return HrSettings(cfg.max_hr, tuple(zones), tuple(easy), "set in the config")

    max_hr, origin = cfg.max_hr, "set in the config"
    if max_hr is None:
        if activities is None:
            from myrun.activities import activities as load  # avoids an import cycle

            activities = load(cfg=cfg)
        max_hr, origin = observed_max_hr(activities, today), "observed in runs of the last 12 months"
    if max_hr is None:
        return HrSettings(None, tuple(zones) if zones else None, tuple(easy) if easy else None,
                          "unavailable: no heart-rate data and nothing set in the config")

    if zones is None:
        zones = tuple(int(round(max_hr * f)) for f in ZONE_FRACTIONS)
    if easy is None:
        easy = tuple(int(round(max_hr * f)) for f in EASY_FRACTIONS)
    return HrSettings(int(max_hr), tuple(zones), tuple(easy),
                      f"calculated from a maximum heart rate of {int(max_hr)}, {origin}")
