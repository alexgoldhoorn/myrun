"""plan_vs_actual(): the planned session beside what was done, per day of one week."""

from __future__ import annotations

from datetime import date

import pandas as pd

from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.optional import none_if_missing, read_plan


def _describe(row) -> str:
    if row.distance_km and row.distance_km > 0:
        return f"{row.sport} {row.distance_km:.1f} km"
    return f"{row.sport} {row.duration_min:.0f} min"


def plan_vs_actual(week_start=None, *, activities: pd.DataFrame | None = None, today=None,
                   cfg: Config | None = None) -> pd.DataFrame:
    """Seven rows, Monday to Sunday. Planned columns are None without a plan input."""
    cfg = cfg or load_config()
    now = pd.Timestamp(today if today is not None else date.today()).normalize()
    start = (pd.Timestamp(week_start).normalize() if week_start is not None
             else now - pd.Timedelta(days=now.weekday()))
    acts = activities if activities is not None else _load(cfg=cfg)
    plan, _ = read_plan(cfg, today=now)

    rows = []
    for day in pd.date_range(start, periods=7):
        done = acts[acts["date"] == day]
        planned = plan[plan["date"] == day] if plan is not None else None
        has_plan = planned is not None and len(planned) > 0
        rows.append({
            "date": day,
            "planned": "; ".join(planned["session"]) if has_plan else None,
            "planned_type": "; ".join(planned["type"]) if has_plan else None,
            "planned_km": float(planned["distance_km"].sum(min_count=1)) if has_plan else None,
            "actual": "; ".join(_describe(r) for r in done.itertuples()) if len(done) else None,
            "actual_run_km": float(done.loc[done["sport"].isin(RUN_SPORTS), "distance_km"].sum()),
        })
    out = pd.DataFrame(rows)
    for column in ("planned", "planned_type", "actual"):
        out[column] = none_if_missing(out[column])
    return out
