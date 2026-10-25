"""Plain-text reports of the library's numbers, for a chat assistant rather than a page.

`python -m myrun.report fitness|race|dashboard|status` prints one report; `fitness --by-band`
prints the like-for-like comparison (heart rate by surface and pace band, per year). Each is built
from the same library calls as the dashboard, so the two never disagree. A missing input
gives a line that says so, never a zero.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from myrun import bands
from myrun.activities import activities as _load
from myrun.config import RUN_SPORTS, Config, load_config
from myrun.hr import hr_settings
from myrun.load import load_status
from myrun.metric import Metric, clean
from myrun.metrics import (headline, intensity_weekly, race_readiness, vo2max_trend,
                           weekly_runs)
from myrun.optional import input_states, read_plan, read_wellness
from myrun.planmatch import plan_vs_actual
from myrun.trends import aerobic_efficiency, best_efforts

DEFAULT_MONTHS = 12            # chosen: a year shows a trend through a full season
DEFAULT_WEEKS = 12             # chosen: same as the dashboard's weekly charts
UPCOMING_RACES = 5             # chosen: races ahead listed in the race report
RECENT_BEST_MONTHS = 12        # chosen: "recent" best effort, against the all-time one


def _num(value, digits: int = 1, unit: str = "") -> str:
    number = clean(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}{unit}"


def _pace(minutes) -> str:
    number = clean(minutes)
    if number is None:
        return "n/a"
    whole = int(number)
    seconds = round((number - whole) * 60)
    if seconds == 60:
        whole, seconds = whole + 1, 0
    return f"{whole}:{seconds:02d}/km"


def _day(value) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{pd.Timestamp(value):%Y-%m-%d}"


def _since(frame: pd.DataFrame, column: str, first: pd.Timestamp) -> pd.DataFrame:
    return frame[frame[column] >= first] if len(frame) else frame


def _value(metric: Metric, value) -> str:
    if metric.unit == "pace":
        return _pace(value)
    if metric.unit == "share":
        return _num(value, 1, " %")
    unit = f" {metric.unit}" if metric.unit and metric.unit != "count" else ""
    return _num(value) + (unit if clean(value) is not None else "")


def _metric_line(metric: Metric) -> str:
    text = f"- {metric.label}: {_value(metric, metric.value)}"
    if metric.previous is not None:
        text += f" (was {_value(metric, metric.previous)}"
        text += f", {metric.note})" if metric.note else ")"
    elif metric.note:
        text += f" ({metric.note})"
    if metric.detail:
        text += f" [{metric.detail}]"
    if metric.tone != "neutral":
        text += f" <{metric.tone}>"
    return text


def fitness(months: int = DEFAULT_MONTHS, *, cfg: Config | None = None,
            activities: pd.DataFrame | None = None, today=None) -> str:
    """VO2max, aerobic efficiency (pace against heart rate) and resting HR / HRV by month."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    now = pd.Timestamp(today if today is not None else date.today()).normalize()
    first = (now - pd.DateOffset(months=months - 1)).to_period("M").start_time
    out = [f"FITNESS TREND, monthly, {first:%Y-%m} to {now:%Y-%m}"]

    out.append("\nVO2max (Garmin's estimate on runs, monthly median):")
    vo2 = _since(vo2max_trend(acts), "month", first)
    if vo2.empty:
        out.append("- no VO2max values in this period (needs the Garmin activity feed)")
    for row in vo2.itertuples():
        out.append(f"- {row.month:%Y-%m}: {_num(row.value, 0)} ({row.n_runs} runs)")
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    if "vo2max" in runs.columns and runs["vo2max"].notna().any():
        last = runs.dropna(subset=["vo2max"]).sort_values("date").iloc[-1]
        out.append(f"- latest: {_num(last['vo2max'], 0)} on {_day(last['date'])}")

    band = hr_settings(cfg, acts)
    out.append("\nAerobic efficiency, easy flat road runs (speed per heartbeat; higher = "
               "faster at the same heart rate):")
    if band.easy_band is None:
        out.append("- no easy heart-rate band could be set, so no comparable runs")
    else:
        low, high = band.easy_band
        out.append(f"- easy band {low}-{high} bpm ({band.source})")
        eff = _since(aerobic_efficiency(activities=acts, cfg=cfg), "month", first)
        if eff.empty:
            out.append("- no comparable easy runs in this period")
        for row in eff.itertuples():
            out.append(f"- {row.month:%Y-%m}: {_num(row.efficiency, 2)} m/beat, "
                       f"median pace {_pace(row.median_pace_min_km)} ({row.n_runs} runs)")

    out.append("\nResting HR and HRV (Garmin, monthly mean):")
    wellness, state = read_wellness(cfg)
    if wellness is None or wellness.empty:
        out.append(f"- unavailable: {state.message or state.status}")
    else:
        recent = wellness[wellness["date"] >= first].copy()
        recent["month"] = recent["date"].dt.to_period("M").dt.start_time
        monthly = recent.groupby("month").agg(resting_hr=("resting_hr", "mean"),
                                              hrv_ms=("hrv_ms", "mean"))
        for month, row in monthly.iterrows():
            out.append(f"- {month:%Y-%m}: resting HR {_num(row.resting_hr, 0, ' bpm')}, "
                       f"HRV {_num(row.hrv_ms, 0, ' ms')}")
    return "\n".join(out)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _cell(row) -> str:
    return (f"{_plural(row.n_runs, 'run')}, {_num(row.km, 0)} km, "
            f"HR {_num(row.mean_hr, 0)} ({_num(row.hr_pct_max, 0)} % max), "
            f"{_num(row.speed_per_beat, 2)} m/beat, {_num(row.temp_c, 0, ' °C')}"
            + (" [noisy]" if row.noisy else ""))


