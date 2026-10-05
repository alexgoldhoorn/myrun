# myrun

A personal training dashboard that sits on top of a
[statistics-for-strava](https://github.com/robiningelbrecht/statistics-for-strava)
database. It answers four questions, and links out to Strava, Garmin Connect and
statistics-for-strava for everything else.

- **Now**: load in the last 7 days against your 4-week average, this week against
  the plan, recovery, the next race.
- **Trends**: aerobic efficiency, volume, best efforts, races.
- **Activity**: heart rate, pace, elevation and cadence over one run, time in zones,
  heart-rate drift, laps, and an overlay with another run.
- **Explore**: any metric against any other, per run or per kilometre, grouped by
  hour of day, temperature, surface, climb or descent, and more.

Every number comes from a function in the `myrun` Python package, so the same data
is one import away in a notebook.

## What it needs

Only the statistics-for-strava SQLite file (`storage/database/strava.db`), which it
opens read-only. It never contacts Strava or Garmin.

Four more inputs are optional. Leave one out and its panels disappear.

| Input | Format | Columns |
|---|---|---|
| Wellness | Parquet, one row per day | `date`, and any of `readiness`, `sleep_hours`, `hrv_ms`, `resting_hr` |
| Plan | CSV | `date` (ISO), `session`, `type` (for example `easy`, `tempo`, `intervals`, `long`, `race`, `rest`), `distance_km` |
| Race log | CSV with your own headers, mapped in the config | at least a name and a date; optionally type, distance, official time, rank percentile, links |
| Garmin activities | Parquet, one row per activity | `start` (local time), and any of `garmin_activity_id`, `session_name`, `session_type`, `vertical_oscillation_cm`, `ground_contact_ms`, `stride_length_m` |

Garmin activities are matched to Strava activities by start time, because the two
share no identifier.

## Run it

```bash
uv sync
cp config.example.yaml ~/my-myrun-config.yaml      # then edit strava_db and your HR zones
MYRUN_CONFIG=~/my-myrun-config.yaml uv run streamlit run app/Now.py
```

There is no login. Bind it to localhost or put it behind a reverse proxy that
authenticates.

## Use it in a notebook

```python
import myrun
runs = myrun.runs()          # one row per run
splits = myrun.splits()      # one row per kilometre
```

See `examples/notebook_example.py`.

## Notes

- Per-km heart rate is computed from streams and cached in `cache_dir`. The first
  visit to the per-km view takes a while; delete the cache to rebuild it.
- Load is Strava's relative effort. Activities without it are not counted, and the
  page says how many.
- Surface is `trail` for trail runs, `mixed` for runs above a configurable climb per
  km, otherwise `road`. A race log entry overrides it.

## Development

```bash
uv run pytest -q
sh scripts/git-hooks/install.sh
```
