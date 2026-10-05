"""myrun: training data as DataFrames, on top of a statistics-for-strava database."""

from myrun.activities import activities, runs
from myrun.config import Config, load_config

__all__ = ["Config", "activities", "load_config", "runs"]
