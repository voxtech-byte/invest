"""
Kinetic Ledger — Status Indicator Component

All style= attributes are single-line strings.

Usage:
    render_status_indicator("Alpha Engine", "Online", status="online")
    render_status_indicator("Fix Gateway", "Latency High", status="warning")
    render_status_indicator("Risk DB", "Syncing...", status="syncing", meta="45ms")
"""
import streamlit as st

_MONO = "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace"
_SANS = "Inter,sans-serif"

_DOT_STYLES = {
    "online":  "background:#88d982;box-shadow:0 0 6px rgba(136,217,130,0.4);",
    "warning": "background:#ffb3ac;box-shadow:0 0 6px rgba(255,179,172,0.4);",
    "offline": "background:#869391;",
    "syncing": "background:#66d9cc;",
}
_DESC_COLORS = {
    "online":  "#bcc9c6",
    "warning": "#ffb3ac",
    "offline": "#869391",
    "syncing": "#bcc9c6",
}


def render_status_indicator(
    label: str,
    description: str = "",
    status: str = "online",
    meta: str = "",
) -> None:
    """Renders a single status indicator row. All styles are single-line."""
    dot_style = _DOT_STYLES.get(status, _DOT_STYLES["online"])
    desc_color = _DESC_COLORS.get(status, "#bcc9c6")

    meta_html = ""
    if meta:
        meta_html = f'<span style="font-family:{_MONO};font-size:0.625rem;color:#bcc9c6;">{meta}</span>'

    html = (
        '<div style="display:flex;justify-content:space-between;align-items:center;padding:0.625rem 0.75rem;background:#2a2a2a;border-radius:4px;margin-bottom:3px;">'
        f'<div style="display:flex;align-items:center;gap:0.625rem;">'
        f'<div style="width:6px;height:6px;border-radius:50%;flex-shrink:0;{dot_style}"></div>'
        f'<span style="font-family:{_SANS};font-size:0.85rem;font-weight:500;color:#e5e2e1;">{label}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:0.625rem;">'
        f'<span style="font-family:{_MONO};font-size:0.6875rem;color:{desc_color};">{description}</span>'
        f'{meta_html}'
        f'</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def render_status_group(title: str, statuses: list[dict]) -> None:
    """Renders a group of status indicators inside a card."""
    st.markdown(
        f'<div style="background:#202020;border:1px solid rgba(61,73,71,0.2);border-radius:4px;overflow:hidden;margin-bottom:4px;">'
        f'<div style="padding:0.625rem 0.75rem;border-bottom:1px solid rgba(61,73,71,0.2);background:#2a2a2a;">'
        f'<span style="font-family:{_SANS};font-size:0.6875rem;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#e5e2e1;">{title}</span>'
        f'</div>'
        f'<div style="padding:0.5rem 0.5rem 0.25rem;">',
        unsafe_allow_html=True
    )
    for s in statuses:
        render_status_indicator(
            label=s.get("label", ""),
            description=s.get("description", ""),
            status=s.get("status", "online"),
            meta=s.get("meta", ""),
        )
    st.markdown("</div></div>", unsafe_allow_html=True)
