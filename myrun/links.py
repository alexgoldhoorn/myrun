"""Link-outs to the tools this dashboard does not replace."""

from __future__ import annotations

import pandas as pd


def strava_url(activity_id: str) -> str:
    return f"https://www.strava.com/activities/{str(activity_id).removeprefix('activity-')}"


def sfs_url(base: str | None, activity_id: str) -> str | None:
    return f"{base.rstrip('/')}/activities/{activity_id}" if base else None


def garmin_url(garmin_activity_id) -> str | None:
    if garmin_activity_id is None or pd.isna(garmin_activity_id):
        return None
    return f"https://connect.garmin.com/modern/activity/{int(garmin_activity_id)}"
