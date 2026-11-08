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

import pandas as pd

from myrun.config import RUN_SPORTS, Config
from myrun.dates import today_ts

# Used only when the config sets no `hr:` zones. All chosen (the common share-of-max-HR
# zone model), not fitted to the runner: set `hr:` in the config to overrule them.
ZONE_FRACTIONS = (0.60, 0.70, 0.80, 0.90)   # upper edge of zones 1 to 4, as a share of max HR
EASY_FRACTIONS = (0.65, 0.80)               # the easy band, as a share of max HR
OBSERVED_DAYS = 365                         # max HR is looked for in the runs of the last year
# A run's max HR counts as a sensor spike when it is more than this far above the 90th
# percentile of all run maxima. Chosen (by Claude, 2026-11): a real all-out effort stays within
# a few percent of the p90 of one's run maxima, an optical-sensor glitch (230 on a 185 runner)
# is 20 % or more above it. Unlike a high quantile, the rule does not depend on the number of
# runs, so one spike cannot lift the maximum (and with it every zone and the easy band) when
# there are only a few hundred runs. On clean data the result is simply the highest run max.
SPIKE_REFERENCE_QUANTILE = 0.90
SPIKE_MARGIN = 1.10
MIN_OBSERVED_RUNS = 5                       # fewer runs with heart rate give no max HR


@dataclass(frozen=True)
class HrSettings:
    max_hr: int | None
    zone_upper_bounds: tuple[int, ...] | None
    easy_band: tuple[int, int] | None
    source: str                              # one line, shown on the pages


def _observed(activities: pd.DataFrame, today=None) -> tuple[int | None, str]:
    """The observed maximum and the pool it came from ("runs of the last 12 months" or
    "all runs" when the last year holds fewer than MIN_OBSERVED_RUNS)."""
    if activities.empty:
        return None, ""
    runs = activities[activities["sport"].isin(RUN_SPORTS)].dropna(subset=["max_hr"])
    now = today_ts(today)
    recent = runs[runs["date"] > now - pd.Timedelta(days=OBSERVED_DAYS)]
    if len(recent) >= MIN_OBSERVED_RUNS:
        pool, label = recent, "runs of the last 12 months"
    else:
        pool, label = runs, "all runs"
    if pool.empty:
        return None, ""
    values = pool["max_hr"].astype(float)
    ceiling = values.quantile(SPIKE_REFERENCE_QUANTILE) * SPIKE_MARGIN
    return int(round(values[values <= ceiling].max())), label


def observed_max_hr(activities: pd.DataFrame, today=None) -> int | None:
    """Highest heart rate reached in runs of the last 12 months (all runs when too few),
    sensor spikes excluded."""
    return _observed(activities, today)[0]


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
        max_hr, pool = _observed(activities, today)
        origin = f"observed in {pool}"
    if max_hr is None:
        return HrSettings(None, tuple(zones) if zones else None, tuple(easy) if easy else None,
                          "unavailable: no heart-rate data and nothing set in the config")

    if zones is None:
        zones = tuple(int(round(max_hr * f)) for f in ZONE_FRACTIONS)
    if easy is None:
        easy = tuple(int(round(max_hr * f)) for f in EASY_FRACTIONS)
    return HrSettings(int(max_hr), tuple(zones), tuple(easy),
                      f"calculated from a maximum heart rate of {int(max_hr)}, {origin}")
