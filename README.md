# myrun

A personal training dashboard that sits on top of a
[statistics-for-strava](https://github.com/robiningelbrecht/statistics-for-strava)
database. It answers four questions, and links out to Strava, Garmin Connect and
statistics-for-strava for everything else.

- **Dashboard**: cards for volume (with the share of the plan done), load and fitness
  (with VO2max and the easy share of running time, from the Garmin input), and recovery,
  each against the period before; a consistency row with the run streak and a 12-week
  calendar of training days; the build-up to the next race against the same point
  before the last similar one; weekly load and weekly kilometres against the plan; this week's
  sessions; recent runs.
- **Trends**: aerobic efficiency, volume, best efforts, shoe mileage, races, and running dynamics
  over time when the Garmin input is set.
- **Activity**: heart rate, pace, elevation and cadence over one run, time in zones,
  heart-rate drift, laps, an overlay with another run, and the run's running dynamics
  against your recent runs on the same surface.
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
| Wellness | Parquet, one row per day | `date`, and any of `readiness`, `sleep_hours`, `hrv_ms`, `resting_hr`, `body_battery`, `stress`, and as card detail `sleep_score`, `deep_sleep_seconds`, `rem_sleep_seconds`, `hrv_status`; other names can be mapped in the config |
| Plan | CSV | `date` (ISO), `session`, `type` (for example `easy`, `tempo`, `intervals`, `long`, `race`, `rest`), `distance_km` |
| Race log | CSV with your own headers, mapped in the config | at least a name and a date; optionally type, distance, official time, rank percentile, links |
| Garmin activities | CSV or Parquet, one row per activity | `start` (local time), and any of `garmin_activity_id`, `session_name`, `session_type`, `ground_contact_ms`, `vertical_oscillation_cm`, `vertical_ratio_pct`, `stride_length_m`, `garmin_cadence_spm`, `power_w`, `aerobic_te`, `anaerobic_te`, `garmin_load`, `vo2max` |

Garmin activities are matched to Strava activities by start time, because the two
share no identifier.

## Run it

```bash
uv sync
cp config.example.yaml ~/my-myrun-config.yaml      # then edit strava_db and your HR zones
MYRUN_CONFIG=~/my-myrun-config.yaml uv run streamlit run app/Dashboard.py
```

To have the numbers ready before the first visit, start it through the launcher instead:
`uv run python -m myrun.ui.warm run app/Dashboard.py`. It takes the same arguments as
`streamlit` and keeps the result cache warm from a background thread.

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
- Surface follows the Strava sport type: `road` for Run, `trail` for Trail Run. A race
  log entry can override it, and you can opt in to a `mixed` label for hilly road runs.
- Heart-rate zones are 60/70/80/90 % of your maximum heart rate, taken from your runs
  of the last 12 months unless you set a maximum or your own zones in the config.
  Each page says which is in use.

## Development

```bash
uv run pytest -q
sh scripts/git-hooks/install.sh
```
