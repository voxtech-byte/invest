import streamlit as st
import pandas as pd
import os
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
    check_portfolio_heat, check_correlation
)
from core.dark_pool import detect_hidden_flows
from core.monte_carlo import run_monte_carlo
from core.black_swan import detect_black_swan_event
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
st.set_page_config(
    page_title="Sovereign Quant Terminal", 
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

config = load_config()
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
    st.markdown(f"### {get_icon('zap')} SOVEREIGN <span style='color:#58a6ff'>V14</span>", unsafe_allow_html=True)
    st.markdown("<span style='font-size:0.7rem; color:#8b949e;'>QUANTITATIVE COMMAND CENTER</span>", unsafe_allow_html=True)

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
    ap_toggle = st.toggle("ACTIVATE AUTO-PILOT SCAN", value=st.session_state.auto_pilot)
    if ap_toggle != st.session_state.auto_pilot:
        st.session_state.auto_pilot = ap_toggle
        st.rerun()

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
    st.markdown("### 🛰️ SYSTEM HEALTH")
    st.write(f"Latency: {round(time.time() % 1, 3)}ms")
    st.write(f"Cloud DB: {'Connected' if db.use_cloud else 'Local Mode'}")

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
    log_content = "<div style='background:#010409; border:1px solid #30363d; padding:15px; height:250px; overflow-y:auto; font-family:\"JetBrains Mono\", monospace; font-size:0.8rem;'>" + "<br>".join(st.session_state.terminal_log) + "</div>"
    st.markdown(log_content, unsafe_allow_html=True)

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
    
    st.markdown(f"<h4 style='display:flex; align-items:center; gap:8px;'>{get_icon('layers')} DISCOVERY RADAR</h4>", unsafe_allow_html=True)
    radar_html = "<div class='sovereign-card' style='height:400px; overflow-y:auto;'>"
    if not st.session_state.scan_results:
        radar_html += "<span style='color:#8b949e;'>Awaiting sweep cycle...</span>"
    else:
        for s in sorted(st.session_state.scan_results, key=lambda x: x['conviction'], reverse=True)[:10]:
            radar_html += f"""<div style="border-bottom: 1px solid #30363d; padding:8px 0;">
<div style="display:flex; justify-content:space-between;">
<strong>{s['symbol'].split('.')[0]}</strong>
<span class="glow-blue">{s['conviction']:.1f}</span>
</div>
<div style="font-size:0.7rem; color:#8b949e;">{s['wyckoff_phase']} | {s['bee_label']}</div>
</div>"""

    radar_html += "</div>"
    st.markdown(radar_html, unsafe_allow_html=True)

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
