"""
Kinetic Ledger — Theme Injector

Loads the Kinetic Ledger design system CSS into Streamlit.
Replaces the old Bloomberg-style terminal theme with the
professional institutional "Kinetic Ledger" design system.

This module:
1. Reads assets/design_system.css
2. Injects it via st.markdown with unsafe_allow_html
3. Provides icon helper using Material Symbols (replaces old SVG icons)

Usage:
    from ui.terminal_style import inject_terminal_theme, get_icon
    inject_terminal_theme()
"""
import streamlit as st
import os


def inject_terminal_theme() -> None:
    """
    Injects the Kinetic Ledger design system CSS into the Streamlit app.
    Call this once at the top of your app.py, after st.set_page_config().
    """
    css_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'design_system.css')

    css_content = ""
    try:
        with open(css_path, 'r') as f:
            css_content = f.read()
    except FileNotFoundError:
        # Fallback: inline the essential tokens if CSS file is missing
        css_content = _get_fallback_css()

    st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)


def get_icon(name: str, size: str = "18px") -> str:
    """
    Returns a Material Symbols Outlined icon HTML string.

    Replaces the old SVG-based icon system with Google Material Symbols.
    See: https://fonts.google.com/icons

    Args:
        name: Material Symbols icon name (e.g., "dashboard", "analytics").
        size: CSS font size for the icon.

    Returns:
        HTML string for the icon span.

    Example:
        get_icon("trending_up")       -> trending up arrow
        get_icon("security", "24px")  -> shield icon at 24px
    """
    return f'<span class="material-symbols-outlined" style="font-size:{size}; vertical-align:middle;">{name}</span>'


# ── Legacy compatibility aliases ──
# These map old icon names to Material Symbols equivalents
ICON_MAP = {
    "activity":     "monitoring",
    "shield":       "security",
    "zap":          "bolt",
    "trending-up":  "trending_up",
    "layers":       "layers",
    "alert":        "warning",
    "check":        "check_circle",
    "x":            "cancel",
    "clock":        "schedule",
    "download":     "download",
    "filter":       "filter_list",
    "search":       "search",
    "settings":     "settings",
    "refresh":      "refresh",
    "chart":        "analytics",
    "wallet":       "account_balance_wallet",
    "user":         "person",
    "bell":         "notifications",
    "terminal":     "terminal",
    "help":         "help_outline",
    "book":         "menu_book",
    "stats":        "query_stats",
    "gauge":        "speed",
    "portfolio":    "analytics",
}


def get_legacy_icon(name: str) -> str:
    """
    Maps old icon names to Material Symbols equivalents.
    Use get_icon() directly for new code.
    """
    mapped = ICON_MAP.get(name, name)
    return get_icon(mapped)


def _get_fallback_css() -> str:
    """Minimal inline CSS if design_system.css is not found."""
    return """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap');

    [data-testid="stAppViewContainer"] {
        background-color: #131313 !important;
        color: #e5e2e1 !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stSidebar"] {
        background-color: #0e0e0e !important;
        border-right: 1px solid rgba(61,73,71,0.2) !important;
    }
    [data-testid="stSidebar"] > div { background-color: #0e0e0e !important; }
    h1,h2,h3,h4,h5,h6 { font-family: 'Inter', sans-serif !important; color: #e5e2e1 !important; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #131313; }
    ::-webkit-scrollbar-thumb { background: #3d4947; border-radius: 4px; }
    """
