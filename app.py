import streamlit as st
import pandas as pd
import os
import sys
import time
from dotenv import load_dotenv
load_dotenv() # Load env vars from .env file

from datetime import datetime
import pytz
import plotly.graph_objects as go
import yfinance as yf

# ── Sovereign Modules ──────────────────────────────────────
from core.utils import load_config, format_rp, draw_progress_bar, TIMEZONE
from core.indicators import calculate_indicators
from core.signals import evaluate_signals, evaluate_exit_conditions
from core.executive import (
    calculate_position_size, check_safety_gates,
    check_sector_exposure, check_liquidity,
    check_portfolio_heat, check_correlation,
    calculate_kelly_suggestion, run_scenario_analysis
)
from core.dark_pool import detect_hidden_flows
from core.monte_carlo import run_monte_carlo
from core.black_swan import detect_black_swan_event
from core.sector_rotation import analyze_sector_rotation
from core.config_validator import validate_config
from core.health_check import check_health
from data.data_fetcher import fetch_data, fetch_ihsg
from data.database import DatabaseManager
from integrations.news_aggregator import fetch_indonesia_market_news, analyze_political_keywords
from ui.terminal_style import inject_terminal_theme, get_icon
from ui.heatmap import generate_correlation_heatmap
from mock_broker import MockBroker
from google_sheets_logger import GoogleSheetsLogger

# =====================================================================
# INITIALIZATION
# =====================================================================
if 'is_demo' not in st.session_state:
    st.session_state.is_demo = "--demo" in sys.argv

