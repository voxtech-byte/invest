"""
Kinetic Ledger — Input Field Component

Renders a Streamlit text input styled with the Kinetic Ledger design system.
The design_system.css already overrides .stTextInput styles:
  - background: var(--surface-container-highest) = #353535
  - border: none, border-bottom: 1px solid rgba(61,73,71,0.2)
  - border-radius: 4px 4px 0 0
  - font-family: var(--font-mono)
  - focus: border-bottom-color transitions to var(--primary) = #66d9cc

Usage:
    from components.input_field import render_input_field

    ticker = render_input_field(
        label="Add Ticker",
        key="settings_ticker",
        placeholder="e.g. BBCA.JK",
    )
    if ticker:
        st.write(f"You entered: {ticker}")
"""
import streamlit as st


def render_input_field(
    label: str,
    key: str,
    placeholder: str = "",
    value: str = "",
) -> str:
    """
    Renders a Kinetic Ledger styled text input.

    Wraps st.text_input() with a consistent label style using the
    kl-label-sm CSS class. The design_system.css handles all visual
    overrides for the underlying Streamlit widget.

    Args:
        label: Input label text displayed above the field.
        key: Unique Streamlit widget key (required for state management).
        placeholder: Placeholder text shown when the field is empty.
        value: Default/initial value for the field.

    Returns:
        Current string value of the input field.
    """
    # Render label with design system typography
    st.markdown(
        f'<div class="kl-label-sm" style="margin-bottom:4px;">{label}</div>',
        unsafe_allow_html=True,
    )

    # Render the native Streamlit input (styled by design_system.css overrides)
    result = st.text_input(
        label="",           # label hidden — we render our own above
        key=key,
        placeholder=placeholder,
        value=value,
        label_visibility="collapsed",
    )

    return result or ""
