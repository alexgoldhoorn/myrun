"""Link-outs to the tools this dashboard does not replace."""

from __future__ import annotations

import pandas as pd


def strava_url(activity_id: str) -> str:
    return f"https://www.strava.com/activities/{str(activity_id).removeprefix('activity-')}"


def sfs_url(base: str | None, activity_id: str) -> str | None:
    """Link to the activity in your statistics-for-strava site; None when `base` is unset."""
    return f"{base.rstrip('/')}/activities/{activity_id}" if base else None


def garmin_url(garmin_activity_id) -> str | None:
    if garmin_activity_id is None or pd.isna(garmin_activity_id):
        return None
    return f"https://connect.garmin.com/modern/activity/{int(garmin_activity_id)}"


def fill_race_garmin_urls(races: pd.DataFrame, activities: pd.DataFrame) -> pd.DataFrame:
    """Give a race without its own Garmin link the link of its matched activity."""
    if "garmin_activity_id" not in activities.columns or "race_name" not in activities.columns:
        return races
    matched = activities.dropna(subset=["race_name", "garmin_activity_id"])
    found = {(r.race_name, r.date): garmin_url(r.garmin_activity_id) for r in matched.itertuples()}
    out = races.copy()
    own = out["garmin_url"] if "garmin_url" in out else pd.Series(None, index=out.index,
                                                                   dtype="object")
    from_activity = [found.get((r.name, r.date)) for r in out[["name", "date"]].itertuples(index=False)]
    out["garmin_url"] = [o if isinstance(o, str) and o else f for o, f in zip(own, from_activity)]
    return out
