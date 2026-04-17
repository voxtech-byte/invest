from core.utils import format_rp, draw_progress_bar

def format_alert(signal_data: dict, extra: dict = None) -> str:
    """Format signal data for Telegram or UI logs."""
    s = signal_data['data']
    conf_emoji = "💎" if signal_data['confidence'] == "HIGH" else "🔹"
    
    msg = f"{conf_emoji} *PROXIMITY SIGNAL: {s['symbol']}*\n"
    msg += f"Conviction: `{s['conviction']}/10` {draw_progress_bar(s['conviction'])}\n"
    msg += f"Phase: `{s['wyckoff_phase']}`\n"
    msg += f"Smart Money: `{s['bee_label']}`\n\n"
    msg += f"Entry: `{format_rp(s['close'])}` (±{format_rp(s['atr']*0.3)})\n"
    msg += f"Target 1: `{format_rp(s['target_1'])}` (RR: {s.get('rrr_1',0)})\n"
    msg += f"Stop Loss: `{format_rp(s['stop_loss'])}`"
    
    return msg

def format_status_report(all_stocks_status: list, ihsg_data: dict = None, broker = None) -> str:
    """Format EOD or periodic status report."""
    msg = "📊 *MARKET STATUS REPORT*\n\n"
    
    if ihsg_data:
        dir_emoji = "📈" if ihsg_data['trend'] == "BULLISH" else "📉"
        msg += f"{dir_emoji} IHSG: `{ihsg_data['last_close']:.2f}` ({ihsg_data['pct_1d']:+.2f}%)\n"
        msg += f"Regime: `{ihsg_data['regime_label']}`\n\n"
        
    if broker:
        msg += f"💰 Equity: `{format_rp(broker.get_balance())}`\n"
        msg += f"💼 Open Positions: `{len(broker.get_open_positions())}`\n\n"
        
    msg += "*Top Conviction Signals:*\n"
    sorted_stocks = sorted(all_stocks_status, key=lambda x: x['conviction'], reverse=True)[:5]
    for s in sorted_stocks:
        msg += f"• {s['symbol']}: `{s['conviction']}/10` ({s['wyckoff_phase']})\n"
        
    return msg