st.set_page_config(
    page_title="Sovereign Quant Terminal " + ("(DEMO MODE)" if st.session_state.is_demo else "V15 PRO"), 
    page_icon="🏛️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

inject_terminal_theme()

if 'auto_pilot' not in st.session_state: st.session_state.auto_pilot = False
if 'stock_idx' not in st.session_state: st.session_state.stock_idx = 0
if 'scan_results' not in st.session_state: st.session_state.scan_results = []
if 'terminal_log' not in st.session_state: st.session_state.terminal_log = []
if 'news_data' not in st.session_state: st.session_state.news_data = []
if 'alert_history' not in st.session_state: st.session_state.alert_history = []

if st.session_state.is_demo and not st.session_state.terminal_log:
    st.session_state.terminal_log.append("<span style='color:#D29922'>🏛️ DEMO MODE ACTIVE: Using cached data & paper simulation.</span>")

config = load_config()

# ── V15: Startup Config Validation ──
_config_issues = validate_config(config)

db = DatabaseManager()
# Initialize Broker with Sovereign balance
broker = MockBroker(initial_equity=config.get('portfolio', {}).get('initial_equity', 50000000))

# Initialize Google Sheets Sync
gs_cfg = config.get('google_sheets', {})
sheet_logger = GoogleSheetsLogger(
    sheet_id=gs_cfg.get('spreadsheet_id'), 
    credentials_file=gs_cfg.get('credentials_file', 'service_account.json')
)

# =====================================================================
# UI HELPERS & CACHING
# =====================================================================
@st.cache_data(ttl=600) # Cache news for 10 minutes
def get_cached_news():
    return fetch_indonesia_market_news()

@st.cache_data(ttl=300) # Cache IHSG for 5 minutes to prevent yfinance rate limiting
def get_cached_ihsg(_config):
    return fetch_ihsg(_config)

def log_to_terminal(msg, is_critical=False):
    ts = datetime.now(TIMEZONE).strftime("%H:%M:%S")
    color = "#f85149" if is_critical else "#58a6ff"
    prefix = "🚨" if is_critical else "›"
    st.session_state.terminal_log.insert(0, f"<span style='color:{color}'>{prefix} [{ts}] {msg}</span>")
    st.session_state.terminal_log = st.session_state.terminal_log[:30]

def render_ticker(news):
    items = []
    for n in news[:8]:
        items.append(f"<span class='ticker-item'><strong>{n['source']}:</strong> {n['title']}</span>")
    ticker_html = f"<div class='ticker-wrap'><div class='ticker'>{''.join(items)}</div></div>"
    st.markdown(ticker_html, unsafe_allow_html=True)

def compile_institutional_data(selected_tickers, config, ihsg_data=None):
    """
    Kompilasi Rangkuman Data Kuantitatif Terbaru (Master Summary Table).
    Hasilnya: 1 Baris per saham dengan parameter super lengkap.
    """
    summary_list = []
    progress_bar = st.sidebar.progress(0)
    
    for i, ticker in enumerate(selected_tickers):
        with st.sidebar:
            st.write(f"Analyzing {ticker}...")
        
        df = fetch_data(ticker, config)
        if df is not None:
            df = calculate_indicators(df, config)
            # Evaluate Signal untuk mendapatkan rangkuman lengkap (Conviction, Target, SL)
            signal, summary, reason = evaluate_signals(ticker, df, config, ihsg_data=ihsg_data)
            
            if summary:
                # Ambil data tambahan dari indikator teknikal baris terakhir
                last_row = df.iloc[-1]
                summary['rsi'] = last_row.get(f"RSI_{config['indicators']['rsi_length']}", 0)
                summary['sma_50'] = last_row.get('SMA_50', 0)
                summary['sma_200'] = last_row.get(f"SMA_{config['indicators']['ma_long']}", 0)
                summary['adx'] = last_row.get('ADX_14', 0)
                summary['volume_ratio'] = last_row['Volume'] / last_row['Vol_Avg'] if last_row.get('Vol_Avg', 0) > 0 else 1.0
                summary['mc_prob_profit'] = summary.get('mc_prob_profit', 0)
                summary['mc_risk'] = summary.get('mc_risk_rating', 'N/A')
                summary['status_reason'] = reason
                
                # Cleanup keys for institutional CSV look
                clean_row = {
                    "Ticker": summary['symbol'],
                    "Price": summary['close'],
                    "Conviction": summary['conviction'],
                    "Phase": summary['wyckoff_phase'],
                    "Target_1": summary['target_1'],
                    "Stop_Loss": summary['stop_loss'],
                    "Weekly_Trend": summary.get('weekly_trend'),
                    "BEE_SmartMoney": summary['bee_label'],
                    "RSI": round(summary['rsi'], 1),
                    "Vol_Ratio": round(summary['volume_ratio'], 2),
                    "MC_Profit_Prob": f"{summary['mc_prob_profit']}%",
                    "MC_Risk": summary['mc_risk'],
                    "Market_Reason": summary['status_reason']
                }
                summary_list.append(clean_row)
                
        progress_bar.progress((i + 1) / len(selected_tickers))
    
    if not summary_list:
        return None
        
    # Buat DataFrame dari list of dicts (otomatis jadi 1 baris per saham)
    master_df = pd.DataFrame(summary_list)
    return master_df.to_csv(index=False).encode('utf-8')

# =====================================================================
# HEADER: REAL-TIME METRICS
# =====================================================================
col_brand, col_ihsg, col_equity, col_controls = st.columns([1.5, 2.5, 3, 2])

with col_brand:
    st.markdown(f"### {get_icon('zap')} SOVEREIGN <span style='color:#58a6ff'>V15</span>", unsafe_allow_html=True)
    # Market Regime Indicator
    regime_label = "NEUTRAL"
    regime_color = "#8b949e"
    if ihsg:
        vol_regime = ihsg.get('volatility_regime', 'NORMAL')
        trend = ihsg.get('trend', 'NEUTRAL')
        pct = ihsg.get('percent', 0)
        if trend == 'BULLISH' and vol_regime != 'HIGH':
            regime_label = "RISK-ON"
            regime_color = "#3FB950"
        elif trend == 'BEARISH' or vol_regime == 'HIGH':
            regime_label = "RISK-OFF"
            regime_color = "#F85149"
        else:
            regime_label = "NEUTRAL"
            regime_color = "#D29922"
    st.markdown(f"<div style='display:inline-block; font-size:0.7rem; color:{regime_color}; border:1px solid {regime_color}; padding:2px 8px; border-radius:4px; font-weight:700;'>{regime_label}</div>", unsafe_allow_html=True)

with col_ihsg:
    ihsg = get_cached_ihsg(config)  # Cached to prevent yfinance rate limiting
    from core.utils import is_market_open
    market_open = is_market_open()
    m_color = "#3FB950" if market_open else "#8b949e"
    m_label = "ACTIVE" if market_open else "CLOSED"
    
    if ihsg:
        c_class = "glow-green" if ihsg['percent'] >= 0 else "glow-red"
        st.markdown(f"""
        <div class="sovereign-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="metric-label">IHSG REGIME ({ihsg['symbol']})</div>
                <div style="font-size:0.6rem; color:{m_color}; border:1px solid {m_color}; padding:1px 4px; border-radius:3px;">{m_label}</div>
            </div>
            <div class="metric-value">{format_rp(ihsg['last_close'])} <span class="{c_class}" style="font-size:0.9rem;">({ihsg['percent']:+.2f}%)</span></div>
        </div>
        """, unsafe_allow_html=True)

with col_equity:
    # Use Database Manager + Broker for real-time equity tracking
    bal = broker.get_balance()
    positions = db.get_active_positions()
    st.markdown(f"""
    <div class="sovereign-card">
        <div class="metric-label">PORTFOLIO EXPOSURE | ACTIVE POS: {len(positions)}</div>
        <div class="metric-value glow-blue">{format_rp(bal)}</div>
    </div>
    """, unsafe_allow_html=True)

with col_controls:
    st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)
    c_left, c_right = st.columns(2)
    with c_left:
        ap_toggle = st.toggle("AUTO-PILOT", value=st.session_state.auto_pilot)
        if ap_toggle != st.session_state.auto_pilot:
            st.session_state.auto_pilot = ap_toggle
            st.rerun()
    with c_right:
        # Paper vs Live badge
        st.markdown("<div style='display:inline-block; font-size:0.65rem; color:#D29922; border:1px solid #D29922; padding:2px 8px; border-radius:4px; font-weight:700; margin-top:6px;'>📄 PAPER MODE</div>", unsafe_allow_html=True)

