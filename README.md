# myrun

A self-hosted training dashboard for runners who already keep their data in
[statistics-for-strava](https://github.com/robiningelbrecht/statistics-for-strava). It reads
that tool's SQLite database (read-only), adds optional wellness, plan, race and Garmin files,
and answers four questions in a [Streamlit](https://streamlit.io) app. It never contacts
Strava or Garmin, so it needs no API keys and runs entirely on your own machine.

![Dashboard page on the synthetic demo data](docs/screenshot-dashboard.png)

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

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

**Try it with synthetic data** (no Strava account needed):

```bash
git clone <this repo> && cd myrun
uv sync
uv run python examples/make_demo_data.py demo
MYRUN_CONFIG=demo/config.yaml uv run streamlit run app/Dashboard.py
```

**Against your own statistics-for-strava database:**

```bash
uv sync
mkdir -p ~/.config/myrun && cp config.example.yaml ~/.config/myrun/config.yaml
# edit it: set strava_db to .../statistics-for-strava/storage/database/strava.db
uv run streamlit run app/Dashboard.py
```

The database is opened read-only, so you can point at the live file (a WAL database reads
fine). Set the optional `inputs:` in the config as you get the files.

## Configuration

All settings live in one YAML file, documented line by line in `config.example.yaml`. Unknown
keys are an error. Only `strava_db` is required. These environment variables apply:

| Variable | Default | Purpose |
|---|---|---|
| `MYRUN_CONFIG` | `~/.config/myrun/config.yaml` | Path of the config file (the app, the notebook API and `python -m myrun.report` all read it) |
| `MYRUN_CACHE_LOG` | unset | Set to `1` to log every result-cache miss and which thread paid for it |
| `MYRUN_DENY_PATTERNS` | `~/.config/myrun/deny-patterns.txt` | Contributors only: the pre-commit guard's list of personal strings (see Development) |

## Docker

```bash
docker build -t myrun .
docker run -p 8501:8501 \
  -v /path/to/statistics-for-strava/storage/database:/data:ro \
  -v /path/to/your/inputs:/inputs:ro \
  -v /path/to/config.yaml:/config/config.yaml:ro \
  -v myrun-cache:/cache \
  myrun
```

Use container paths in that config file: `strava_db: /data/strava.db`, `/inputs/...` for the
optional inputs, `cache_dir: /cache`. The image runs as UID 1000, so the mounted files must be
readable by it and the cache volume writable (the container's `HOME` is `/tmp`).

Text reports for scripts or chat tools: `uv run python -m myrun.report fitness|race|dashboard|status`.

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

The tests build a synthetic database (`tests/fixture.py`); no real data is needed or present.
The hook blocks data files (`.db`, `.csv`, `.parquet`, `.fit`, `config.yaml`, ...) and runs the
tests. If you keep a list of personal strings (hostnames, your name, a home path), one regex
per line in `~/.config/myrun/deny-patterns.txt`, it also rejects staged files that match; without
that file the check is skipped with a warning.

## License

MIT, see `LICENSE`. The bundled Inter font is under the SIL Open Font License 1.1
(`app/static/FONT-LICENSE.md`). Dependencies (numpy, pandas, pyarrow, PyYAML, zstandard,
Streamlit, Plotly) are BSD, MIT or Apache-2.0 licensed. This project is not affiliated with
Strava, Garmin or statistics-for-strava.
