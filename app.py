import streamlit as st
import pandas as pd
import os
import sys
import time
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
import pytz
import plotly.graph_objects as go

# ── Sovereign Modules ──────────────────────────────────────
from core.utils import load_config, format_rp, TIMEZONE
from core.indicators import calculate_indicators
from core.signals import evaluate_signals, evaluate_exit_conditions
from core.executive import (
    calculate_position_size, check_safety_gates,
    check_sector_exposure, check_liquidity,
    calculate_kelly_suggestion, run_scenario_analysis
)
from core.dark_pool import detect_hidden_flows
from core.monte_carlo import run_monte_carlo
from core.black_swan import detect_black_swan_event
from core.config_validator import validate_config
from core.health_check import check_health
from data.data_fetcher import fetch_data, fetch_ihsg
from data.database import DatabaseManager
from integrations.news_aggregator import fetch_indonesia_market_news
from ui.terminal_style import inject_terminal_theme
from mock_broker import MockBroker
from google_sheets_logger import GoogleSheetsLogger

# ── Kinetic Ledger Components ──────────────────────────────
from components.metric_card import render_metric_card, render_metric_row
from components.data_table import render_kinetic_table
from components.status_indicator import render_status_indicator, render_status_group
from components.navigation import render_topnav, render_page_header, render_sidebar_nav
from components.input_field import render_input_field

# =====================================================================
# INITIALIZATION
# =====================================================================
if 'is_demo' not in st.session_state:
    st.session_state.is_demo = "--demo" in sys.argv

