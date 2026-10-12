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
