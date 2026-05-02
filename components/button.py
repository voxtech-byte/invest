"""
Kinetic Ledger — Button Component

Renders consistent institutional-grade buttons.
- Primary: solid primary-container background
- Secondary: border only, surface-container-high
- Danger: border tertiary, text tertiary
- All: 32px min height, 4px radius, no scale on hover

Usage:
    render_button("Run Scan", style="primary", icon="sync")
    render_button("Export", style="secondary", icon="download")
    render_button("Emergency Sell", style="danger")
"""
import streamlit as st


def render_button(
    label: str,
    style: str = "secondary",
    icon: str = "",
    full_width: bool = False,
) -> None:
    """
    Renders a styled button as HTML.

    Note: This renders visual-only HTML. For interactive buttons,
    use Streamlit's native st.button() — the design_system.css
    already overrides Streamlit button styles.

    Args:
        label: Button text.
        style: "primary", "secondary", or "danger".
        icon: Material Symbols icon name.
        full_width: Whether button takes 100% width.
    """
    style_map = {
        "primary": {
            "bg": "#26a69a",
            "color": "#003430",
            "border": "none",
            "hover_bg": "#84f5e8",
        },
        "secondary": {
            "bg": "#2a2a2a",
            "color": "#e5e2e1",
            "border": "1px solid rgba(61,73,71,0.2)",
            "hover_bg": "#393939",
        },
        "danger": {
            "bg": "transparent",
            "color": "#ffb3ac",
            "border": "1px solid rgba(255,179,172,0.3)",
            "hover_bg": "rgba(255,179,172,0.1)",
        },
    }

    s = style_map.get(style, style_map["secondary"])
    width = "width:100%;" if full_width else ""

    icon_html = ""
    if icon:
        icon_html = f'<span class="material-symbols-outlined" style="font-size:16px;">{icon}</span>'

    st.markdown(f"""
    <div style="
        background:{s['bg']};
        color:{s['color']};
        border:{s['border']};
        border-radius:4px;
        min-height:32px;
        padding:6px 16px;
        display:inline-flex;
        align-items:center;
        justify-content:center;
        gap:8px;
        font-family:'Inter',sans-serif;
        font-size:0.8rem;
        font-weight:500;
        cursor:pointer;
        transition:background-color 0.2s ease;
        {width}
    ">
        {icon_html} {label}
    </div>
    """, unsafe_allow_html=True)
