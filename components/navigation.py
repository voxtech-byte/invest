"""
Kinetic Ledger — Navigation Component

Primary navigation is via the sidebar (render_sidebar_nav).
The topnav is visual-only due to Streamlit's HTML limitation —
it cannot have click handlers. Sidebar buttons drive all routing.

Usage:
    render_topnav(active_view=st.session_state.kl_active_view)
    render_page_header("Trading Command Center")

    with st.sidebar:
        render_sidebar_nav(active_view=st.session_state.kl_active_view)
"""
import streamlit as st
from datetime import datetime
import pytz


# ── View definitions with sections ────────────────────────────────────
# Each view has: key, label, icon (Material Symbols), section
VIEWS = [
    # Trading section
    {"key": "command",   "label": "Command Center",  "icon": "dashboard",    "section": "TRADING"},
    {"key": "signals",   "label": "Signals",         "icon": "query_stats",  "section": "TRADING"},
    {"key": "risk",      "label": "Risk Management", "icon": "security",     "section": "TRADING"},
    # Analytics section
    {"key": "portfolio", "label": "Portfolio",       "icon": "analytics",    "section": "ANALYTICS"},
    {"key": "journal",   "label": "Trade Journal",   "icon": "menu_book",    "section": "ANALYTICS"},
    # Admin section
    {"key": "settings",  "label": "Settings",        "icon": "settings",     "section": "ADMIN"},
]

# CSS injected once into sidebar for nav item styling
_SIDEBAR_CSS = """
<style>
/* Override Streamlit sidebar button defaults for nav items */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    border-radius: 4px !important;
    color: #737373 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    text-align: left !important;
    padding: 0.5rem 0.75rem !important;
    min-height: 40px !important;
    width: 100% !important;
    justify-content: flex-start !important;
    transition: background-color 0.15s ease, color 0.15s ease !important;
    border-left: 3px solid transparent !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #171717 !important;
    color: #e5e2e1 !important;
}
/* Active nav item — primary button type */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #1e2e2c !important;
    color: #66d9cc !important;
    border-left: 3px solid #66d9cc !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: #243533 !important;
}
</style>
"""


def render_topnav(active_view: str = "command") -> str:
    """
    Renders the Kinetic Ledger top bar (brand + active view indicator).

    NOTE: Nav links are visual-only HTML — NOT clickable. This is a
    Streamlit limitation. All navigation is handled by render_sidebar_nav().
    The topnav shows the brand name and current active view label only.

    Args:
        active_view: Currently active view key.

    Returns:
        The current active view key from session state (unchanged).
    """
    active_label = next((v["label"] for v in VIEWS if v["key"] == active_view), "Command Center")

    topnav_html = f"""
<div style="
    background:#171717;
    border-bottom:1px solid rgba(61,73,71,0.2);
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:0 1.5rem;
    height:3.5rem;
    flex-shrink:0;
    margin-bottom:0.5rem;
">
    <div style="display:flex; align-items:center; gap:1.5rem;">
        <span style="
            font-family:'Inter',sans-serif;
            font-size:1.1rem;
            font-weight:900;
            letter-spacing:-0.05em;
            color:#66d9cc;
        ">KINETIC LEDGER</span>
        <span style="
            font-family:ui-monospace,SFMono-Regular,monospace;
            font-size:0.65rem;
            text-transform:uppercase;
            letter-spacing:0.1em;
            color:#3d4947;
        ">/</span>
        <span style="
            font-family:ui-monospace,SFMono-Regular,monospace;
            font-size:0.7rem;
            text-transform:uppercase;
            letter-spacing:0.05em;
            color:#bcc9c6;
        ">{active_label}</span>
    </div>
    <div style="display:flex; align-items:center; gap:0.75rem;">
        <div style="
            width:6px; height:6px; border-radius:50%;
            background:#88d982;
            box-shadow:0 0 6px rgba(136,217,130,0.5);
        "></div>
        <span style="
            font-family:ui-monospace,monospace;
            font-size:0.65rem;
            color:#bcc9c6;
            text-transform:uppercase;
            letter-spacing:0.08em;
        ">V15 PRO</span>
    </div>
</div>
"""
    st.markdown(topnav_html, unsafe_allow_html=True)
    return st.session_state.get('kl_active_view', 'command')


def render_page_header(
    title: str,
    subtitle: str = "",
    show_time: bool = True,
    actions: list[dict] = None,
) -> None:
    """
    Renders a page-level header with title, subtitle, and optional action buttons.

    Args:
        title: Page title text.
        subtitle: Descriptive text below title.
        show_time: Whether to show system time in WIB.
        actions: List of action button dicts with keys: label, icon, style.
    """
    if show_time and not subtitle:
        try:
            tz = pytz.timezone('Asia/Jakarta')
            now = datetime.now(tz)
            subtitle = f"SYS_TIME: {now.strftime('%H:%M:%S')} WIB  |  IDX"
        except Exception:
            subtitle = ""

    subtitle_html = ""
    if subtitle:
        subtitle_html = f'<p class="kl-page-subtitle">{subtitle}</p>'

    actions_html = ""
    if actions:
        btns = ""
        for a in actions:
            icon = a.get("icon", "")
            icon_html = (
                f'<span class="material-symbols-outlined" style="font-size:15px;">{icon}</span>'
                if icon else ""
            )
            style = a.get("style", "secondary")
            if style == "primary":
                btn_style = "background:#26a69a; color:#003430; border:none;"
            else:
                btn_style = "background:#2a2a2a; color:#e5e2e1; border:1px solid rgba(61,73,71,0.2);"

            btns += f"""<div style="
                {btn_style}
                border-radius:4px;
                min-height:32px;
                padding:5px 14px;
                display:inline-flex;
                align-items:center;
                gap:6px;
                font-family:'Inter',sans-serif;
                font-size:0.8rem;
                font-weight:500;
                cursor:pointer;
            ">{icon_html}{a.get('label', '')}</div>"""

        actions_html = f'<div style="display:flex; gap:8px;">{btns}</div>'

    st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:1.5rem;">
    <div>
        <h1 style="
            font-family:'Inter',sans-serif;
            font-size:2rem;
            font-weight:700;
            letter-spacing:-0.02em;
            color:#e5e2e1;
            line-height:1;
            margin:0;
        ">{title}</h1>
        {subtitle_html}
    </div>
    {actions_html}
