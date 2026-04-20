from core.utils import format_rp, draw_progress_bar


def format_alert(signal_data: dict, extra: dict = None) -> str:
    """
    Format signal data for Telegram with rich Wyckoff/regime context.
    Supports BUY, SELL, TP1, and warning events.
    """
    s = signal_data.get('data', signal_data)
    signal_type = signal_data.get('type', 'ALERT')
    score = s.get('conviction', 0)

    # ── Signal type header ──
    if signal_type == "AUTO_TRADE_BUY":
        header = f"🚀 *AUTO-BUY SIGNAL: {s['symbol']}*"
    elif signal_type == "AUTO_TRADE_SELL":
        header = f"🚩 *EXIT SIGNAL: {s['symbol']}*"
    elif signal_type == "PARTIAL_TP1":
        header = f"🎯 *TP1 HIT: {s['symbol']}*"
    elif signal_type == "ALERT_ONLY_BUY":
        header = f"🔔 *WATCHLIST ALERT: {s['symbol']}*"
    else:
        header = f"📊 *SIGNAL: {s['symbol']}*"

    msg = f"{header}\n"
    msg += f"{'─' * 30}\n"

    # ── Core Metrics ──
    msg += f"💰 Price: `{format_rp(s.get('close', 0))}`\n"
    msg += f"📊 Conviction: `{score}/10` {draw_progress_bar(score)}\n"
    msg += f"🔄 Wyckoff: `{s.get('wyckoff_phase', 'N/A')}`\n"

    # Wyckoff target (Cause & Effect)
    if s.get('wyckoff_target'):
        msg += f"🎯 Wyckoff Target: `{format_rp(s['wyckoff_target'])}`\n"

    msg += f"🐝 BEE Flow: `{s.get('bee_label', 'N/A')}`\n"
    msg += f"📅 Weekly Trend: `{s.get('weekly_trend', 'N/A')}`\n\n"

    # ── Risk Management ──
    msg += f"*Risk Management:*\n"
    msg += f"🛑 Stop Loss: `{format_rp(s.get('stop_loss', 0))}`\n"
    msg += f"🎯 Target 1: `{format_rp(s.get('target_1', 0))}`\n"
    msg += f"🎯 Target 2: `{format_rp(s.get('target_2', 0))}`\n"

    atr = s.get('atr', 0)
    if atr and s.get('close', 0) > 0:
        atr_pct = (atr / s['close']) * 100
        msg += f"📏 ATR: `{format_rp(atr)}` ({atr_pct:.1f}%)\n"

    # ── VWAP ──
    if s.get('vwap', 0) > 0:
        vwap_status = "Above ✅" if s['close'] > s['vwap'] else "Below ⚠️"
        msg += f"📐 VWAP: `{format_rp(s['vwap'])}` ({vwap_status})\n"

    # ── Exit reason (for sells) ──
    if signal_data.get('exit_reason'):
        msg += f"\n⚡ *Reason:* {signal_data['exit_reason']}\n"

    # ── Extra context ──
    if extra:
        if extra.get('heat_pct'):
            msg += f"\n🌡️ Portfolio Heat: `{extra['heat_pct']:.1f}%`"
        if extra.get('regime'):
            msg += f"\n🌐 IHSG Regime: `{extra['regime']}`"
        if extra.get('lot'):
            msg += f"\n📦 Position Size: `{extra['lot']:,} shares`"

    return msg


def format_status_report(all_stocks_status: list, ihsg_data: dict = None, broker=None) -> str:
    """
    Format EOD or periodic status report with full performance metrics.
    """
    msg = "📊 *SOVEREIGN QUANT — STATUS REPORT*\n"
    msg += f"{'═' * 35}\n\n"

    if ihsg_data:
        dir_emoji = "📈" if ihsg_data.get('trend') == "BULLISH" else "📉"
        msg += f"{dir_emoji} IHSG: `{ihsg_data.get('last_close', 0):,.0f}` ({ihsg_data.get('pct_1d', ihsg_data.get('percent', 0)):+.2f}%)\n"
        msg += f"🌐 Regime: `{ihsg_data.get('volatility_regime', 'N/A')}`\n"
        msg += f"📊 Trend: `{ihsg_data.get('trend', 'N/A')}`\n\n"

    if broker:
        msg += f"💰 Cash: `{format_rp(broker.get_balance())}`\n"
        pos_count = len(broker.get_open_positions())
        msg += f"💼 Open Positions: `{pos_count}`\n"

        # Performance stats
        stats = broker.get_performance_stats() if hasattr(broker, 'get_performance_stats') else {}
        if stats:
            msg += f"\n*Performance:*\n"
            msg += f"📈 Win Rate: `{stats.get('win_rate', 0):.0f}%`\n"
            msg += f"💹 Avg P&L: `{stats.get('avg_pnl_pct', 0):+.2f}%`\n"
            msg += f"📉 Max DD: `{stats.get('max_drawdown_pct', 0):.1f}%`\n"
            if stats.get('sharpe_ratio') is not None:
                msg += f"📊 Sharpe: `{stats['sharpe_ratio']:.2f}`\n"
            if stats.get('sortino_ratio') is not None:
                msg += f"📊 Sortino: `{stats['sortino_ratio']:.2f}`\n"
            msg += f"🔢 Total Trades: `{stats.get('total_trades', 0)}`\n"
        msg += "\n"

    # Top signals
    if all_stocks_status:
        msg += "*Top Conviction Signals:*\n"
        sorted_stocks = sorted(all_stocks_status, key=lambda x: x.get('conviction', 0), reverse=True)[:5]
        for s in sorted_stocks:
            trend_icon = "🟢" if s.get('weekly_trend') == "BULLISH" else ("🔴" if s.get('weekly_trend') == "BEARISH" else "⚪")
            msg += f"{trend_icon} {s['symbol']}: `{s.get('conviction', 0)}/10` ({s.get('wyckoff_phase', 'N/A')})\n"

    msg += f"\n{'═' * 35}\n"
    msg += f"🤖 _Sovereign Quant V14 Pro_"

    return msg

import os
import requests
import asyncio

async def send_telegram(message: str, photo_path: str = None) -> bool:
    """Send formatted message (and optional photo) to Telegram."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        if photo_path and os.path.exists(photo_path):
            photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(photo_path, "rb") as photo:
                files = {"photo": photo}
                res = requests.post(photo_url, data={"chat_id": chat_id, "caption": message, "parse_mode": "Markdown"}, files=files, timeout=15)
                return res.status_code == 200
        else:
            res = requests.post(url, json=payload, timeout=10)
            return res.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