st.set_page_config(
    page_title="Kinetic Ledger" + (" (DEMO)" if st.session_state.is_demo else ""),
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_terminal_theme()

# Session state defaults
if 'kl_active_view' not in st.session_state: st.session_state.kl_active_view = "command"
if 'auto_pilot' not in st.session_state: st.session_state.auto_pilot = False
if 'stock_idx' not in st.session_state: st.session_state.stock_idx = 0
if 'scan_results' not in st.session_state: st.session_state.scan_results = []
if 'terminal_log' not in st.session_state: st.session_state.terminal_log = []
if 'news_data' not in st.session_state: st.session_state.news_data = []
if 'alert_history' not in st.session_state: st.session_state.alert_history = []

config = load_config()
_config_issues = validate_config(config)
db = DatabaseManager()
broker = MockBroker(initial_equity=config.get('portfolio', {}).get('initial_equity', 50000000))

gs_cfg = config.get('google_sheets', {})
sheet_logger = GoogleSheetsLogger(
    sheet_id=gs_cfg.get('spreadsheet_id'),
    credentials_file=gs_cfg.get('credentials_file', 'service_account.json')
)

# =====================================================================
# CACHING & HELPERS
# =====================================================================
@st.cache_data(ttl=300)
def get_cached_ihsg(_config):
    return fetch_ihsg(_config)

def log_to_terminal(msg, is_critical=False):
    ts = datetime.now(TIMEZONE).strftime("%H:%M:%S")
    color = "#ffb3ac" if is_critical else "#66d9cc"
    prefix = "ALERT" if is_critical else ">"
    st.session_state.terminal_log.insert(0, f'<span style="color:{color}">[{ts}] {prefix} {msg}</span>')
    st.session_state.terminal_log = st.session_state.terminal_log[:30]

def compile_institutional_data(selected_tickers, config, ihsg_data=None):
    """Compile master summary table for CSV export."""
    summary_list = []
    progress_bar = st.sidebar.progress(0)
    for i, ticker in enumerate(selected_tickers):
        df = fetch_data(ticker, config)
        if df is not None:
            df = calculate_indicators(df, config)
            signal, summary, reason = evaluate_signals(ticker, df, config, ihsg_data=ihsg_data)
            if summary:
                last_row = df.iloc[-1]
                summary['rsi'] = last_row.get(f"RSI_{config['indicators']['rsi_length']}", 0)
                summary['sma_50'] = last_row.get('SMA_50', 0)
                summary['sma_200'] = last_row.get(f"SMA_{config['indicators']['ma_long']}", 0)
                summary['adx'] = last_row.get('ADX_14', 0)
                summary['volume_ratio'] = last_row['Volume'] / last_row['Vol_Avg'] if last_row.get('Vol_Avg', 0) > 0 else 1.0
                clean_row = {
                    "Ticker": summary['symbol'], "Price": summary['close'],
                    "Conviction": summary['conviction'], "Phase": summary['wyckoff_phase'],
                    "Target_1": summary['target_1'], "Stop_Loss": summary['stop_loss'],
                    "Weekly_Trend": summary.get('weekly_trend'),
                    "BEE_SmartMoney": summary['bee_label'],
                    "RSI": round(summary['rsi'], 1),
                    "Vol_Ratio": round(summary['volume_ratio'], 2),
                    "MC_Profit_Prob": f"{summary.get('mc_prob_profit', 0)}%",
                    "MC_Risk": summary.get('mc_risk_rating', 'N/A'),
                    "Market_Reason": reason
                }
                summary_list.append(clean_row)
        progress_bar.progress((i + 1) / len(selected_tickers))
    if not summary_list:
        return None
    return pd.DataFrame(summary_list).to_csv(index=False).encode('utf-8')


# =====================================================================
# PURE HELPER FUNCTIONS (testable, no Streamlit dependencies)
# =====================================================================

def get_conviction_color_class(score: float) -> str:
    """Map conviction score (0-10) to a Kinetic Ledger color class.

    Returns:
        "profit"  when score >= 6.5  (#88d982 emerald)
        "neutral" when 4.5 <= score < 6.5  (#e5e2e1 on-surface)
        "loss"    when score < 4.5  (#ffb3ac crimson)
    """
    if score >= 6.5:
        return "profit"
    elif score >= 4.5:
        return "neutral"
    else:
        return "loss"


def get_pnl_color_class(pnl: float) -> str:
    """Map a P&L value to a Kinetic Ledger color class.

    Returns:
        "profit" when pnl >= 0
        "loss"   when pnl < 0
    """
    return "profit" if pnl >= 0 else "loss"


def get_sector_bar_color(pct: float) -> str:
    """Map a sector allocation percentage to a bar color.

    Returns:
        "#ffb3ac" (crimson/risk) when pct > 40
        "#66d9cc" (teal/primary) otherwise
    """
    return "#ffb3ac" if pct > 40 else "#66d9cc"


def add_ticker_if_not_exists(tickers: list, ticker: str) -> list:
    """Add ticker to list only if it doesn't already exist.

    Args:
        tickers: Current list of ticker strings.
        ticker: Ticker to add.

    Returns:
        Original list unchanged if ticker exists, otherwise list with ticker appended.
    """
    if ticker in tickers:
        return tickers
    return tickers + [ticker]


# =====================================================================
# LOAD GLOBAL DATA
# =====================================================================
ihsg = get_cached_ihsg(config)


# =====================================================================
# TOP NAVIGATION
# =====================================================================
render_topnav(active_view=st.session_state.kl_active_view)

# Navigation via sidebar
with st.sidebar:
    selected_view = render_sidebar_nav(active_view=st.session_state.kl_active_view)


# =====================================================================
# VIEW 1: TRADING COMMAND CENTER
# =====================================================================
def view_command():
    try:
        render_page_header("Trading Command Center")

        # ── Hero Chart Area ──
        active_sym = st.session_state.get('active_symbol', 'STANDBY')

        if 'current_df' in st.session_state and active_sym != 'STANDBY':
            df_display = st.session_state.current_df

            if df_display is None or df_display.empty:
                st.markdown("""
<div style="background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; height:420px; display:flex; align-items:center; justify-content:center; color:#bcc9c6; font-family:ui-monospace,monospace; font-size:0.85rem;">
    SELECT TARGET OR ENABLE AUTO-PILOT TO INITIATE STREAMING
</div>
""", unsafe_allow_html=True)
            else:
                # Chart header
                try:
                    last_close = df_display['Close'].iloc[-1]
                    prev_close = df_display['Close'].iloc[-2] if len(df_display) > 1 else last_close
                    change = last_close - prev_close
                    change_pct = (change / prev_close * 100) if prev_close > 0 else 0
                except (IndexError, KeyError):
                    last_close, change, change_pct = 0, 0, 0
                change_color = "#88d982" if change >= 0 else "#ffb3ac"
                arrow = "arrow_upward" if change >= 0 else "arrow_downward"

                st.markdown(f"""
<div style="padding:1rem 1.25rem; margin-bottom:1rem; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="display:flex; justify-content:space-between; align-items:center;">
<div style="display:flex; align-items:baseline; gap:1rem;">
<span style="font-family:'Inter',sans-serif; font-size:1.25rem; font-weight:700; color:#e5e2e1;">{active_sym.split('.')[0]}</span>
<span style="color:#bcc9c6; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.875rem; color:#e5e2e1;">{format_rp(last_close)}</span>
<span style="color:{change_color}; display:flex; align-items:center; gap:2px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">
<span class="material-symbols-outlined" style="font-size:14px;">{arrow}</span>
{change_pct:+.2f}%
</span>
</div>
</div>
</div>
""", unsafe_allow_html=True)

                # Candlestick chart
                fig = go.Figure(data=[go.Candlestick(
                    x=df_display.index,
                    open=df_display['Open'], high=df_display['High'],
                    low=df_display['Low'], close=df_display['Close'],
                    increasing_line_color='#88d982', decreasing_line_color='#ffb3ac',
                    increasing_fillcolor='#88d982', decreasing_fillcolor='#ffb3ac',
                )])
                fig.update_layout(
                    template='plotly_dark',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='#202020',
                    margin=dict(l=0, r=50, t=10, b=30),
                    height=380,
                    xaxis_rangeslider_visible=False,
                    xaxis=dict(gridcolor='rgba(61,73,71,0.1)', showgrid=True),
                    yaxis=dict(gridcolor='rgba(61,73,71,0.1)', showgrid=True, side='right'),
                    font=dict(family="ui-monospace, SFMono-Regular, monospace", size=10, color="#bcc9c6"),
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

                # Monte Carlo
                col_mc_btn, col_mc_res = st.columns([1, 2])
                with col_mc_btn:
                    if st.button("Monte Carlo Stress Test", use_container_width=True, type="secondary", key="mc_btn"):
                        with st.spinner("Simulating 1,000 market paths..."):
                            mc_res = run_monte_carlo(df_display)
                            st.session_state.mc_results = mc_res

                if 'mc_results' in st.session_state:
                    mc = st.session_state.mc_results
                    if "error" not in mc:
                        with col_mc_res:
                            risk_color = "#ffb3ac" if mc.get('risk_rating') == 'HIGH' else "#66d9cc" if mc.get('risk_rating') == 'LOW' else "#bcc9c6"
                            st.markdown(f"""
<div style="border-left-color:#66d9cc; background:#0e0e0e; border:1px solid rgba(61,73,71,0.1); border-left:2px solid #66d9cc; border-radius:4px; padding:0.75rem; font-family:ui-monospace,monospace; font-size:0.6875rem; line-height:1.8; color:#bcc9c6;">
<span style="font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Prob. Profit:</span> <span style="color:#66d9cc; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">{mc.get('prob_profit', 0)}%</span>
&nbsp;&nbsp;
<span style="font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">VaR 95 (10D):</span> <span style="color:#ffb3ac; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">{mc.get('var_pct', 0)}%</span>
&nbsp;&nbsp;
<span style="font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Risk:</span> <span style="color:{risk_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">{mc.get('risk_rating', 'N/A')}</span>
</div>
""", unsafe_allow_html=True)
        else:
            st.markdown("""
<div style="background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; height:420px; display:flex; align-items:center; justify-content:center; color:#bcc9c6; font-family:ui-monospace,monospace; font-size:0.85rem; letter-spacing:0.05em;">
    SELECT TARGET OR ENABLE AUTO-PILOT TO INITIATE STREAMING
</div>
""", unsafe_allow_html=True)

        # ── 3 Metric Cards ──
        bal = broker.get_balance()
        positions = broker.get_open_positions()
        daily_pnl = broker.get_daily_realized_pnl()
        pnl_color = get_pnl_color_class(daily_pnl)
        pnl_prefix = "+" if daily_pnl >= 0 else ""

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        render_metric_row([
            {"label": "Portfolio Balance", "value": format_rp(bal), "icon": "account_balance_wallet"},
            {"label": "Daily P&L", "value": f"{pnl_prefix}{format_rp(daily_pnl)}", "color": pnl_color, "icon": "trending_up" if daily_pnl >= 0 else "trending_down"},
            {"label": "Open Positions", "value": str(len(positions)), "subtitle": "Actively Managed", "icon": "folder_open"},
        ])

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        # ── Layout: Execution Log + Scan Status ──
        col_log, col_scan = st.columns([7, 3])

        with col_log:
            import re
            log_rows = []
            for entry in st.session_state.terminal_log[:15]:
                clean = re.sub(r'<[^>]+>', '', entry)
                parts = clean.strip().split('] ', 1)
                ts_text = parts[0].replace('[', '') if len(parts) > 1 else "--:--:--"
                msg = parts[1] if len(parts) > 1 else clean

                msg_upper = msg.upper()
                if "BUY" in msg_upper:
                    log_color = "buy"
                elif "SELL" in msg_upper or "EXIT" in msg_upper:
                    log_color = "sell"
                elif "ALERT" in msg_upper or "ERROR" in msg_upper or "CIRCUIT" in msg_upper:
                    log_color = "loss"
                else:
                    log_color = "muted"

                log_rows.append({
                    "cells": [ts_text, msg[:80]],
                    "colors": ["muted", log_color],
                })

            if not log_rows:
                log_rows = [{"cells": ["--:--:--", "Awaiting system activity..."], "colors": ["muted", "muted"]}]

            render_kinetic_table(
                headers=["Time", "Event"],
                rows=log_rows,
                align=["left", "left"],
                title="Execution Log",
                show_filter=False,
                max_height="280px",
            )

        with col_scan:
            # System Conviction Gauge
            avg_conviction = 0.0
            if st.session_state.scan_results:
                avg_conviction = sum(s['conviction'] for s in st.session_state.scan_results) / len(st.session_state.scan_results)

            conv_pct = min(100, int(avg_conviction * 10))
            conv_color = "#88d982" if conv_pct >= 65 else "#66d9cc" if conv_pct >= 45 else "#ffb3ac"
            bias_label = "Bullish Bias" if conv_pct >= 60 else "Neutral" if conv_pct >= 40 else "Bearish Bias"
            offset = round(283 - (283 * conv_pct / 100), 1)

            st.markdown(f"""
<div style="display:flex; flex-direction:column; align-items:center; padding:1.25rem; margin-bottom:8px; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
    <span style="width:100%; margin-bottom:1.5rem; font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">System Conviction</span>
    <div style="position:relative; width:160px; height:160px; display:flex; align-items:center; justify-content:center;">
        <svg style="width:100%; height:100%; transform:rotate(-90deg);" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="45" fill="none" stroke="#2a2a2a" stroke-width="8"></circle>
            <circle cx="50" cy="50" r="45" fill="none" stroke="{conv_color}" stroke-width="8"
                    stroke-dasharray="283" stroke-dashoffset="{offset}" stroke-linecap="round"></circle>
        </svg>
        <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center;">
            <div style="font-size:2rem; font-weight:700; color:{conv_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">{conv_pct}%</div>
            <div style="color:{conv_color}; margin-top:4px; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">{bias_label}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

            # Scan Status
            from core.utils import is_market_open
            market_open = is_market_open()
            statuses = [
                {"label": "Alpha Engine", "description": "Demo Mode" if st.session_state.is_demo else "Online", "status": "online"},
                {"label": "Market Feed", "description": "Active" if market_open else "Closed", "status": "online" if market_open else "offline"},
            ]
            if ihsg:
                ihsg_pct = ihsg.get('percent', 0)
                statuses.append({
                    "label": "IHSG",
                    "description": f"{ihsg_pct:+.2f}%",
                    "status": "online" if ihsg_pct >= 0 else "warning",
                })
            render_status_group("Scan Status", statuses)

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            ap_toggle = st.toggle("AUTO-PILOT", value=st.session_state.auto_pilot, key="ap_toggle_cmd")
            if ap_toggle != st.session_state.auto_pilot:
                st.session_state.auto_pilot = ap_toggle
                st.rerun()

            if st.button("Re-Scan", use_container_width=True, type="primary", key="rescan_btn"):
                st.session_state.stock_idx = 0
                st.session_state.auto_pilot = True
                st.rerun()

    except Exception as e:
        st.error(f"Command Center error: {e}")


# =====================================================================
# VIEW 2: PORTFOLIO ANALYTICS
# =====================================================================
def view_portfolio():
    try:
        render_page_header("Portfolio Analytics", actions=[{"label": "Export", "icon": "download", "style": "secondary"}])

        # 2x2 Grid
        top_left, top_right = st.columns(2)

        # ── Equity Curve ──
        with top_left:
            st.markdown("""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
    <div style="padding:1rem 1.25rem; border-bottom:1px solid rgba(61,73,71,0.2); background:#1b1b1c; display:flex; justify-content:space-between; align-items:center;">
        <span style="font-family:ui-monospace,monospace; font-size:0.6875rem; font-weight:400; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Equity Curve</span>
        <div style="display:flex; gap:1rem;">
            <div style="display:flex; align-items:center; gap:6px;">
                <span style="width:6px; height:6px; border-radius:50%; background:#66d9cc;"></span>
                <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.625rem; color:#bcc9c6; letter-spacing:0.05em;">PORTFOLIO</span>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

            try:
                eq_data = db.get_equity_snapshots() if hasattr(db, 'get_equity_snapshots') else []
            except Exception:
                eq_data = []

            if eq_data and len(eq_data) >= 2:
                eq_df = pd.DataFrame(eq_data)
                date_col = 'snapshot_date' if 'snapshot_date' in eq_df.columns else 'date'
                eq_df['date'] = pd.to_datetime(eq_df[date_col], errors='coerce')
                eq_df = eq_df.dropna(subset=['date']).sort_values('date')
                val_col = 'total_equity' if 'total_equity' in eq_df.columns else 'balance'

                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    x=eq_df['date'], y=eq_df[val_col],
                    name='Portfolio', mode='lines',
                    line=dict(color='#66d9cc', width=1.5),
                ))
                initial_eq = config.get('portfolio', {}).get('initial_equity', 50_000_000)
                fig_eq.add_hline(
                    y=initial_eq, line_dash='dash', line_color='#3d4947',
                    annotation_text=f'Initial: {format_rp(initial_eq)}',
                    annotation_font_color='#bcc9c6', annotation_font_size=9,
                )
                fig_eq.update_layout(
                    template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='#202020', height=280,
                    margin=dict(l=0, r=50, t=10, b=30),
                    yaxis=dict(gridcolor='rgba(61,73,71,0.1)', side='right'),
                    xaxis=dict(gridcolor='rgba(61,73,71,0.1)'),
                    font=dict(family="ui-monospace, monospace", size=9, color="#bcc9c6"),
                    showlegend=False,
                )
                st.plotly_chart(fig_eq, use_container_width=True, config={'displayModeBar': False})
            else:
                st.markdown(
                    '<div style="padding:3rem; text-align:center; color:#bcc9c6; font-family:ui-monospace,monospace; font-size:0.8rem;">Equity data will appear after the first sweep cycle.</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("</div>", unsafe_allow_html=True)

        # ── Drawdown Tracker ──
        with top_right:
            peak = getattr(broker, 'peak_equity', broker.initial_equity)
            current = broker.get_balance()
            dd_pct = ((peak - current) / peak * 100) if peak > 0 else 0.0
            max_dd = config.get('portfolio', {}).get('max_drawdown_pct', 15.0)
            dd_color = "#ffb3ac" if dd_pct > 5 else "#bcc9c6"

            st.markdown(f"""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:1rem 1.25rem; border-bottom:1px solid rgba(61,73,71,0.2); background:#1b1b1c; display:flex; justify-content:space-between; align-items:center;">
<span style="font-family:ui-monospace,monospace; font-size:0.6875rem; font-weight:400; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Drawdown Tracker</span>
<span style="color:{dd_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.875rem; color:#e5e2e1;">-{dd_pct:.1f}%</span>
</div>
<div style="padding:2rem; text-align:center;">
<div style="font-size:2.5rem; color:{dd_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">-{dd_pct:.1f}%</div>
<div style="margin-top:0.5rem; font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">YTD Peak-to-Trough</div>
<div style="margin-top:1rem; display:flex; justify-content:space-between; padding-top:1rem; border-top:1px solid rgba(61,73,71,0.2);">
<div style="text-align:center;">
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Limit</div>
<div style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{max_dd}%</div>
</div>
<div style="text-align:center;">
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Peak Equity</div>
<div style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{format_rp(peak)}</div>
</div>
<div style="text-align:center;">
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Current</div>
<div style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{format_rp(current)}</div>
</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

        # ── Active Positions Table + Sector Exposure ──
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        bot_left, bot_right = st.columns(2)

        with bot_left:
            open_pos = broker.get_open_positions()
            pos_rows = []
            for sym, pos in open_pos.items():
                avg_p = pos.get('avg_price', 0)
                latest = next((s for s in st.session_state.scan_results if s['symbol'] == sym), None)
                curr_price = latest['close'] if latest else avg_p
                pnl_pct = ((curr_price - avg_p) / avg_p * 100) if avg_p > 0 else 0.0
                pnl_color = get_pnl_color_class(pnl_pct)

                pos_rows.append({
                    "cells": [sym.split('.')[0], format_rp(avg_p), format_rp(curr_price), f"{pnl_pct:+.2f}%"],
                    "colors": ["primary", "muted", "muted", pnl_color],
                })

            if not pos_rows:
                pos_rows = [{"cells": ["--", "--", "--", "--"], "colors": ["muted"] * 4}]

            render_kinetic_table(
                headers=["Symbol", "Avg Price", "Current", "P&L %"],
                rows=pos_rows,
                align=["left", "right", "right", "right"],
                title="Active Positions",
                show_filter=False,
            )

        with bot_right:
            sectors_map = config.get('sectors', {})
            sector_alloc: dict[str, int] = {}

            if open_pos:
                for sym in open_pos:
                    sec = sectors_map.get(sym, 'Other')
                    sector_alloc[sec] = sector_alloc.get(sec, 0) + 1
                total = sum(sector_alloc.values())

                st.markdown("""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:1rem 1.25rem; border-bottom:1px solid rgba(61,73,71,0.2); background:#1b1b1c;">
<span style="font-family:ui-monospace,monospace; font-size:0.6875rem; font-weight:400; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Sector Exposure</span>
</div>
<div style="padding:1rem;">
""", unsafe_allow_html=True)

                for sec, count in sorted(sector_alloc.items(), key=lambda x: x[1], reverse=True):
                    pct = (count / total * 100) if total > 0 else 0.0
                    bar_color = get_sector_bar_color(pct)
                    st.markdown(f"""
<div style="margin-bottom:0.75rem;">
<div style="display:flex; justify-content:space-between; margin-bottom:4px;">
<span style="color:#e5e2e1; text-transform:uppercase; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{sec}</span>
<span style="color:{bar_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{pct:.0f}%</span>
</div>
<div style="width:100%; height:4px; background:#353535; border-radius:2px; overflow:hidden;">
<div style="width:{pct}%; background:{bar_color}; height:100%; border-radius:2px;"></div>
</div>
</div>
""", unsafe_allow_html=True)

                st.markdown("</div></div>", unsafe_allow_html=True)
            else:
                st.markdown("""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:1rem 1.25rem; border-bottom:1px solid rgba(61,73,71,0.2); background:#1b1b1c;">
<span style="font-family:ui-monospace,monospace; font-size:0.6875rem; font-weight:400; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Sector Exposure</span>
</div>
<div style="padding:3rem; text-align:center; color:#bcc9c6; font-family:ui-monospace,monospace; font-size:0.8rem;">No open positions for sector analysis.</div>
</div>
""", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Portfolio Analytics error: {e}")


# =====================================================================
# VIEW 3: SIGNALS & INTELLIGENCE
# =====================================================================
def view_signals():
    try:
        render_page_header(
            "Signals & Intelligence",
            subtitle="Algorithmic scan results and institutional flow analysis.",
        )

        col_actions = st.columns([6, 1, 1])
        with col_actions[2]:
            if st.button("Run Scan", key="sig_scan", use_container_width=True, type="primary"):
                st.session_state.auto_pilot = True
                st.session_state.stock_idx = 0
                st.rerun()

        col_table, col_quality = st.columns([2, 1])

        with col_table:
            # Scan Results Table
            scan_rows = []
            for s in sorted(st.session_state.scan_results, key=lambda x: x['conviction'], reverse=True)[:15]:
                conv = s['conviction']
                conv_color = get_conviction_color_class(conv)

                vol_ratio = s.get('volume_ratio', s.get('vw_conviction_mod', 1.0))
                if not isinstance(vol_ratio, (int, float)):
                    vol_ratio = 1.0

                phase = s.get('wyckoff_phase', 'N/A')
                # Shorten phase labels for table display
                phase_short = (phase
                    .replace("SPRING — High Probability Reversal", "SPRING")
                    .replace("UPTHRUST — Distribusi Institusi", "UPTHRUST")
                    .replace("MARKUP (Strong Trend)", "MARKUP")
                    .replace("MARKDOWN (Stay Away)", "MARKDOWN")
                    .replace("ACCUMULATION (Smart Money Buying)", "ACCUM")
                    .replace("DISTRIBUTION (Institutions Selling)", "DIST")
                    .replace("CONSOLIDATION (Neutral)", "CONSOL")
                )
                if len(phase_short) > 18:
                    phase_short = phase_short[:16] + ".."

                smi = s.get('smi_10', 0)
                smi_str = f"{smi:+.2f}" if isinstance(smi, (int, float)) else "0.00"

                scan_rows.append({
                    "cells": [
                        s['symbol'].split('.')[0],
                        f"{conv:.1f}",
                        phase_short,
                        smi_str,
                        f"{vol_ratio:.1f}x",
                    ],
                    "colors": ["primary", conv_color, "muted", "", "muted"],
                })

            if not scan_rows:
                scan_rows = [{"cells": ["--", "--", "--", "--", "--"], "colors": ["muted"] * 5}]

            render_kinetic_table(
                headers=["Symbol", "Conviction", "Wyckoff Phase", "SMI", "Vol Ratio"],
                rows=scan_rows,
                align=["left", "right", "left", "right", "right"],
                title="Scan Results",
                subtitle=f"UPDATED: {datetime.now(TIMEZONE).strftime('%H:%M:%S')} WIB",
                show_filter=False,
            )

            # Institutional Factors Cards
            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
            inst_left, inst_right = st.columns(2)

            with inst_left:
                scan_anomalies = sum(1 for s in st.session_state.scan_results if s.get('inst_footprint', 0) >= 60)
                dp_status = "Elevated" if scan_anomalies > 2 else "Normal"
                dp_color = "#ffb3ac" if scan_anomalies > 2 else "#88d982"
                st.markdown(f"""
<div style="min-height:120px; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="display:flex; justify-content:space-between; align-items:flex-start;">
<span style="font-family:'Inter',sans-serif; font-size:0.8rem; font-weight:400; color:#bcc9c6;">Institutional Flow</span>
<span style="width:6px; height:6px; border-radius:50%; background:{dp_color};"></span>
</div>
<div style="margin-top:0.75rem; color:{dp_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:1.5rem; font-weight:700; color:#e5e2e1;">{dp_status}</div>
<div style="margin-top:4px; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">{scan_anomalies} high-footprint stocks</div>
</div>
""", unsafe_allow_html=True)

            with inst_right:
                accum_count = sum(1 for s in st.session_state.scan_results if s.get('accum_days', 0) >= 3)
                accum_color = "#88d982" if accum_count > 0 else "#bcc9c6"
                st.markdown(f"""
<div style="min-height:120px; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="display:flex; justify-content:space-between; align-items:flex-start;">
<span style="font-family:'Inter',sans-serif; font-size:0.8rem; font-weight:400; color:#bcc9c6;">Accumulation Signals</span>
<span style="width:6px; height:6px; border-radius:50%; background:{accum_color};"></span>
</div>
<div style="margin-top:0.75rem; color:{accum_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:1.5rem; font-weight:700; color:#e5e2e1;">{accum_count}</div>
<div style="margin-top:4px; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Stocks with 3+ accum days</div>
</div>
""", unsafe_allow_html=True)

        with col_quality:
            history = broker.get_trade_history()
            sells = [t for t in history if t.get('action') == 'SELL']
            wins = sum(1 for t in sells if t.get('realized_pnl', 0) >= 0)
            win_rate = (wins / len(sells) * 100) if sells else 0.0
            wr_color = "#88d982" if win_rate >= 50 else "#ffb3ac"
            losing_count = len(sells) - wins
            total_count = len(sells)

            st.markdown(f"""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:1.25rem; border-bottom:1px solid rgba(61,73,71,0.2);">
<span style="font-family:'Inter',sans-serif; font-size:0.875rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#e5e2e1;">Signal Quality</span>
</div>
<div style="padding:1.25rem;">
<div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.5rem;">
<span style="font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Win Rate</span>
<span style="color:{wr_color}; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.875rem; color:#e5e2e1;">{win_rate:.1f}%</span>
</div>
<div style="height:6px; margin-bottom:1.5rem; width:100%; height:4px; background:#353535; border-radius:2px; overflow:hidden;">
<div style="width:{win_rate}%; background:{wr_color}; height:100%; border-radius:2px;"></div>
</div>
<div style="background:#1b1b1c; padding:1rem; border-radius:4px; border:1px solid rgba(61,73,71,0.1);">
<div style="margin-bottom:0.75rem; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">False Signal Tracker</div>
<div style="display:flex; justify-content:space-between; align-items:center;">
<div>
<div style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.875rem; color:#e5e2e1;">{losing_count}</div>
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Losing Trades</div>
</div>
<div style="text-align:right;">
<div style="color:#ffb3ac; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{losing_count} / {total_count}</div>
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">All Time</div>
</div>
</div>
</div>
<div style="margin-top:1rem; padding-top:1rem; border-top:1px solid rgba(61,73,71,0.1);">
<div style="margin-bottom:0.5rem; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Scanned Universe</div>
<div style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.875rem; color:#e5e2e1;">{len(st.session_state.scan_results)}</div>
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Symbols processed</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Signals view error: {e}")


# =====================================================================
# VIEW 4: RISK MANAGEMENT
# =====================================================================
def view_risk():
    try:
        render_page_header("Risk Management", subtitle="Live Portfolio Exposure Analysis")

        col_gauge, col_scenario = st.columns([8, 4])

        with col_gauge:
            # Portfolio Heat Gauge
            total_risk = 0.0
            for sym, pos in broker.get_open_positions().items():
                qty = pos.get('quantity', 0)
                avg_p = pos.get('avg_price', 0)
                sl = pos.get('stop_loss', avg_p * 0.95)
                total_risk += qty * abs(avg_p - sl)

            balance = broker.get_balance()
            heat_pct = (total_risk / balance * 100) if balance > 0 else 0.0
            max_heat = config.get('portfolio', {}).get('max_portfolio_heat_pct', 6.0)

            heat_normalized = min(100.0, (heat_pct / max_heat) * 100 if max_heat > 0 else 0.0)
            offset = round(283 - (283 * heat_normalized / 100), 1)
            heat_color = "#ffb3ac" if heat_normalized > 80 else "#bcc9c6" if heat_normalized > 50 else "#66d9cc"
            heat_label = "High Exposure" if heat_normalized > 80 else "Moderate" if heat_normalized > 50 else "Low Exposure"

            st.markdown(f"""
<div style="display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:300px; position:relative; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<span style="position:absolute; top:1rem; left:1rem; font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Portfolio Heat</span>
<div style="position:relative; width:192px; height:192px; margin-top:1rem;">
<svg style="width:100%; height:100%; transform:rotate(-90deg);" viewBox="0 0 100 100">
<circle cx="50" cy="50" r="45" fill="none" stroke="#353535" stroke-width="2"></circle>
<circle cx="50" cy="50" r="45" fill="none" stroke="{heat_color}" stroke-width="4"
stroke-dasharray="283" stroke-dashoffset="{offset}" stroke-linecap="round"></circle>
</svg>
<div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center;">
<span style="font-size:2.5rem; color:{heat_color}; font-weight:700; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">{heat_pct:.0f}<span style="font-size:1.25rem;">%</span></span>
<span style="color:{heat_color}; margin-top:4px; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">{heat_label}</span>
</div>
</div>
<div style="width:100%; display:flex; justify-content:space-around; margin-top:2rem; padding-top:1rem; border-top:1px solid rgba(61,73,71,0.2);">
<div style="text-align:center;">
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Heat Limit</div>
<div style="margin-top:4px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{max_heat}%</div>
</div>
<div style="text-align:center;">
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Risk Capital</div>
<div style="color:#ffb3ac; margin-top:4px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{format_rp(total_risk)}</div>
</div>
<div style="text-align:center;">
<div style="font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Balance</div>
<div style="margin-top:4px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{format_rp(balance)}</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

        with col_scenario:
            # Fixed -5% Scenario (no interactive slider per design spec)
            scenario = run_scenario_analysis(broker, config, ihsg_shock_pct=-5.0)
            kelly = calculate_kelly_suggestion(broker, 1000, 950, config)

            st.markdown(f"""
<div style="display:flex; flex-direction:column; gap:1rem; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="display:flex; align-items:center; gap:8px;">
<span class="material-symbols-outlined" style="color:#66d9cc; font-size:1rem;">science</span>
<span style="font-family:'Inter',sans-serif; font-size:0.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:0.1em; color:#bcc9c6;">Stress Test Scenario</span>
</div>
<div style="background:#2a2a2a; padding:1rem; border-radius:4px;">
<div style="margin-bottom:0.5rem; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">IF IHSG DROPS</div>
<div style="font-size:1.5rem; color:#ffb3ac; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">-5.0%</div>
<div style="border-top:1px solid rgba(61,73,71,0.2); margin-top:0.75rem; padding-top:0.75rem;">
<div style="margin-bottom:4px; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">PORTFOLIO IMPACT</div>
<div style="font-size:1.25rem; color:#ffb3ac; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">{format_rp(scenario['total_estimated_loss'])}</div>
<div style="margin-top:4px; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.625rem; color:#bcc9c6; letter-spacing:0.05em;">({scenario['pct_of_equity']:+.1f}% of AUM)</div>
</div>
</div>
<div style="background:#1b1b1c; padding:1rem; border-radius:4px; border-left:2px solid #66d9cc;">
<div style="margin-bottom:4px; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">KELLY CRITERION</div>
<div style="font-family:'Inter',sans-serif; font-size:0.875rem; font-weight:400; color:#e5e2e1;">{kelly.get('label', 'INSUFFICIENT DATA')}</div>
<div style="margin-top:4px; color:#bcc9c6; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.625rem; color:#bcc9c6; letter-spacing:0.05em;">{kelly.get('note', '')[:60]}</div>
</div>
</div>
""", unsafe_allow_html=True)

        # Risk Status Cards
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        r1, r2, r3, r4 = st.columns(4)

        with r1:
            daily_pnl = broker.get_daily_realized_pnl()
            render_metric_card(
                "Daily P&L",
                f"{'+'if daily_pnl >= 0 else ''}{format_rp(daily_pnl)}",
                color=get_pnl_color_class(daily_pnl),
                icon="trending_up" if daily_pnl >= 0 else "trending_down",
            )

        with r2:
            peak_eq = getattr(broker, 'peak_equity', broker.initial_equity)
            dd = ((peak_eq - balance) / peak_eq * 100) if peak_eq > 0 else 0.0
            render_metric_card(
                "Max Drawdown",
                f"-{dd:.1f}%",
                color="loss" if dd > 5 else "neutral",
                subtitle="YTD Peak-to-Trough",
                icon="waterfall_chart",
            )

        with r3:
            active_count = len(broker.get_open_positions())
            render_metric_card(
                "Active Positions",
                str(active_count),
                subtitle="ACTIVE" if active_count > 0 else "IDLE",
                icon="folder_open",
            )

        with r4:
            stress_pass = heat_pct < max_heat
            render_metric_card(
                "Stress Test",
                "PASS" if stress_pass else "FAIL",
                color="profit" if stress_pass else "loss",
                subtitle=f"Heat: {heat_pct:.1f}% / {max_heat}%",
                icon="verified" if stress_pass else "warning",
            )

    except Exception as e:
        st.error(f"Risk Management error: {e}")


# =====================================================================
# VIEW 5: TRADE JOURNAL
# =====================================================================
def view_journal():
    try:
        render_page_header("Trade Journal", actions=[
            {"label": "Export CSV", "icon": "download", "style": "secondary"},
        ])

        history = broker.get_trade_history()
        sells = [t for t in history if t.get('action') == 'SELL']

        trade_rows = []
        for trade in reversed(sells[-20:]):
            realized_pnl = trade.get('realized_pnl', 0)
            pnl_pct = 0.0
            price = trade.get('price', 0)
            qty = trade.get('qty', 0)
            if price > 0 and qty > 0:
                cost_basis = price * qty
                pnl_pct = (realized_pnl / cost_basis) * 100

            pnl_color = get_pnl_color_class(realized_pnl)
            pnl_prefix = "+" if realized_pnl >= 0 else ""

            trade_rows.append({
                "cells": [
                    trade.get('symbol', 'N/A').split('.')[0],
                    "LONG",
                    format_rp(price),
                    f"{pnl_pct:+.1f}%",
                    f"{pnl_prefix}{format_rp(realized_pnl)}",
                    (trade.get('reason', '') or 'N/A')[:30],
                ],
                "colors": ["primary", "buy", "muted", pnl_color, pnl_color, "muted"],
            })

        if not trade_rows:
            trade_rows = [{"cells": ["--"] * 6, "colors": ["muted"] * 6}]

        render_kinetic_table(
            headers=["Symbol", "Type", "Price", "P&L %", "P&L (Rp)", "Reason"],
            rows=trade_rows,
            align=["left", "left", "right", "right", "right", "left"],
            title="Closed Trades",
            show_filter=False,
            max_height="350px",
        )

        # Monthly Performance Chart
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

        if sells:
            # Group P&L by month
            monthly: dict[str, float] = {}
            for t in sells:
                try:
                    dt = datetime.fromisoformat(t.get('date', ''))
                    key = dt.strftime('%b %Y')
                    monthly[key] = monthly.get(key, 0.0) + t.get('realized_pnl', 0.0)
                except Exception:
                    pass

            if monthly:
                m_df = pd.DataFrame([{"Month": k, "PnL": v} for k, v in monthly.items()])
                m_df['Color'] = m_df['PnL'].apply(lambda x: '#88d982' if x >= 0 else '#ffb3ac')

                st.markdown("""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:1rem 1.25rem; border-bottom:1px solid rgba(61,73,71,0.2); display:flex; justify-content:space-between; align-items:center;">
<div>
<span style="font-family:'Inter',sans-serif; font-size:0.875rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#e5e2e1;">Monthly Performance</span>
<div style="margin-top:4px; font-family:'Inter',sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Net P&L (Rp)</div>
</div>
<div style="display:flex; gap:1rem;">
<div style="display:flex; align-items:center; gap:6px;">
<span style="width:6px; height:6px; border-radius:50%; background:#88d982;"></span>
<span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.625rem; color:#bcc9c6; letter-spacing:0.05em;">Profit</span>
</div>
<div style="display:flex; align-items:center; gap:6px;">
<span style="width:6px; height:6px; border-radius:50%; background:#ffb3ac;"></span>
<span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.625rem; color:#bcc9c6; letter-spacing:0.05em;">Loss</span>
</div>
</div>
</div>
""", unsafe_allow_html=True)

                fig_m = go.Figure(data=[go.Bar(
                    x=m_df['Month'], y=m_df['PnL'],
                    marker_color=m_df['Color'].tolist(),
                    marker_line_width=0,
                )])
                fig_m.update_layout(
                    template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='#202020', height=220,
                    margin=dict(l=0, r=50, t=10, b=30),
                    yaxis=dict(gridcolor='rgba(61,73,71,0.1)', showgrid=True, side='right'),
                    xaxis=dict(gridcolor='rgba(61,73,71,0.1)'),
                    font=dict(family="ui-monospace, monospace", size=9, color="#bcc9c6"),
                    showlegend=False,
                )
                st.plotly_chart(fig_m, use_container_width=True, config={'displayModeBar': False})
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                '<div style="text-align:center; color:#bcc9c6; padding:2rem; font-family:ui-monospace,monospace; font-size:0.8rem; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">Trade history will appear after completed sell trades.</div>',
                unsafe_allow_html=True,
            )

    except Exception as e:
        st.error(f"Trade Journal error: {e}")


# =====================================================================
# VIEW 6: SETTINGS & CONFIGURATION
# =====================================================================
def view_settings():
    try:
        render_page_header("System Configuration", subtitle="Manage parameters and system health.")

        col_watch, col_params, col_health = st.columns(3)

        # ── Watchlist Manager ──
        with col_watch:
            st.markdown("""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:0.75rem 1rem; border-bottom:1px solid rgba(61,73,71,0.2); display:flex; justify-content:space-between; align-items:center;">
<span style="font-family:'Inter',sans-serif; font-size:0.875rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#e5e2e1;">Watchlist Manager</span>
<span class="material-symbols-outlined" style="color:#bcc9c6; font-size:1rem;">list_alt</span>
</div>
<div style="padding:1rem;">
""", unsafe_allow_html=True)

            current_stocks = config.get('stocks', [])
            st.markdown(f'<div style="margin-bottom:8px; font-family:Inter,sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">Tracking {len(current_stocks)} symbols</div>', unsafe_allow_html=True)

            # Use render_input_field component
            new_ticker = render_input_field(
                label="Add Ticker",
                key="settings_add_ticker",
                placeholder="e.g. BBCA.JK",
            )
            if st.button("Add Symbol", key="settings_add_btn", use_container_width=True):
                ticker = new_ticker.strip().upper()
                if ticker:
                    updated = add_ticker_if_not_exists(current_stocks, ticker)
                    if len(updated) > len(current_stocks):
                        import json
                        config['stocks'] = updated
                        with open('config.json', 'w') as f:
                            json.dump(config, f, indent=2)
                        st.success(f"Added {ticker}")
                        st.rerun()
                    else:
                        st.info(f"{ticker} already in watchlist")

            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            for stock in current_stocks[:12]:
                sector = config.get('sectors', {}).get(stock, 'Other')
                st.markdown(f"""
<div style="background:#2a2a2a; padding:0.5rem 0.75rem; border-radius:4px; margin-bottom:3px; display:flex; justify-content:space-between; align-items:center;">
<span style="color:#66d9cc; font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; font-size:0.75rem; color:#bcc9c6;">{stock.split('.')[0]}</span>
<span style="font-size:0.6rem; background:#0e0e0e; color:#bcc9c6; padding:2px 6px; border-radius:2px; text-transform:uppercase; letter-spacing:0.1em; border:1px solid rgba(61,73,71,0.2);">{sector}</span>
</div>
""", unsafe_allow_html=True)

            if len(current_stocks) > 12:
                st.markdown(f'<div style="margin-top:4px; font-family:Inter,sans-serif; font-size:0.625rem; font-weight:500; text-transform:uppercase; letter-spacing:0.12em; color:#bcc9c6;">+{len(current_stocks)-12} more symbols</div>', unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

        # ── Parameter Display (read-only) ──
        with col_params:
            ind_cfg = config.get('indicators', {})
            exec_cfg = config.get('execution', {})
            portfolio_cfg = config.get('portfolio', {})

            params = [
                ("RSI Length", ind_cfg.get('rsi_length', 14), "bars"),
                ("ATR Period", ind_cfg.get('atr_period', 14), "bars"),
                ("MA Short", ind_cfg.get('ma_short', 50), "bars"),
                ("MA Long", ind_cfg.get('ma_long', 200), "bars"),
                ("Auto-Trade Threshold", exec_cfg.get('auto_trade_threshold', 6.5), "/ 10"),
                ("Alert Threshold", exec_cfg.get('alert_only_threshold', 4.5), "/ 10"),
                ("Max Positions", portfolio_cfg.get('max_open_positions', 5), "slots"),
                ("Max Drawdown Limit", f"{portfolio_cfg.get('max_drawdown_pct', 15.0)}%", ""),
                ("Max Heat", f"{portfolio_cfg.get('max_portfolio_heat_pct', 6.0)}%", ""),
            ]

            params_rows = [
                {"cells": [name, str(val), unit], "colors": ["muted", "primary", "muted"]}
                for name, val, unit in params
            ]

            render_kinetic_table(
                headers=["Parameter", "Value", "Unit"],
                rows=params_rows,
                align=["left", "right", "left"],
                title="System Parameters",
                show_filter=False,
                max_height="320px",
            )

        # ── Health Check (last-known status, no ping button) ──
        with col_health:
            st.markdown("""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:0.75rem 1rem; border-bottom:1px solid rgba(61,73,71,0.2); display:flex; justify-content:space-between; align-items:center;">
<span style="font-family:'Inter',sans-serif; font-size:0.875rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#e5e2e1;">System Health</span>
<span class="material-symbols-outlined" style="color:#bcc9c6; font-size:1rem;">monitor_heart</span>
</div>
<div style="padding:0.5rem;">
""", unsafe_allow_html=True)

            hr = st.session_state.get('health_results', {})
            services = [
                ('supabase', 'Supabase DB'),
                ('telegram', 'Telegram API'),
                ('yfinance', 'Market Data'),
                ('google_sheets', 'Google Sheets'),
            ]
            for svc_key, svc_name in services:
                r = hr.get(svc_key, {})
                if r:
                    status = "online" if r.get('ok') else "warning"
                    desc = r.get('message', 'N/A')[:22]
                    meta = f"{r.get('latency_ms', 0):.0f}ms" if r.get('ok') else ""
                else:
                    status = "offline"
                    desc = "Not checked"
                    meta = ""
                render_status_indicator(svc_name, desc, status=status, meta=meta)

            # Terminal readout
            summary = hr.get('_summary', {})
            passed = summary.get('passed', 0)
            total = summary.get('total', 4)
            sys_status = f"{passed}/{total} OK" if hr else "UNCHECKED"
            st.markdown(f"""
<div style="margin-top:0.75rem; padding:0.75rem; background:#0e0e0e; border-radius:4px; border:1px solid rgba(61,73,71,0.1); font-family:ui-monospace,monospace; font-size:0.625rem; color:#bcc9c6; line-height:1.8;">
&gt; SYSTEM.STATUS: {sys_status}<br/>
&gt; LAST_SYNC: {datetime.now(TIMEZONE).strftime('%H:%M:%S')} WIB<br/>
&gt; MODE: {'DEMO' if st.session_state.is_demo else 'PAPER TRADING'}<br/>
&gt; LICENSE: {config.get('commercial', {}).get('terminal_version', 'V15-PRO')}
</div>
""", unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

        # Config warnings
        if _config_issues:
            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
            with st.expander(f"Configuration Warnings ({len(_config_issues)})", expanded=False):
                for issue in _config_issues[:5]:
                    st.warning(issue)

        # Data Hub Export
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        st.markdown("""
<div style="padding:0; overflow:hidden; background:#202020; border:1px solid rgba(61,73,71,0.2); border-radius:4px; padding:1.25rem;">
<div style="padding:0.75rem 1rem; border-bottom:1px solid rgba(61,73,71,0.2);">
<span style="font-family:'Inter',sans-serif; font-size:0.875rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:#e5e2e1;">Institutional Data Hub</span>
</div>
<div style="padding:1.25rem;">
""", unsafe_allow_html=True)

        stock_list = config.get('stocks', [])
        selected_for_download = st.multiselect(
            "Select Tickers to Export",
            options=stock_list,
            default=stock_list[:2] if stock_list else [],
            key="data_hub_select",
        )

        if st.button("Generate Data Hub CSV", use_container_width=True, type="primary", key="gen_csv"):
            if selected_for_download:
                with st.spinner("Assembling quant factors..."):
                    csv_data = compile_institutional_data(selected_for_download, config, ihsg_data=ihsg)
                    if csv_data:
                        ts = datetime.now().strftime("%Y%m%d_%H%M")
                        st.download_button(
                            "Download Complete Dataset",
                            csv_data,
                            f"kinetic_export_{ts}.csv",
                            "text/csv",
                            use_container_width=True,
                        )
                        st.success("Dataset compiled successfully.")
                    else:
                        st.error("Failed to compile dataset.")
            else:
                st.warning("Select at least one ticker.")

        st.markdown("</div></div>", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Settings error: {e}")


# =====================================================================
# VIEW ROUTER
# =====================================================================
view_map = {
    "command":   view_command,
    "portfolio": view_portfolio,
    "signals":   view_signals,
    "risk":      view_risk,
    "journal":   view_journal,
    "settings":  view_settings,
}

current_view = st.session_state.get('kl_active_view', 'command')
view_fn = view_map.get(current_view, view_command)
try:
    view_fn()
except Exception as e:
    st.error(f"Failed to render view '{current_view}': {e}")


# =====================================================================
# AUTO-PILOT STATE MACHINE
# =====================================================================
if st.session_state.auto_pilot:
    try:
        stocks = config.get('stocks', [])
        exec_cfg = config.get('execution', {})
        idx = st.session_state.stock_idx

        # ── PHASE 0: EXIT MANAGEMENT ──
        if idx == 0:
            log_to_terminal("Phase 0: Active Position Management (Stop/Trail/TP)...")
            open_positions = dict(broker.get_open_positions())
            for sym, pos in open_positions.items():
                try:
                    df_exit = fetch_data(sym, config)
                    if df_exit is None or df_exit.empty:
                        continue
                    df_exit = calculate_indicators(df_exit, config)
                    current_price = df_exit['Close'].iloc[-1]

                    exit_type, exit_reason = evaluate_exit_conditions(
                        sym, df_exit, config, position=pos, ihsg_data=ihsg
                    )

                    if exit_type == "PARTIAL_TP1":
                        tp1_pct = exec_cfg.get('tp1_scale_out_pct', 50)
                        sell_qty = int(pos['quantity'] * (tp1_pct / 100))
                        sell_qty = (sell_qty // 100) * 100
                        if sell_qty >= 100:
                            log_to_terminal(f"TP1 HIT: {sym} -- Selling {tp1_pct}%", is_critical=True)
                            success, res = broker.execute_sell(sym, current_price, lot=sell_qty, reason=f"Partial TP1: {exit_reason}")
                            if success:
                                sheet_logger.log_trade(sym, "SELL", current_price, sell_qty, reason=f"Terminal Partial TP1")
                                remaining = broker.get_open_positions().get(sym)
                                if remaining:
                                    remaining['tp1_hit'] = True
                                    broker._save_positions()

                    elif exit_type == "AUTO_TRADE_SELL":
                        log_to_terminal(f"EXIT: {sym} -- {exit_reason}", is_critical=True)
                        success, res = broker.execute_sell(sym, current_price, reason=f"Exit: {exit_reason}")
                        if success:
                            sheet_logger.log_trade(sym, "SELL", current_price, pos['quantity'], reason=f"Auto-Pilot Exit ({exit_reason})")
                            ts = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
                            st.session_state.alert_history.append(f"[{ts}] SELL {sym.split('.')[0]} @ {format_rp(current_price)} -- {exit_reason}")
                except Exception as e:
                    log_to_terminal(f"Exit error {sym}: {e}", is_critical=True)

        # ── PHASE 1: TARGET SCANNING ──
        symbol = stocks[idx]
        st.session_state.active_symbol = symbol

        log_to_terminal(f"Scanning target: {symbol}...")
        if 'mc_results' in st.session_state:
            del st.session_state.mc_results

        df = fetch_data(symbol, config)
        if df is not None and len(df) >= 60:
            df = calculate_indicators(df, config)
            st.session_state.current_df = df

            last_row = df.iloc[-1]
            is_liquid, liq_reason = check_liquidity(last_row, config)
            if not is_liquid:
                log_to_terminal(f"{symbol} skipped: {liq_reason}")
            else:
                anomaly = detect_hidden_flows(df, config)
                if anomaly['detected']:
                    log_to_terminal(f"DARK POOL DETECTED: {symbol}", is_critical=True)

                swan = detect_black_swan_event(df)
                if swan['alert']:
                    log_to_terminal(f"BLACK SWAN ALERT: {symbol}", is_critical=True)

                current_pos = broker.get_open_positions().get(symbol)
                signal, summary, reason = evaluate_signals(
                    symbol, df, config, ihsg_data=ihsg, open_position=current_pos
                )

                if summary:
                    st.session_state.scan_results = [s for s in st.session_state.scan_results if s['symbol'] != symbol]
                    st.session_state.scan_results.append(summary)
                    log_to_terminal(f"Processed {symbol}: Score {summary['conviction']}/10 | {summary.get('weekly_trend', 'N/A')}")

                    # BUY execution
                    if signal['type'] == "AUTO_TRADE_BUY" and current_pos is None:
                        is_safe, safety_warnings = check_safety_gates(broker, ihsg, config)
                        sector_warn = check_sector_exposure(symbol, broker.get_open_positions(), config)

                        if is_safe and not sector_warn:
                            lot, pos_value, risk_tier = calculate_position_size(
                                summary['close'], summary['stop_loss'],
                                summary['conviction'], config, ihsg_data=ihsg
                            )
                            if lot > 0:
                                from datetime import timedelta
                                last_sell = next((t for t in reversed(broker.get_trade_history())
                                                if t['symbol'] == symbol and t['action'] == 'SELL'), None)
                                in_cooldown = False
                                if last_sell:
                                    try:
                                        last_exit_date = datetime.fromisoformat(last_sell['date'])
                                        cooldown_days = config.get('signals', {}).get('reentry_cooldown_days', 3)
                                        if datetime.now(TIMEZONE) - last_exit_date < timedelta(days=cooldown_days):
                                            in_cooldown = True
                                    except Exception:
                                        pass

                                if in_cooldown:
                                    log_to_terminal(f"{symbol} SKIPPED: Cooldown active")
                                else:
                                    log_to_terminal(f"AUTO-BUY: {symbol} ({lot} shares, Risk: {risk_tier}%)", is_critical=True)
                                    success, res = broker.execute_buy(symbol, summary['close'], lot, reason=f"Terminal-Live S:{summary['conviction']:.1f}")
                                    if success:
                                        sheet_logger.log_trade(symbol, "BUY", summary['close'], lot, conviction=summary['conviction'], reason="Kinetic Ledger Auto-Buy")
                                        ts = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
                                        st.session_state.alert_history.append(f"[{ts}] BUY {symbol.split('.')[0]} x{lot} @ {format_rp(summary['close'])} | Score: {summary['conviction']:.1f}")
                        else:
                            warn_msg = safety_warnings[0] if safety_warnings else (sector_warn[0] if sector_warn else 'Unknown')
                            log_to_terminal(f"SIGNAL IGNORED: {warn_msg}")

        elif df is not None:
            log_to_terminal(f"{symbol}: Insufficient data ({len(df)} rows < 60)")

        st.session_state.stock_idx = (idx + 1) % len(stocks)
        time.sleep(1)
        st.rerun()

    except Exception as e:
        log_to_terminal(f"Auto-pilot error: {e}", is_critical=True)
        st.session_state.auto_pilot = False
        st.error(f"Auto-pilot stopped due to error: {e}. Toggle auto-pilot to restart.")
