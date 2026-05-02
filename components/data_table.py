"""
Kinetic Ledger — Data Table Component (The Ledger)

All style= attributes are single-line strings — no multi-line style blocks.
This prevents Streamlit from rendering raw CSS as visible text.

Usage:
    render_kinetic_table(
        headers=["Symbol", "Side", "Qty", "Price", "Status"],
        rows=[
            {"cells": ["BBCA", "BUY", "150", "8,200", "Filled"],
             "colors": ["primary", "buy", "", "", "muted"]},
        ],
        align=["left", "left", "right", "right", "left"],
        title="Execution Log",
    )
"""
import streamlit as st
from typing import Optional

_MONO = "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace"
_SANS = "Inter,sans-serif"

_SURFACE_LOWEST = "#0e0e0e"
_SURFACE_LOW    = "#1b1b1c"
_SURFACE        = "#202020"
_SURFACE_HIGH   = "#2a2a2a"
_SURFACE_HIGHEST= "#353535"
_ON_SURFACE     = "#e5e2e1"
_ON_SURFACE_VAR = "#bcc9c6"
_PRIMARY        = "#66d9cc"
_SECONDARY      = "#88d982"
_TERTIARY       = "#ffb3ac"
_BORDER         = "rgba(61,73,71,0.2)"

_COLOR_MAP = {
    "primary": _PRIMARY,
    "buy":     _SECONDARY,
    "sell":    _TERTIARY,
    "profit":  _SECONDARY,
    "loss":    _TERTIARY,
    "muted":   _ON_SURFACE_VAR,
    "neutral": _ON_SURFACE,
    "":        _ON_SURFACE,
}


def render_kinetic_table(
    headers: list[str],
    rows: list[dict],
    align: Optional[list[str]] = None,
    title: str = "",
    subtitle: str = "",
    max_height: str = "400px",
    show_filter: bool = False,
) -> None:
    """
    Renders a Kinetic Ledger-style data table.
    All style attributes are single-line to prevent Streamlit rendering issues.
    """
    if align is None:
        align = ["left"] * len(headers)

    # ── Section header ────────────────────────────────────────────────
    header_html = ""
    if title:
        subtitle_span = ""
        if subtitle:
            subtitle_span = f'<span style="font-family:{_MONO};font-size:0.625rem;color:{_ON_SURFACE_VAR};background:{_SURFACE_HIGHEST};padding:2px 8px;border-radius:2px;">{subtitle}</span>'

        header_html = (
            f'<div style="background:{_SURFACE_HIGH};padding:0.625rem 1rem;border-bottom:1px solid {_BORDER};display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-family:{_SANS};font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:{_ON_SURFACE};">{title}</span>'
            f'<div style="display:flex;align-items:center;gap:10px;">{subtitle_span}</div>'
            f'</div>'
        )

    # ── Table headers ─────────────────────────────────────────────────
    th_cells = ""
    for i, h in enumerate(headers):
        text_align = align[i] if i < len(align) else "left"
        th_cells += f'<th style="padding:6px 12px;font-family:{_MONO};font-size:0.6rem;font-weight:400;text-transform:uppercase;letter-spacing:0.1em;color:{_ON_SURFACE_VAR};text-align:{text_align};white-space:nowrap;">{h}</th>'

    # ── Table rows ────────────────────────────────────────────────────
    if not rows:
        placeholder = "".join(
            f'<td style="padding:8px 12px;font-family:{_MONO};font-size:0.8rem;color:{_ON_SURFACE_VAR};text-align:left;">--</td>'
            for _ in headers
        )
        rows_html = f'<tr style="background:{_SURFACE_LOW};">{placeholder}</tr>'
    else:
        rows_html = ""
        for i, row in enumerate(rows):
            row_bg = _SURFACE_LOW if i % 2 == 0 else _SURFACE_HIGH
            cells = row.get("cells", [])
            colors = row.get("colors", [""] * len(cells))
            td_cells = ""
            for j, cell_val in enumerate(cells):
                text_align = align[j] if j < len(align) else "left"
                cell_color = _COLOR_MAP.get(colors[j] if j < len(colors) else "", _ON_SURFACE)
                font_weight = "700" if (colors[j] if j < len(colors) else "") == "primary" else "400"
                td_cells += f'<td style="padding:8px 12px;font-family:{_MONO};font-size:0.8rem;color:{cell_color};font-weight:{font_weight};text-align:{text_align};vertical-align:middle;white-space:nowrap;">{cell_val}</td>'
            rows_html += f'<tr style="background:{row_bg};">{td_cells}</tr>'

    # ── Full table ────────────────────────────────────────────────────
    html = (
        f'<div style="background:{_SURFACE_LOWEST};border:1px solid {_BORDER};border-radius:4px;overflow:hidden;margin-bottom:4px;">'
        f'{header_html}'
        f'<div style="max-height:{max_height};overflow-y:auto;">'
        f'<table style="width:100%;border-collapse:collapse;text-align:left;">'
        f'<thead><tr style="background:{_SURFACE};">{th_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)