</div>
""", unsafe_allow_html=True)


def render_sidebar_nav(active_view: str = "command") -> str:
    """
    Renders the primary navigation sidebar with sections, icons, and active states.

    This is the ONLY interactive navigation in the app. Each nav item is a
    native Streamlit button styled via CSS injection. Clicking updates
    st.session_state.kl_active_view and triggers st.rerun().

    Sections:
        TRADING  — Command Center, Signals, Risk Management
        ANALYTICS — Portfolio, Trade Journal
        ADMIN    — Settings

    Args:
        active_view: Currently active view key.

    Returns:
        Selected view key string.
    """
    # Inject sidebar CSS once
    st.sidebar.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)

    # ── Brand header ──────────────────────────────────────────────────
    st.sidebar.markdown("""
<div style="
    display:flex;
    align-items:center;
    gap:10px;
    padding:1rem 0.75rem 1.25rem;
    border-bottom:1px solid rgba(61,73,71,0.2);
    margin-bottom:0.5rem;
">
    <div style="
        width:34px; height:34px;
        border-radius:4px;
        background:#1e2e2c;
        display:flex; align-items:center; justify-content:center;
        border:1px solid rgba(102,217,204,0.2);
        flex-shrink:0;
    ">
        <span class="material-symbols-outlined" style="color:#66d9cc; font-size:1.1rem;">account_balance</span>
    </div>
    <div>
        <div style="
            color:#66d9cc;
            font-family:'Inter',sans-serif;
            font-weight:700;
            font-size:0.8rem;
            letter-spacing:0.05em;
            text-transform:uppercase;
            line-height:1.2;
        ">Kinetic Ledger</div>
        <div style="
            color:#3d4947;
            font-family:ui-monospace,monospace;
            font-size:0.6rem;
            text-transform:uppercase;
            letter-spacing:0.12em;
            margin-top:2px;
        ">Sovereign V15 Pro</div>
    </div>
</div>
""", unsafe_allow_html=True)

    selected = active_view

    # ── Render sections ───────────────────────────────────────────────
    current_section = None
    for v in VIEWS:
        # Section divider
        if v["section"] != current_section:
            current_section = v["section"]
            st.sidebar.markdown(f"""
<div style="
    padding:0.75rem 0.75rem 0.25rem;
    font-family:ui-monospace,SFMono-Regular,monospace;
    font-size:0.6rem;
    font-weight:500;
    text-transform:uppercase;
    letter-spacing:0.12em;
    color:#3d4947;
">
    {current_section}
</div>
""", unsafe_allow_html=True)

        is_active = v["key"] == active_view
        btn_type = "primary" if is_active else "secondary"

        # Icon + label as button text
        icon_span = f'<span class="material-symbols-outlined" style="font-size:1.1rem; vertical-align:middle; margin-right:8px;">{v["icon"]}</span>'
        btn_label = f"{v['label']}"

        # Render the nav button
        # We use a container to inject the icon via HTML alongside the button
        col_icon, col_btn = st.sidebar.columns([1, 5])

        with col_icon:
            st.markdown(
                f"""<div style="
                    display:flex; align-items:center; justify-content:center;
                    height:40px; padding-top:4px;
                ">
                    <span class="material-symbols-outlined" style="
                        font-size:1.1rem;
                        color:{'#66d9cc' if is_active else '#737373'};
                    ">{v['icon']}</span>
                </div>""",
                unsafe_allow_html=True,
            )

        with col_btn:
            if st.button(
                btn_label,
                key=f"nav_{v['key']}",
                use_container_width=True,
                type=btn_type,
            ):
                st.session_state.kl_active_view = v["key"]
                selected = v["key"]
                st.rerun()

    # ── Footer ────────────────────────────────────────────────────────
    st.sidebar.markdown("""
<div style="
    margin-top:1.5rem;
    padding-top:1rem;
    border-top:1px solid rgba(61,73,71,0.2);
">
    <div style="
        padding:0.75rem;
        font-family:ui-monospace,monospace;
        font-size:0.6rem;
        color:#3d4947;
        text-transform:uppercase;
        letter-spacing:0.08em;
        line-height:1.8;
    ">
        IDX &nbsp;|&nbsp; Paper Trading<br/>
        Navigation via sidebar
    </div>
</div>
""", unsafe_allow_html=True)

    return selected