def _season_label(season: tuple[int, ...] | None) -> str:
    return "all months" if not season else "months " + ",".join(str(m) for m in season)


def fitness_by_band(months: int = DEFAULT_MONTHS, *, first_year: int | None = None,
                    season: tuple[int, ...] | None = None, cfg: Config | None = None,
                    activities: pd.DataFrame | None = None, today=None) -> str:
    """Heart rate by surface and pace band per year (and per month for the last `months`),
    aerobic efficiency per year, and the easy/steady/hard mix per year."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    now = pd.Timestamp(today if today is not None else date.today()).normalize()
    first_year = first_year if first_year is not None else bands.default_first_year(now)
    runs = bands.band_runs(activities=acts, cfg=cfg, today=now)
    heart = hr_settings(cfg, acts, now)
    threshold, threshold_source = bands.trail_threshold(acts[acts["sport"].isin(RUN_SPORTS)])
    out = [f"FITNESS BY PACE BAND, {first_year} to {now.year}, {_season_label(season)}",
           "Each run's core (first and last km and lap dropped), grade-adjusted pace; "
           "races, intervals and unsteady runs left out. Compare a band with itself across "
           "years: a lower HR in the same band and surface is fitness, not an easier mix.",
           f"- max HR {heart.max_hr or 'n/a'} ({heart.source}); untagged runs count as trail "
           f"from {threshold:g} m climb/km ({threshold_source}), only in years without "
           f"TrailRun; cells under {bands.NOISY_RUNS} runs are [noisy]"]

    shown = runs[runs["year"] >= first_year]
    if season:
        shown = shown[shown["date"].dt.month.isin(season)]
    counts = shown["excluded"].fillna("kept").value_counts()
    out.append("- runs: " + ", ".join(f"{name} {n}" for name, n in counts.items()))

    gear = bands.gear_yearly(runs[runs["year"] >= first_year], season)
    out.append("\nWatch and HR sensor per year (share of the runs kept; a step in HR that lines "
               "up with a change of watch or strap can be the sensor, not fitness):")
    if gear.empty:
        out.append("- no qualifying runs")
    for row in gear.itertuples():
        watches = ", ".join(f"{name} {_num(pct, 0)} %" for name, pct in row.watches.items())
        line = f"- {row.year}: {watches}"
        if cfg.hr_sensors:
            line += "; HR " + ", ".join(f"{name} {_num(pct, 0)} %"
                                        for name, pct in row.sensors.items())
        out.append(line)
    if cfg.hr_sensors and cfg.hr_sensors_worn == "hard":
        out.append("- the strap is worn on hard runs only, so most runs here are wrist HR from "
                   "the watch: a change of watch is a change of HR sensor")
    offsets = bands.watch_offsets(runs)
    for row in offsets.itertuples():
        chained = ("" if row.applied_bpm == row.offset_bpm
                   else f", {row.offset_bpm:+.1f} against the {row.reference} plus the chain")
        out.append(f"- HR corrected: {row.device} {row.applied_bpm:+.1f} bpm onto the "
                   f"{offsets.iloc[0].reference} scale{chained} (fitted from {row.n_reference} "
                   f"{row.reference} and {row.n_runs} {row.device} runs in the same quarter, "
                   f"surface and pace band, {_plural(row.n_cells, 'cell')}); every HR and "
                   "efficiency figure below includes it")
    if offsets.empty:
        out.append(f"- no watch HR correction: no watch switch has {bands.MIN_PAIRED_RUNS} "
                   "runs on both watches in shared cells")
    for device, owned_from in cfg.device_owned_from.items():
        out.append(f"- left out everywhere: activities on the {device} before {owned_from} "
                   "(the previous owner's)")

    yearly = bands.since_year(bands.band_table(runs, "year", season), first_year)
    for surface in bands.SURFACES:
        cells = yearly[yearly["surface"] == surface]
        out.append(f"\n{surface.title()}, per year (band: runs, km, HR, % of max, speed per beat, "
                   "start temperature):")
        if cells.empty:
            out.append("- no qualifying runs")
        for band in bands.PACE_BANDS:
            rows = cells[cells["band"] == band]
            if rows.empty:
                continue
            out.append(f"- {band}/km:")
            out.extend(f"  - {int(row.period)}: {_cell(row)}" for row in rows.itertuples())

    first_month = (now - pd.DateOffset(months=months - 1)).to_period("M").start_time
    monthly = bands.band_table(runs, "month", season)
    monthly = monthly[monthly["period"] >= first_month]
    out.append(f"\nPer month, {first_month:%Y-%m} to {now:%Y-%m}:")
    if monthly.empty:
        out.append("- no qualifying runs")
    for row in monthly.itertuples():
        out.append(f"- {row.period:%Y-%m} {row.surface} {row.band}: {_cell(row)}")

    out.append("\nAerobic efficiency per year, easy flat road runs (monthly medians weighted "
               "by run count; higher = faster at the same heart rate):")
    efficiency = bands.yearly_efficiency(activities=acts, cfg=cfg, season=season,
                                         offsets=offsets)
    efficiency = efficiency[efficiency["year"] >= first_year]
    if efficiency.empty:
        out.append("- no comparable easy runs")
    for row in efficiency.itertuples():
        noisy = " [noisy]" if row.n_runs < bands.NOISY_RUNS else ""
        out.append(f"- {row.year}: {_num(row.efficiency, 3)} m/beat ({_plural(row.n_runs, 'run')} "
                   f"in {_plural(row.n_months, 'month')}){noisy}")

    out.append("\nIntensity mix per year (share of running minutes, Garmin training effect):")
    mix = bands.intensity_yearly(activities=acts, cfg=cfg, season=season)
    mix = mix[mix["year"] >= first_year]
    if mix.empty:
        out.append("- no training effect values (needs the Garmin activity feed)")
    for row in mix.itertuples():
        out.append(f"- {row.year}: easy {_num(row.easy_pct, 0)} %, steady "
                   f"{_num(row.steady_pct, 0)} %, hard {_num(row.hard_pct, 0)} % "
                   f"({_num(row.rated_pct, 0)} % of minutes rated)")
    return "\n".join(out)


def race(weeks: int = DEFAULT_WEEKS, *, cfg: Config | None = None,
         activities: pd.DataFrame | None = None, today=None) -> str:
    """The build-up to the next race against the last similar one, plus the weeks behind it."""
    cfg = cfg or load_config()
    acts = activities if activities is not None else _load(cfg=cfg)
    now = pd.Timestamp(today if today is not None else date.today()).normalize()
    runs = acts[acts["sport"].isin(RUN_SPORTS)]
    plan, plan_state = read_plan(cfg, today=now)
    out = ["RACE PROGRESS"]

    if plan is None:
        out.append(f"- no training plan: {plan_state.message or plan_state.status}")
    else:
        ahead = plan[(plan["type"] == "race") & (plan["date"] >= now)].sort_values("date")
        out.append("\nRaces ahead in the plan:")
        if ahead.empty:
            out.append("- none")
        for row in ahead.head(UPCOMING_RACES).itertuples():
            extra = [f"{_num(row.distance_km)} km"] if clean(row.distance_km) else []
            if isinstance(getattr(row, "surface", None), str) and row.surface:
                extra.append(row.surface)
            if clean(getattr(row, "elevation_m", None)):
                extra.append(f"{_num(row.elevation_m, 0)} m climb")
            out.append(f"- {_day(row.date)} ({(row.date - now).days} days): {row.session}"
                       + (f", {', '.join(extra)}" if extra else ""))

    ready = race_readiness(runs, plan, now)
    if ready is not None:
        out.append(f"\nBuild-up for {ready['race']}, last {ready['weeks']} weeks:")
        out.append(f"- now: {_num(ready['km'])} km, longest run {_num(ready['longest_km'])} km")
        prev = ready["previous"]
        if prev is None:
            out.append("- no earlier similar race to compare with")
        else:
            out.append(f"- same point before {prev['name']} ({_day(prev['date'])}): "
                       f"{_num(prev['km'])} km, longest run {_num(prev['longest_km'])} km")

    weekly = weekly_runs(weeks, activities=acts, today=now, cfg=cfg)
    intensity = intensity_weekly(weeks, activities=acts, today=now, cfg=cfg)
    out.append(f"\nLast {weeks} weeks (Monday start; the current week is partial):")
    for row in weekly.itertuples():
        planned = f", planned {_num(row.planned_km)} km" if clean(row.planned_km) is not None else ""
        line = (f"- {row.week_start:%Y-%m-%d}: {_num(row.run_km)} km in {row.n_runs} runs, "
                f"longest {_num(row.longest_km)} km, easy pace {_pace(row.easy_pace_min_km)}"
                f"{planned}")
        match = intensity[intensity["week_start"] == row.week_start]
        if len(match):
            mins = match.iloc[0]
            line += (f", easy/steady/hard {_num(mins.easy_min, 0)}/{_num(mins.steady_min, 0)}/"
                     f"{_num(mins.hard_min, 0)} min")
        out.append(line)

    out.append("\nLoad, last 7 days against the 28-day weekly average:")
    for label, column in (("Strava relative effort", "relative_effort"),
                          ("Garmin load", "garmin_load")):
        if column not in acts.columns:
            continue
        status = load_status(activities=acts, today=now, cfg=cfg, column=column)
        out.append(f"- {label}: {_num(status['last7'], 0)} vs {_num(status['avg_week_28'], 0)} "
                   f"(ratio {_num(status['ratio'], 2)}, {status['label']})")

    out.append("\nThis week, plan against done:")
    for row in plan_vs_actual(activities=acts, today=now, cfg=cfg).itertuples():
        planned = row.planned if isinstance(row.planned, str) and row.planned else "-"
        actual = row.actual if isinstance(row.actual, str) and row.actual else "-"
        out.append(f"- {row.date:%a %d}: planned {planned}; done {actual}")

    bests = best_efforts(cfg=cfg)
    if len(bests):
        recent_from = now - pd.DateOffset(months=RECENT_BEST_MONTHS)
        out.append(f"\nBest efforts (fastest ever, and fastest in the last {RECENT_BEST_MONTHS} months):")
        for distance, group in bests.groupby("distance_m"):
            best = group.loc[group["time_s"].idxmin()]
            recent = group[group["date"] >= recent_from]
            line = f"- {distance / 1000:g} km: {_effort(best)}"
            if len(recent):
                line += f"; recent {_effort(recent.loc[recent['time_s'].idxmin()])}"
            out.append(line)
    return "\n".join(out)


def _effort(row) -> str:
    minutes, seconds = divmod(int(row["time_s"]), 60)
    hours, minutes = divmod(minutes, 60)
    clock = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
    return f"{clock} ({_pace(row['pace_min_km'])}) on {_day(row['date'])}"


def dashboard(*, cfg: Config | None = None, activities: pd.DataFrame | None = None,
              today=None) -> str:
    """Every dashboard card as a line, grouped by row."""
    cards = headline(activities=activities, today=today, cfg=cfg)
    out = ["DASHBOARD (each value against its comparison period)"]
    for group, metrics in cards.items():
        out.append(f"\n{group.title()}:")
        out.extend(_metric_line(metric) for metric in metrics)
    return "\n".join(out)


def status(*, cfg: Config | None = None) -> str:
    """Age and state of every input, so an answer can say when data is stale."""
    states = input_states(cfg or load_config())
    out = ["INPUTS"]
    for state in states.values():
        age = f", {state.age_hours:.0f} h old" if state.age_hours is not None else ""
        note = f": {state.message}" if state.message else ""
        out.append(f"- {state.name}: {state.status}{age}{note}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m myrun.report", description=__doc__)
    parser.add_argument("report", choices=("fitness", "race", "dashboard", "status"))
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS)
    parser.add_argument("--weeks", type=int, default=DEFAULT_WEEKS)
    parser.add_argument("--by-band", action="store_true",
                        help="fitness: heart rate by surface and pace band, per year and month")
    parser.add_argument("--from-year", type=int, default=None,
                        help="fitness --by-band: first year shown (default: five years back)")
    parser.add_argument("--season", default="",
                        help="fitness --by-band: only these months, e.g. 9-10 or 9,10 or 11-2")
    args = parser.parse_args(argv)
    if not 1 <= args.months <= 120 or not 1 <= args.weeks <= 104:
        parser.error("--months must be 1-120 and --weeks 1-104")
    if args.from_year is not None and not 2000 <= args.from_year <= 2100:
        parser.error("--from-year must be a year like 2021")
    try:
        season = bands.parse_season(args.season)
    except ValueError as exc:
        parser.error(str(exc))
    if args.report == "fitness" and args.by_band:
        text = fitness_by_band(args.months, first_year=args.from_year, season=season)
    elif args.report == "fitness":
        text = fitness(args.months)
    elif args.report == "race":
        text = race(args.weeks)
    elif args.report == "dashboard":
        text = dashboard()
    else:
        text = status()
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
