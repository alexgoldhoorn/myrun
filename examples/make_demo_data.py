"""Writes a small synthetic data set and a config for it, so the dashboard runs with no
Strava account. Nothing here is real data.

    uv run python examples/make_demo_data.py demo
    MYRUN_CONFIG=demo/config.yaml uv run streamlit run app/Dashboard.py

The data is the test fixture: about eight activities, 30 days of wellness, a short plan and
one race, dated relative to today. Enough to see every page work, not enough to look good.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import fixture  # noqa: E402


def main(target: str = "demo") -> None:
    out = Path(target).resolve()
    out.mkdir(parents=True, exist_ok=True)
    today = date.today()
    fixture.build_fixture(out / "strava.db", today)
    fixture.write_wellness(out / "wellness.parquet", today)
    fixture.write_plan(out / "plan.csv", today)
    fixture.write_races(out / "races.csv", today)
    (out / "config.yaml").write_text(f"""strava_db: {out}/strava.db
cache_dir: {out}/cache
inputs:
  wellness_parquet: {out}/wellness.parquet
  plan_csv: {out}/plan.csv
  race_log_csv: {out}/races.csv
race_log_columns:
  name: "name "
  date: date
  type: type
  distance_km: distance (km)
  official_time: official time
  rank_pct: Rank % (all)
  garmin_url: Garmin URL
race_log_date_format: "%d/%m/%Y"
hr:
  zone_upper_bounds: [125, 145, 160, 172]
""")
    print(f"wrote {out}/config.yaml\nMYRUN_CONFIG={out}/config.yaml uv run streamlit run app/Dashboard.py")


if __name__ == "__main__":
    main(*sys.argv[1:2])
