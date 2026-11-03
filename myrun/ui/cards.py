"""Metric cards as HTML. Everything that comes from data is escaped."""

from __future__ import annotations

from html import escape

import streamlit as st

from myrun import fmt
from myrun.metric import Metric
from myrun.ui import theme

_W, _H, _PAD = 100.0, 28.0, 2.0


def sparkline_svg(series) -> str:
    """An inline trend line; '' for fewer than two points."""
    values = [float(v) for v in series]
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = (_W - 2 * _PAD) / (len(values) - 1)
    points = " ".join(
        f"{_PAD + i * step:.1f},{_H - _PAD - (v - low) / span * (_H - 2 * _PAD):.1f}"
        for i, v in enumerate(values))
    return (f'<svg class="mr-spark" viewBox="0 0 {_W:.0f} {_H:.0f}" preserveAspectRatio="none" '
            f'aria-hidden="true"><polyline points="{points}"/></svg>')


def card_html(metric: Metric) -> str:
    tone = theme.TONE_CLASS.get(metric.tone, theme.TONE_CLASS["neutral"])
    value = escape(fmt.metric_value(metric.value, metric.unit))
    detail = (f'<span class="mr-detail {tone}">{escape(metric.detail)}</span>'
              if metric.detail else "")
    change = fmt.metric_delta(metric.delta, metric.unit) if metric.value is not None else ""
    change_html = f'<div class="mr-change {tone}">{escape(change)}</div>' if change else ""
    note = f'<div class="mr-note">{escape(metric.note)}</div>' if metric.note else ""
    spark = sparkline_svg(metric.series) if metric.value is not None else ""
    return (f'<div class="mr-card"><div class="mr-label">{escape(metric.label)}</div>'
            f'<div class="mr-value">{value}{detail}</div>{change_html}{note}{spark}</div>')


def row_html(metrics: list[Metric]) -> str:
    return '<div class="mr-row">' + "".join(card_html(m) for m in metrics) + "</div>"


def card_row(metrics: list[Metric]) -> None:
    if metrics:
        st.markdown(row_html(metrics), unsafe_allow_html=True)


def strip_html(items: list[tuple[str, str]]) -> str:
    """A one-line header strip of 'label: value' pairs."""
    parts = "".join(f'<span><span class="mr-label">{escape(label)}</span> '
                    f'<strong>{escape(value)}</strong></span>' for label, value in items)
    return f'<div class="mr-strip">{parts}</div>'


def summary_html(items: list[tuple[str, str]]) -> str:
    """A row of small cards holding a label and a ready-made value, nothing else.

    The row wraps instead of cutting text off, so a value is always shown in full."""
    parts = "".join(f'<div class="mr-card mr-compact"><div class="mr-label">{escape(label)}</div>'
                    f'<div class="mr-value">{escape(value)}</div></div>' for label, value in items)
    return f'<div class="mr-row mr-row-compact">{parts}</div>' if parts else ""


def links_html(items: list[tuple[str, str | None]]) -> str:
    """Outgoing links as one row of evenly spaced buttons; entries without a URL are left out."""
    parts = "".join(f'<a class="mr-link" href="{escape(url)}" target="_blank" rel="noopener">'
                    f'{escape(label)}</a>' for label, url in items if url)
    return f'<div class="mr-links">{parts}</div>' if parts else ""


_MARKDOWN = str.maketrans({c: f"&#{ord(c)};" for c in "*_`[]~$"})


def note_html(text: str) -> str:
    """A small grey line of plain text: neither markup nor Markdown in it is interpreted."""
    return f'<div class="mr-note">{escape(text).translate(_MARKDOWN)}</div>'


_DAY_LEVELS = (30, 60)       # minutes: under 30 is light, under 60 medium, the rest full


def _month_labels(days) -> list[str]:
    """One entry per week column: the month's short name for the first column and for each
    week holding the first day of a month, else ''."""
    labels, previous = [], None
    dates = list(days["date"])
    for start in range(0, len(dates), 7):
        week = dates[start:start + 7]
        first_of_month = next((d for d in week if d.day == 1), None)
        if first_of_month is not None:
            labels.append(f"{first_of_month:%b}")
        elif previous is None:
            labels.append(f"{week[0]:%b}")
        else:
            labels.append("")
        previous = labels[-1]
    return labels


def calendar_html(days) -> str:
    """Training days as a grid, one column per week (Monday on top), under a row of month
    names; '' without days.

    `days` has `date` and `minutes`; NaN minutes mark days that have not happened yet.
    The last day that is not NaN is today and is outlined."""
    if len(days) == 0:
        return ""
    played = days["minutes"].notna()
    today = days["date"][played].max() if played.any() else None
    squares = []
    for row in days.itertuples(index=False):
        if row.minutes != row.minutes:                       # NaN: a future day
            squares.append('<span class="mr-day mr-day-future"></span>')
            continue
        marker = " mr-day-today" if row.date == today else ""
        unknown = row.minutes <= 0 and getattr(row, "activities", 0) > 0
        level = 1 if unknown else 0 if row.minutes <= 0 else 1 + sum(
            row.minutes >= edge for edge in _DAY_LEVELS)
        text = ("activity, length unknown" if unknown else "rest" if level == 0
                else f"{row.minutes:.0f} min")
        squares.append(f'<span class="mr-day mr-day-{level}{marker}" '
                       f'title="{escape(f"{row.date:%a %d %b}: {text}")}"></span>')
    names = _month_labels(days)
    labels = "".join(f"<span>{escape(name)}</span>" for name in names)
    return (f'<div class="mr-cal-wrap">'
            f'<div class="mr-cal-labels" style="grid-template-columns: repeat({len(names)}, 14px)">'
            f'{labels}</div><div class="mr-cal">{"".join(squares)}</div></div>')


def readiness_html(ready: dict | None) -> str:
    """The race build-up strip; '' when there is no race ahead."""
    if not ready:
        return ""
    weeks, when = ready["weeks"], ready["days_to_go"]
    to_go = "today" if when == 0 else f"in {when} day" + ("" if when == 1 else "s")
    items = [("Race build-up", f"{ready['race']}, {to_go}"),
             (f"Last {weeks} weeks", f"{ready['km']:.0f} km, longest {ready['longest_km']:.0f} km")]
    previous = ready.get("previous")
    if previous:
        items.append((f"Same point before {previous['name']} ({previous['date']:%b %Y})",
                      f"{previous['km']:.0f} km, longest {previous['longest_km']:.0f} km"))
    return strip_html(items)
