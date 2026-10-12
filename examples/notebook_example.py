"""The same numbers the dashboard shows, in a notebook.

Paste the cells into Jupyter, or run this file. It reads the config named by
MYRUN_CONFIG (default ~/dockers/myrun/config.yaml).
"""

import myrun

# One row per run, with weather, surface and session type.
runs = myrun.runs()
print(runs[["date", "distance_km", "pace_min_km", "avg_hr", "temp_c", "surface"]].tail())

# Pace against temperature on road runs.
road = runs[runs["surface"] == "road"]
print(road[["temp_c", "pace_min_km"]].corr())

# One row per kilometre: heart rate on climbs, flats and descents.
splits = myrun.splits()
print(splits.groupby("grade_class")[["avg_hr", "pace_min_km"]].median())

# Second-by-second data for the latest run that has streams.
latest = runs[runs["has_streams"]].iloc[-1]["activity_id"]
print(myrun.activity_streams(latest).describe())

# What the Dashboard page shows.
print(myrun.load_status())
print(myrun.input_status())