# =====================================================================
# MAIN LAYOUT: 70/30 ASYMMETRIC SPLIT
# =====================================================================
main_left, main_right = st.columns([7, 3])

# =====================================================================
# SIDEBAR: DATA HUB & CONFIG
# =====================================================================
with st.sidebar:
    st.markdown("### 🏛️ INSTITUTIONAL DATA HUB")
    st.markdown("Download super-complete quantitative datasets.")
    
    stock_list = config.get('stocks', [])
    selected_for_download = st.multiselect(
        "Select Tickers to Export", 
        options=stock_list,
        default=stock_list[:2] if stock_list else []
    )
    
    if st.button("🚀 GENERATE DATA HUB CSV", width='stretch'):
        if not selected_for_download:
            st.warning("Pilih minimal satu saham untuk ditarik datanya.")
        else:
            with st.spinner("Assembling quant factors..."):
                csv_data = compile_institutional_data(selected_for_download, config, ihsg_data=ihsg)
                if csv_data:
                    ts = datetime.now().strftime("%Y%m%d_%H%M")
                    st.download_button(
                        label="📥 DOWNLOAD COMPLETE DATASET",
                        data=csv_data,
                        file_name=f"sovereign_quant_export_{ts}.csv",
                        mime="text/csv",
                        width='stretch'
                    )
                    st.success("Dataset compiled successfully!")
                else:
                    st.error("Failed to compile dataset. Check logs.")
    
    st.divider()

    # ═════ V15: ONBOARDING CHECKLIST & HEALTH ═════
    st.markdown("### 🛡️ SYSTEM HEALTH")
    if st.button("🔄 Run Health Check", use_container_width=True):
        with st.spinner("Checking all connections..."):
            st.session_state.health_results = check_health(config)

    if 'health_results' in st.session_state:
        hr = st.session_state.health_results
        summary = hr.get('_summary', {})
        st.markdown(f"**{summary.get('passed', 0)}/{summary.get('total', 0)} services connected**")
        for svc in ['supabase', 'telegram', 'yfinance', 'google_sheets']:
            r = hr.get(svc, {})
            icon = '✅' if r.get('ok') else '❌'
            lat = f" ({r.get('latency_ms', 0):.0f}ms)" if r.get('ok') else ""
            st.markdown(f"{icon} **{svc.replace('_', ' ').title()}**: {r.get('message', 'N/A')}{lat}")
    else:
        st.info("Click 'Run Health Check' to test all connections.")

    # Config Warnings
    if _config_issues:
        st.divider()
        st.markdown("### ⚙️ Config Warnings")
        for issue in _config_issues[:5]:
            st.warning(issue)
        if len(_config_issues) > 5:
            st.caption(f"... and {len(_config_issues) - 5} more.")

    st.divider()

    # ═════ WATCHLIST MANAGER ═════
    st.markdown("### 📝 WATCHLIST MANAGER")
    current_stocks = config.get('stocks', [])
    st.caption(f"Currently tracking {len(current_stocks)} stocks.")

    new_ticker = st.text_input("Add Ticker (e.g. BBCA.JK)", key="add_ticker_input")
    col_add, col_remove = st.columns(2)
    with col_add:
        if st.button("➕ Add", use_container_width=True):
            ticker = new_ticker.strip().upper()
            if ticker and ticker not in current_stocks:
                current_stocks.append(ticker)
                config['stocks'] = current_stocks
                import json
                with open('config.json', 'w') as f:
                    json.dump(config, f, indent=2)
                st.success(f"Added {ticker}")
                st.rerun()
            elif ticker in current_stocks:
                st.warning(f"{ticker} already in watchlist")

    remove_ticker = st.selectbox("Remove Ticker", options=[""] + current_stocks, key="remove_ticker_select")
    with col_remove:
        if st.button("➖ Remove", use_container_width=True):
            if remove_ticker and remove_ticker in current_stocks:
                current_stocks.remove(remove_ticker)
                config['stocks'] = current_stocks
                import json
                with open('config.json', 'w') as f:
                    json.dump(config, f, indent=2)
                st.success(f"Removed {remove_ticker}")
                st.rerun()

    st.divider()

    # ═════ MANUAL OVERRIDE ═════
    st.markdown("### ⚡ MANUAL OVERRIDE")
    override_sym = st.selectbox("Select Stock", options=[""] + current_stocks, key="override_sym")

    col_fbuy, col_fsell = st.columns(2)
    with col_fbuy:
        if st.button("🚀 FORCE BUY", use_container_width=True, type="primary"):
            if override_sym:
                try:
                    df_override = fetch_data(override_sym, config)
                    if df_override is not None and not df_override.empty:
                        price = df_override['Close'].iloc[-1]
                        lot = 100  # Minimum lot
                        success, res = broker.execute_buy(
                            override_sym, price, lot,
                            reason="MANUAL FORCE BUY"
                        )
                        if success:
                            sheet_logger.log_trade(override_sym, "BUY", price, lot, reason="Manual Override")
                            st.success(f"Bought {lot} shares of {override_sym} @ {format_rp(price)}")
                            st.balloons()
                        else:
                            st.error(f"Buy failed: {res}")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Select a stock first")

    with col_fsell:
        if st.button("🚨 EMERGENCY SELL", use_container_width=True, type="secondary"):
            if override_sym:
                pos = broker.get_open_positions().get(override_sym)
                if pos:
                    try:
                        df_override = fetch_data(override_sym, config)
                        price = df_override['Close'].iloc[-1] if df_override is not None else pos['avg_price']
                        success, res = broker.execute_sell(
                            override_sym, price,
                            reason="MANUAL EMERGENCY SELL"
                        )
                        if success:
                            sheet_logger.log_trade(override_sym, "SELL", price, pos['quantity'], reason="Emergency Manual Sell")
                            st.success(f"SOLD all {override_sym} @ {format_rp(price)}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning(f"No open position for {override_sym}")
            else:
                st.warning("Select a stock first")

# --- LEFT COLUMN (70%): CHART & LOGS ---
with main_left:
    active_sym = st.session_state.get('active_symbol', 'STANDBY')
    st.markdown(f"<h4 style='margin-bottom:10px;'>{get_icon('trending-up')} LIVE ORDER FLOW: <code>{active_sym}</code></h4>", unsafe_allow_html=True)
    
    # 1. PRIMARY VISUALIZATION
    if 'current_df' in st.session_state and active_sym != 'STANDBY':
        df_display = st.session_state.current_df
        
        # Create Plotly Chart
        fig = go.Figure(data=[go.Candlestick(x=df_display.index,
                    open=df_display['Open'], high=df_display['High'],
                    low=df_display['Low'], close=df_display['Close'],
                    increasing_line_color='#3FB950', decreasing_line_color='#F85149')])
        
        fig.update_layout(
            template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=0, b=0), height=400, xaxis_rangeslider_visible=False
        )
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        
        # --- MONTE CARLO INTERACTION ---
        col_mc_btn, col_mc_res = st.columns([1, 2])
        with col_mc_btn:
             if st.button("🛡️ RUN MONTE CARLO STRESS TEST", width='stretch'):
                 with st.spinner("Simulating 1,000 market paths..."):
                     from core.monte_carlo import run_monte_carlo
                     mc_res = run_monte_carlo(df_display)
                     st.session_state.mc_results = mc_res
        
        if 'mc_results' in st.session_state:
            mc = st.session_state.mc_results
            with col_mc_res:
                st.markdown(f"""
                <div style="font-size:0.8rem; border-left: 2px solid #58a6ff; padding-left:15px;">
                    <strong>Probability of Profit:</strong> <span class="glow-blue">{mc['prob_profit']}%</span> | 
                    <strong>VAR 95 (10D):</strong> <span class="glow-red">{mc['var_pct']}%</span><br>
                    <strong>Risk Rating:</strong> {mc['risk_rating']} | <strong>Expected Avg:</strong> Rp {mc['expected_price_avg']}
                </div>
                """, unsafe_allow_html=True)
                
    else:
        st.markdown("""
        <div style="background:#010409; border: 1px solid #30363d; height:450px; display:flex; align-items:center; justify-content:center; color:#8b949e;">
            [ SELECT TARGET OR ENABLE AUTO-PILOT TO INITIATE STREAMING ]
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown(f"<h4 style='display:flex; align-items:center; gap:8px;'>{get_icon('activity')} TERMINAL LOG</h4>", unsafe_allow_html=True)
    log_content = "<div style='background:#010409; border:1px solid #30363d; padding:15px; height:180px; overflow-y:auto; font-family:\"JetBrains Mono\", monospace; font-size:0.8rem;'>" + "<br>".join(st.session_state.terminal_log) + "</div>"
    st.markdown(log_content, unsafe_allow_html=True)

    # ═════════════════════════════════════════════════════════
    # V15 PREMIUM PANELS (TABBED)
    # ═════════════════════════════════════════════════════════
    tab_eq, tab_sector, tab_risk, tab_dna, tab_alerts = st.tabs([
        "📈 Equity Curve", "🔥 Sector Heatmap", "🛡️ Risk Dashboard", "🧬 Trade DNA", "📋 Alert History"
    ])

    # ── TAB 1: EQUITY CURVE ──
    with tab_eq:
        try:
            eq_data = db.get_equity_snapshots() if hasattr(db, 'get_equity_snapshots') else []
        except Exception:
            eq_data = []
        if eq_data and len(eq_data) >= 2:
            eq_df = pd.DataFrame(eq_data)
            eq_df['date'] = pd.to_datetime(eq_df.get('snapshot_date', eq_df.get('date', '')))
            eq_df = eq_df.sort_values('date')
            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=eq_df['date'], y=eq_df['total_equity'],
                name='Portfolio', mode='lines+markers',
                line=dict(color='#58a6ff', width=2),
                marker=dict(size=4)
            ))
            initial_eq = config.get('portfolio', {}).get('initial_equity', 50_000_000)
            fig_eq.add_hline(y=initial_eq, line_dash='dash', line_color='#8b949e',
                           annotation_text=f'Initial: {format_rp(initial_eq)}')
            fig_eq.update_layout(
                template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)', height=300,
                margin=dict(l=0, r=0, t=30, b=0),
                title='Portfolio Equity Curve',
                yaxis_title='Equity (Rp)'
            )
            st.plotly_chart(fig_eq, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("Equity curve data will appear after the first automated sweep cycle saves snapshots.")

    # ── TAB 2: SECTOR HEATMAP ──
    with tab_sector:
        scan_data = st.session_state.scan_results
        if scan_data:
            sectors_map = config.get('sectors', {})
            sector_scores = {}
            for s in scan_data:
                sec = sectors_map.get(s['symbol'], 'Other')
                if sec not in sector_scores:
                    sector_scores[sec] = []
                sector_scores[sec].append(s['conviction'])
            
            hm_data = []
            for sec, scores in sector_scores.items():
                avg = sum(scores) / len(scores)
                hm_data.append({"Sector": sec, "Avg Conviction": round(avg, 1), "Stocks": len(scores)})
            
            if hm_data:
                import plotly.express as px
                hm_df = pd.DataFrame(hm_data)
                fig_hm = px.treemap(
                    hm_df, path=['Sector'], values='Stocks',
                    color='Avg Conviction', color_continuous_scale=['#F85149', '#D29922', '#3FB950'],
                    range_color=[0, 10]
                )
                fig_hm.update_layout(
                    template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)',
                    height=350, margin=dict(l=0, r=0, t=30, b=0)
                )
                fig_hm.update_traces(textinfo='label+value+text',
                                    texttemplate='%{label}<br>Score: %{color:.1f}<br>(%{value} stocks)')
                st.plotly_chart(fig_hm, use_container_width=True, config={'displayModeBar': False})
            else:
                st.info("No sector data available yet.")
        else:
            st.info("Run a scan cycle to populate the sector heatmap.")

    # ── TAB 3: RISK DASHBOARD ──
    with tab_risk:
        col_heat, col_loss, col_dd = st.columns(3)
        
        # Portfolio Heat Gauge
        with col_heat:
            total_risk = 0.0
            for sym, pos in broker.get_open_positions().items():
                qty = pos.get('quantity', 0)
                avg_p = pos.get('avg_price', 0)
                sl = pos.get('stop_loss', avg_p * 0.95)
                total_risk += qty * abs(avg_p - sl)
            heat_pct = (total_risk / broker.get_balance() * 100) if broker.get_balance() > 0 else 0
            max_heat = config.get('portfolio', {}).get('max_portfolio_heat_pct', 6.0)
            heat_color = '#F85149' if heat_pct > max_heat else '#D29922' if heat_pct > max_heat * 0.7 else '#3FB950'
            st.markdown(f"""
            <div class="sovereign-card" style="text-align:center;">
                <div class="metric-label">PORTFOLIO HEAT</div>
                <div style="font-size:2rem; color:{heat_color}; font-weight:700;">{heat_pct:.1f}%</div>
                <div style="font-size:0.65rem; color:#8b949e;">Limit: {max_heat}%</div>
            </div>""", unsafe_allow_html=True)

        # Daily Loss Meter
        with col_loss:
            daily_pnl = broker.get_daily_realized_pnl()
            pnl_color = '#3FB950' if daily_pnl >= 0 else '#F85149'
            st.markdown(f"""
            <div class="sovereign-card" style="text-align:center;">
                <div class="metric-label">DAILY P&L</div>
                <div style="font-size:2rem; color:{pnl_color}; font-weight:700;">{format_rp(daily_pnl)}</div>
                <div style="font-size:0.65rem; color:#8b949e;">Realized Today</div>
            </div>""", unsafe_allow_html=True)

        # Max Drawdown
        with col_dd:
            peak = getattr(broker, 'peak_equity', broker.initial_equity)
            current = broker.get_balance()
            dd_pct = ((peak - current) / peak * 100) if peak > 0 else 0
            max_dd = config.get('portfolio', {}).get('max_drawdown_pct', 15.0)
            dd_color = '#F85149' if dd_pct > max_dd * 0.7 else '#D29922' if dd_pct > max_dd * 0.3 else '#3FB950'
            st.markdown(f"""
            <div class="sovereign-card" style="text-align:center;">
                <div class="metric-label">MAX DRAWDOWN</div>
                <div style="font-size:2rem; color:{dd_color}; font-weight:700;">{dd_pct:.1f}%</div>
                <div style="font-size:0.65rem; color:#8b949e;">Limit: {max_dd}% | Peak: {format_rp(peak)}</div>
            </div>""", unsafe_allow_html=True)

        # Scenario Analysis
        st.markdown("#### ⚡ Scenario Analysis: IHSG Stress Test")
        shock_val = st.slider("Simulated IHSG Shock (%)", min_value=-10.0, max_value=0.0, value=-3.0, step=0.5)
        scenario = run_scenario_analysis(broker, config, ihsg_shock_pct=shock_val)
        if scenario['per_position']:
            sc_df = pd.DataFrame(scenario['per_position'])
            st.dataframe(sc_df, use_container_width=True, hide_index=True)
            loss_color = '#F85149' if scenario['pct_of_equity'] < -2 else '#D29922'
            st.markdown(f"**Estimated Total Loss:** <span style='color:{loss_color}'>{format_rp(scenario['total_estimated_loss'])} ({scenario['pct_of_equity']:+.1f}% of equity)</span>", unsafe_allow_html=True)
        else:
            st.info("No open positions to stress test.")

        # Kelly Criterion
        st.markdown("#### 🎲 Kelly Criterion Suggestion")
        kelly = calculate_kelly_suggestion(broker, 1000, 950, config)
        st.markdown(f"""
        <div class="sovereign-card" style="font-size:0.85rem;">
            <strong>Status:</strong> {kelly['label']}<br>
            <strong>Note:</strong> {kelly.get('note', 'N/A')}
        </div>""", unsafe_allow_html=True)

    # ── TAB 4: TRADE DNA ──
    with tab_dna:
        history = broker.get_trade_history()
        sells = [t for t in history if t.get('action') == 'SELL']
        if sells:
            for trade in reversed(sells[-10:]):
                pnl = trade.get('pnl', 0)
                pnl_pct = trade.get('pnl_pct', 0)
                pnl_color = '#3FB950' if pnl >= 0 else '#F85149'
                pnl_icon = '✅' if pnl >= 0 else '❌'
                st.markdown(f"""
                <div class="sovereign-card" style="margin-bottom:8px; border-left:3px solid {pnl_color};">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>{trade.get('symbol', 'N/A').split('.')[0]}</strong>
                        <span style="color:{pnl_color}; font-weight:700;">{pnl_icon} {format_rp(pnl)} ({pnl_pct:+.1f}%)</span>
                    </div>
                    <div style="font-size:0.7rem; color:#8b949e; margin-top:4px;">
                        📅 {trade.get('date', 'N/A')[:10]} | 💰 Price: {format_rp(trade.get('price', 0))} | 📦 Qty: {trade.get('quantity', 0)}
                    </div>
                    <div style="font-size:0.7rem; color:#8b949e;">
                        📝 {trade.get('reason', 'No reason recorded')}
                    </div>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("No closed trades yet. Trade DNA cards will appear after the first completed sell.")

    # ── TAB 5: ALERT HISTORY ──
    with tab_alerts:
        if st.session_state.alert_history:
            search = st.text_input("🔍 Filter alerts", placeholder="Type ticker or keyword...")
            filtered = [a for a in st.session_state.alert_history if search.lower() in a.lower()] if search else st.session_state.alert_history
            for alert in reversed(filtered[-20:]):
                st.markdown(f"<div style='font-size:0.75rem; border-bottom:1px solid #21262d; padding:4px 0; font-family:monospace;'>{alert}</div>", unsafe_allow_html=True)
        else:
            st.info("Alert history will populate as the bot sends Telegram notifications during auto-pilot.")

with main_right:
    # 1. POLITICAL RISK METER
    news = get_cached_news()
    politics = analyze_political_keywords(news)
    noise = politics['political_noise_level']
    noise_color = "#F85149" if noise > 6 else "#3FB950"
    
    st.markdown(f"""
    <div class="sovereign-card">
        <div class="metric-label">POLITICAL RISK GAUGE</div>
        <div style="font-size:1.8rem; color:{noise_color}; font-weight:700;">{politics['status']} ({noise}/10)</div>
        <div style="font-size:0.7rem; color:#8b949e; margin-top:5px;">Based on current News Sentiment analysis</div>
    </div>
    """, unsafe_allow_html=True)
    
    # ── V15: LIVE CONVICTION LEADERBOARD ──
    st.markdown(f"<h4 style='display:flex; align-items:center; gap:8px;'>{get_icon('layers')} CONVICTION LEADERBOARD</h4>", unsafe_allow_html=True)
    radar_html = "<div class='sovereign-card' style='max-height:350px; overflow-y:auto;'>"
    if not st.session_state.scan_results:
        radar_html += "<span style='color:#8b949e;'>Awaiting sweep cycle...</span>"
    else:
        for rank, s in enumerate(sorted(st.session_state.scan_results, key=lambda x: x['conviction'], reverse=True)[:10], 1):
            conv = s['conviction']
            conv_color = '#3FB950' if conv >= 7 else '#D29922' if conv >= 5 else '#8b949e'
            phase = s.get('wyckoff_phase', 'N/A')
            phase_short = phase[:15] + '...' if len(phase) > 15 else phase
            # Badges
            badges = ""
            if s.get('is_squeeze'): badges += "<span style='background:#7C3AED; color:white; padding:0 4px; border-radius:3px; font-size:0.55rem; margin-left:3px;'>SQUEEZE</span>"
            if s.get('accum_days', 0) >= 3: badges += "<span style='background:#2563EB; color:white; padding:0 4px; border-radius:3px; font-size:0.55rem; margin-left:3px;'>ACCUM</span>"
            fp = s.get('inst_footprint', 0)
            if fp >= 60: badges += f"<span style='background:#059669; color:white; padding:0 4px; border-radius:3px; font-size:0.55rem; margin-left:3px;'>FP:{fp}</span>"
            radar_html += f"""<div style="border-bottom: 1px solid #30363d; padding:6px 0;">
<div style="display:flex; justify-content:space-between; align-items:center;">
<div><span style='color:#8b949e; font-size:0.7rem;'>#{rank}</span> <strong>{s['symbol'].split('.')[0]}</strong>{badges}</div>
<span style="color:{conv_color}; font-weight:700;">{conv:.1f}</span>
</div>
<div style="font-size:0.65rem; color:#8b949e;">{phase_short} | {s.get('bee_label', 'N/A')} | RS:{s.get('rs_vs_ihsg', 0):+.1f}%</div>
</div>"""

    radar_html += "</div>"
    st.markdown(radar_html, unsafe_allow_html=True)

    # ── PORTFOLIO HEATMAP (Open Positions) ──
    open_pos = broker.get_open_positions()
    if open_pos:
        st.markdown(f"<h4 style='display:flex; align-items:center; gap:8px;'>{get_icon('shield')} PORTFOLIO HEATMAP</h4>", unsafe_allow_html=True)
        pos_html = "<div class='sovereign-card'>"
        for sym, pos in open_pos.items():
            avg_p = pos.get('avg_price', 0)
            # Try to get latest price from scan results
            latest = next((s for s in st.session_state.scan_results if s['symbol'] == sym), None)
            curr_price = latest['close'] if latest else avg_p
            unrealized_pct = ((curr_price - avg_p) / avg_p * 100) if avg_p > 0 else 0
            u_color = '#3FB950' if unrealized_pct >= 0 else '#F85149'
            bar_width = min(100, abs(unrealized_pct) * 10)
            pos_html += f"""<div style="margin-bottom:6px;">
<div style="display:flex; justify-content:space-between; font-size:0.8rem;">
<strong>{sym.split('.')[0]}</strong>
<span style="color:{u_color}; font-weight:600;">{unrealized_pct:+.1f}%</span>
</div>
<div style="background:#21262d; border-radius:3px; height:6px; width:100%;">
<div style="background:{u_color}; border-radius:3px; height:6px; width:{bar_width}%;"></div>
</div>
</div>"""
        pos_html += "</div>"
        st.markdown(pos_html, unsafe_allow_html=True)

    # 3. SOVEREIGN INTELLIGENCE NARRATIVE
    st.markdown(f"<h4 style='display:flex; align-items:center; gap:8px;'>{get_icon('shield')} SOVEREIGN INTELLIGENCE</h4>", unsafe_allow_html=True)
    if politics['sample_headlines']:
        narrative = f"Market is reacting to: **{politics['sample_headlines'][0]}**. Risk is {politics['status']}."
    else:
        narrative = "No significant macro anomalies detected in the current news cycle."
    
    st.markdown(f"""
    <div class="sovereign-card" style="font-size:0.85rem; border-left:3px solid #58a6ff;">
        {narrative}
    </div>
    """, unsafe_allow_html=True)

    # 4. CORRELATION & DIVERSIFICATION
    with st.expander("📊 INSTITUTIONAL CORRELATION MATRIX", expanded=False):
        positions = db.get_active_positions()
        if len(positions) < 2:
            st.info("Assemble at least 2 active stock positions in your portfolio to generate the Correlation Heatmap.")
        else:
            with st.spinner("Rendering Live Matrix..."):
                hist_data = {}
                for sym in list(positions.keys())[:10]: # Limit to 10 to avoid UI freeze
                    df_hist = fetch_data(sym, config)
                    if df_hist is not None:
                        hist_data[sym] = df_hist
                
                fig_hm = generate_correlation_heatmap(positions, hist_data)
                if fig_hm:
                    st.plotly_chart(fig_hm, width='stretch', config={'displayModeBar': False})
                else:
                    st.warning("Insufficient relative data to build correlation matrix.")

# ── TICKER TAPE ──────────────────────────────────────────
render_ticker(news)

# =====================================================================
# STATE MACHINE EXECUTION
# =====================================================================
if st.session_state.auto_pilot:
    try:
        stocks = config.get('stocks', [])
        exec_cfg = config.get('execution', {})
        idx = st.session_state.stock_idx

        # ═══════════════════════════════════════════════════════════
        # PHASE 0: ACTIVE EXIT MANAGEMENT
        # ═══════════════════════════════════════════════════════════
        if idx == 0:
            log_to_terminal("🔍 Phase 0: Active Position Management (Stop/Trail/TP)...")
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
                            log_to_terminal(f"🎯 TP1 HIT: {sym} — Selling {tp1_pct}%", is_critical=True)
                            success, res = broker.execute_sell(sym, current_price, lot=sell_qty, reason=f"Partial TP1: {exit_reason}")
                            if success:
                                sheet_logger.log_trade(sym, "SELL", current_price, sell_qty, reason=f"Terminal Partial TP1")
                                remaining = broker.get_open_positions().get(sym)
                                if remaining:
                                    remaining['tp1_hit'] = True
                                    broker._save_positions()

                    elif exit_type == "AUTO_TRADE_SELL":
                        log_to_terminal(f"🚩 EXIT: {sym} — {exit_reason}", is_critical=True)
                        success, res = broker.execute_sell(sym, current_price, reason=f"Exit: {exit_reason}")
                        if success:
                            sheet_logger.log_trade(sym, "SELL", current_price, pos['quantity'], reason=f"Auto-Pilot Exit ({exit_reason})")
                            ts = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
                            st.session_state.alert_history.append(f"[{ts}] 🔴 SELL {sym.split('.')[0]} @ {format_rp(current_price)} — {exit_reason}")
                            st.balloons()
                except Exception as e:
                    log_to_terminal(f"❌ Exit error {sym}: {e}", is_critical=True)

        # ═══════════════════════════════════════════════════════════
        # PHASE 1: TARGET SCANNING & EXECUTION
        # ═══════════════════════════════════════════════════════════
        symbol = stocks[idx]
        st.session_state.active_symbol = symbol

        log_to_terminal(f"Scanning target: {symbol}...")
        if 'mc_results' in st.session_state: del st.session_state.mc_results

        df = fetch_data(symbol, config)
        if df is not None and len(df) >= 60:
            df = calculate_indicators(df, config)
            st.session_state.current_df = df

            # Liquidity Filter
            last_row = df.iloc[-1]
            is_liquid, liq_reason = check_liquidity(last_row, config)
            if not is_liquid:
                log_to_terminal(f"⏭️ {symbol} skipped: {liq_reason}")
            else:
                # Anomaly Check
                anomaly = detect_hidden_flows(df, config)
                if anomaly['detected']:
                    log_to_terminal(f"DARK POOL DETECTED: {symbol}", is_critical=True)

                # Black Swan Check
                swan = detect_black_swan_event(df)
                if swan['alert']:
                    log_to_terminal(f"BLACK SWAN ALERT: {symbol}", is_critical=True)

                # Check existing position
                current_pos = broker.get_open_positions().get(symbol)

                # Signal Evaluate (with position context)
                signal, summary, reason = evaluate_signals(
                    symbol, df, config, ihsg_data=ihsg, open_position=current_pos
                )
                if summary:
                    st.session_state.scan_results = [s for s in st.session_state.scan_results if s['symbol'] != symbol]
                    st.session_state.scan_results.append(summary)
                    log_to_terminal(f"Processed {symbol}: Score {summary['conviction']}/10 | {summary.get('weekly_trend', 'N/A')}")

                    # --- ACTIVE EXECUTION LOGIC ---
                    if signal['type'] == "AUTO_TRADE_BUY" and current_pos is None:
                        is_safe, safety_warnings = check_safety_gates(broker, ihsg, config)
                        sector_warn = check_sector_exposure(symbol, broker.get_open_positions(), config)

                        if is_safe and not sector_warn:
                            lot, pos_value, risk_tier = calculate_position_size(
                                summary['close'],
                                summary['stop_loss'],
                                summary['conviction'],
                                config,
                                ihsg_data=ihsg
                            )
                            if lot > 0:
                                from datetime import timedelta
                                last_sell = next((t for t in reversed(broker.get_trade_history()) 
                                                if t['symbol'] == symbol and t['action'] == 'SELL'), None)
                                in_cooldown = False
                                if last_sell:
                                    try:
                                        last_exit_date = datetime.fromisoformat(last_sell['date'])
                                        if datetime.now(TIMEZONE) - last_exit_date < timedelta(days=3):
                                            in_cooldown = True
                                    except: pass

                                if in_cooldown:
                                    log_to_terminal(f"⏳ {symbol} SKIPPED: Cooldown active")
                                else:
                                    log_to_terminal(f"🚀 AUTO-BUY: {symbol} ({lot} shares, Risk: {risk_tier}%)", is_critical=True)
                                    success, res = broker.execute_buy(symbol, summary['close'], lot, reason=f"Terminal-Live S:{summary['conviction']:.1f}")
                                    if success:
                                        sheet_logger.log_trade(symbol, "BUY", summary['close'], lot, conviction=summary['conviction'], reason="Sovereign Terminal Auto-Buy")
                                        ts = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
                                        st.session_state.alert_history.append(f"[{ts}] 🟢 BUY {symbol.split('.')[0]} x{lot} @ {format_rp(summary['close'])} | Score: {summary['conviction']:.1f}")
                                        st.balloons()

                        else:
                            warn_msg = safety_warnings[0] if safety_warnings else (sector_warn[0] if sector_warn else 'Unknown')
                            log_to_terminal(f"⚠️ SIGNAL IGNORED: {warn_msg}")
        elif df is not None:
            log_to_terminal(f"⏭️ {symbol}: Insufficient data ({len(df)} rows < 60)")

        # Advance to next
        st.session_state.stock_idx = (idx + 1) % len(stocks)
        time.sleep(1)
        st.rerun()

    except Exception as e:
        # Race condition guard — prevent infinite rerun loop
        log_to_terminal(f"❌ Auto-pilot error: {e}", is_critical=True)
        st.session_state.auto_pilot = False
        st.error(f"Auto-pilot stopped due to error: {e}. Toggle auto-pilot to restart.")
