"""
Kinetic Ledger — Metric Card Component

Renders a professional metric display card with fully inlined styles.
All style attributes are single-line — no multi-line style strings.

Usage:
    render_metric_card("Portfolio Balance", "Rp 50,000,000", icon="account_balance_wallet")
    render_metric_card("Daily P&L", "+Rp 1,250,000", color="profit", icon="trending_up")
    render_metric_card("Max Drawdown", "-4.2%", color="loss")
"""
import streamlit as st

_COLOR_MAP = {
    "neutral": "#e5e2e1",
    "profit":  "#88d982",
    "loss":    "#ffb3ac",
    "primary": "#66d9cc",
}

_MONO = "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace"
_SANS = "Inter,sans-serif"


def render_metric_card(
    label: str,
    value: str,
    color: str = "neutral",
    icon: str = "",
    subtitle: str = "",
) -> None:
    """
    Renders a single metric card. All style= attributes are single-line.

    Args:
        label: Upper label text.
        value: Main display value.
        color: "neutral", "profit", "loss", or "primary".
        icon: Material Symbols icon name (background watermark).
        subtitle: Small text below value.
    """
    value_color = _COLOR_MAP.get(color, "#e5e2e1")

    icon_html = ""
    if icon:
        icon_html = f'<div style="position:absolute;right:0;bottom:0;padding:0.75rem;opacity:0.12;pointer-events:none;"><span class="material-symbols-outlined" style="font-size:3rem;color:#bcc9c6;line-height:1;">{icon}</span></div>'

    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<div style="font-family:{_MONO};font-size:0.7rem;color:#bcc9c6;margin-top:0.25rem;">{subtitle}</div>'

    html = (
        '<div style="background:#202020;border:1px solid rgba(61,73,71,0.2);border-radius:4px;padding:1.25rem;'
        'display:flex;flex-direction:column;justify-content:space-between;min-height:7rem;position:relative;overflow:hidden;">'
        f'<div style="font-family:{_SANS};font-size:0.6875rem;font-weight:500;text-transform:uppercase;letter-spacing:0.1em;color:#bcc9c6;">{label}</div>'
        f'<div style="font-family:{_MONO};font-size:1.5rem;font-weight:700;color:{value_color};margin-top:0.5rem;line-height:1.1;">{value}</div>'
        f'{subtitle_html}'
        f'{icon_html}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_metric_row(metrics: list[dict]) -> None:
    """
    Renders multiple metric cards in a horizontal row.

    Args:
        metrics: List of dicts with keys: label, value, color, icon, subtitle.
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            render_metric_card(
                label=m.get("label", ""),
                value=m.get("value", ""),
                color=m.get("color", "neutral"),
                icon=m.get("icon", ""),
                subtitle=m.get("subtitle", ""),
            )
