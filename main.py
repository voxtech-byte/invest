import os
import asyncio
import time
from dotenv import load_dotenv
load_dotenv() # Load env vars from .env file

from datetime import datetime
from logger import get_logger

# ── Sovereign Modules ──────────────────────────────────────
from core.utils import load_config, TIMEZONE, format_rp
from core.indicators import calculate_indicators
from core.signals import evaluate_signals, evaluate_exit_conditions
from core.executive import (
    calculate_position_size, check_safety_gates,
    check_sector_exposure, check_liquidity,
    check_portfolio_heat, check_correlation
)
from core.dark_pool import detect_hidden_flows
from core.black_swan import detect_black_swan_event
from data.data_fetcher import fetch_data, fetch_ihsg
from data.database import DatabaseManager
from integrations.alerts import format_alert, format_status_report
from google_sheets_logger import GoogleSheetsLogger

logger = get_logger(__name__)

async def main():
    logger.info("🏛️ SOVEREIGN QUANT TERMINAL V14: ENGINE INITIALIZED")
    config = load_config()
    db = DatabaseManager()
    exec_cfg = config.get('execution', {})

    # Initialize Google Sheets Sync
    gs_cfg = config.get('google_sheets', {})
    sheet_logger = GoogleSheetsLogger(
        sheet_id=gs_cfg.get('spreadsheet_id'),
        credentials_file=gs_cfg.get('credentials_file', 'service_account.json')
    )

    # Initialize Broker
    from mock_broker import MockBroker
    broker = MockBroker(initial_equity=config.get('portfolio', {}).get('initial_equity', 50_000_000))

    stocks = config.get('stocks', [])
    ihsg_data = fetch_ihsg(config)

    # ═══════════════════════════════════════════════════════════
    # PHASE 0: ACTIVE EXIT MANAGEMENT
    # ═══════════════════════════════════════════════════════════
    logger.info("🔍 Phase 0: Active Position Management (Stop Loss / Trailing / Partial TP)...")
    open_positions = dict(broker.get_open_positions())  # Copy to avoid mutation during iteration

    for sym, pos in open_positions.items():
        try:
            df_exit = fetch_data(sym, config)
            if df_exit is None or df_exit.empty:
                logger.warning(f"[{sym}] No data for exit check — skipping")
                continue

            df_exit = calculate_indicators(df_exit, config)
            current_price = df_exit['Close'].iloc[-1]

            # ── Update highest_price for trailing stop ──
            if current_price > pos.get('highest_price', pos.get('avg_price', 0)):
                pos['highest_price'] = current_price
                broker._save_positions()

            # ── Evaluate exit conditions with full position context ──
            exit_type, exit_reason = evaluate_exit_conditions(
                sym, df_exit, config, position=pos, ihsg_data=ihsg_data
            )

            if exit_type == "PARTIAL_TP1":
                # ── PARTIAL PROFIT TAKING: Sell 50% at TP1 ──
                tp1_pct = exec_cfg.get('tp1_scale_out_pct', 50)
                sell_qty = int(pos['quantity'] * (tp1_pct / 100))
                sell_qty = (sell_qty // 100) * 100  # Round to lot

                if sell_qty >= 100:
                    logger.info(f"🎯 TP1 HIT: {sym} — Selling {tp1_pct}% ({sell_qty} shares)")
                    success_sell, res = broker.execute_sell(
                        sym, current_price, lot=sell_qty,
                        reason=f"Partial TP1: {exit_reason}"
                    )
                    if success_sell:
                        sheet_logger.log_trade(
                            sym, "SELL", current_price, sell_qty,
                            reason=f"GHA Partial TP1 ({exit_reason})"
                        )
                        # Mark TP1 as hit — trailing stop now active at break-even
                        remaining = broker.get_open_positions().get(sym)
                        if remaining:
                            remaining['tp1_hit'] = True
                            broker._save_positions()
                        logger.info(f"[{sym}] TP1 sold. Remaining position trailing at break-even.")
                else:
                    logger.info(f"[{sym}] TP1 hit but position too small for partial sell ({pos['quantity']} shares)")

            elif exit_type == "AUTO_TRADE_SELL":
                # ── FULL EXIT ──
                logger.warning(f"🚩 EXIT SIGNAL: {sym} — {exit_reason}")
                success_sell, res = broker.execute_sell(
                    sym, current_price,
                    reason=f"Signal-Based Exit: {exit_reason}"
                )
                if success_sell:
                    sheet_logger.log_trade(
                        sym, "SELL", current_price, pos['quantity'],
                        reason=f"GHA Auto-Exit ({exit_reason})"
                    )
                    db.remove_position(sym)

        except Exception as e:
            logger.error(f"[{sym}] Exit evaluation error: {e}")
            continue

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: TARGET SCANNING & EXECUTION
    # ═══════════════════════════════════════════════════════════
    logger.info("📡 Phase 1: Scanning watchlist for entry signals...")
    all_status = []
    for symbol in stocks:
        try:
            logger.info(f"Analyzing {symbol}...")
            df = fetch_data(symbol, config)

            if df is None or df.empty:
                logger.warning(f"[{symbol}] No data available — skipping")
                continue

            # ── Data Quality Check: Minimum 60 rows ──
            if len(df) < 60:
                logger.warning(f"[{symbol}] Insufficient data ({len(df)} rows < 60 minimum)")
                continue

            df = calculate_indicators(df, config)
            last_row = df.iloc[-1]

            # ── Liquidity Filter ──
            is_liquid, liq_reason = check_liquidity(last_row, config)
            if not is_liquid:
                logger.info(f"[{symbol}] Skipped: {liq_reason}")
                continue

            # Anomaly Checks
            detect_hidden_flows(df, config)
            detect_black_swan_event(df)

            # ── Check if we already hold this stock (pass position for exit eval) ──
            current_pos = broker.get_open_positions().get(symbol)

            # Signal Evaluation
            signal, summary, reason = evaluate_signals(
                symbol, df, config,
                ihsg_data=ihsg_data,
                open_position=current_pos
            )

            if summary:
                all_status.append(summary)

                # ── BUY Execution Logic ──
                if signal['type'] == "AUTO_TRADE_BUY" and current_pos is None:
                    is_safe, safety_warnings = check_safety_gates(broker, ihsg_data, config)
                    sector_warn = check_sector_exposure(symbol, broker.get_open_positions(), config)

                    if is_safe and not sector_warn:
                        lot, pos_value, risk_tier = calculate_position_size(
                            summary['close'],
                            summary['stop_loss'],
                            summary['conviction'],
                            config,
                            ihsg_data=ihsg_data
                        )
                        if lot > 0:
                            # ── Portfolio Heat Check ──
                            risk_amount = lot * abs(summary['close'] - summary['stop_loss'])
                            heat_ok, heat_pct, heat_msg = check_portfolio_heat(broker, risk_amount, config)
                            if not heat_ok:
                                logger.info(f"🌡️ {symbol} BLOCKED: {heat_msg}")
                                continue

                            # ── Correlation Check ──
                            corr_warnings = check_correlation(
                                symbol, df, broker.get_open_positions(), config,
                                fetch_data_fn=fetch_data
                            )
                            if corr_warnings:
                                logger.info(f"🔗 {symbol} CORRELATION WARNING: {corr_warnings[0]}")
                                # Don't block, but log warning

                            logger.info(f"🚀 AUTO-BUY: {symbol} ({lot} shares, Risk: {risk_tier}%, Heat: {heat_pct:.1f}%)")
                            success_buy, res = broker.execute_buy(
                                symbol, summary['close'], lot,
                                reason=f"GHA-Auto S:{summary['conviction']:.1f} W:{summary.get('weekly_trend', 'N/A')}"
                            )
                            if success_buy:
                                sheet_logger.log_trade(
                                    symbol, "BUY", summary['close'], lot,
                                    conviction=summary['conviction'],
                                    reason=f"Sovereign GHA Auto-Buy (Wyckoff: {summary['wyckoff_phase']})"
                                )
                                db.save_position(symbol, broker.get_open_positions().get(symbol, {}))
                        else:
                            logger.info(f"[{symbol}] Signal valid but lot=0 after sizing")
                    else:
                        warn_msg = safety_warnings[0] if safety_warnings else (sector_warn[0] if sector_warn else 'Unknown')
                        logger.info(f"⚠️ {symbol} SIGNAL IGNORED: {warn_msg}")

        except Exception as e:
            logger.error(f"[{symbol}] Scan error: {e}")
            continue

        # Cooldown protection
        time.sleep(1)

    # Save results to DB
    db.save_scan_results(all_status)
    logger.info(f"✅ Sweep complete. {len(all_status)} stocks analyzed. Data synced.")

if __name__ == "__main__":
    asyncio.run(main())
