"""
Sovereign Quant V15 — System Health Check

Checks connectivity to all external services.
Returns a structured status report for dashboard rendering.
"""

import os
import time
from logger import get_logger

logger = get_logger(__name__)


def check_health(config: dict) -> dict:
    """
    Run connectivity checks against all external dependencies.

    Returns:
        dict with service names as keys and status dicts as values.
        Each status: { 'ok': bool, 'latency_ms': float, 'message': str }
    """
    results = {}

    # ── 1. Supabase ──
    results['supabase'] = _check_supabase()

    # ── 2. Telegram ──
    results['telegram'] = _check_telegram()

    # ── 3. yfinance ──
    results['yfinance'] = _check_yfinance()

    # ── 4. Google Sheets ──
    results['google_sheets'] = _check_gsheets(config)

    # Summary
    all_ok = all(r['ok'] for r in results.values())
    results['_summary'] = {
        'all_ok': all_ok,
        'total': len(results) - 1,  # exclude _summary
        'passed': sum(1 for k, r in results.items() if k != '_summary' and r['ok']),
        'failed': sum(1 for k, r in results.items() if k != '_summary' and not r['ok'])
    }

    return results


def _check_supabase() -> dict:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")

    if not url or not key or "YOUR_SUPABASE" in url:
        return {'ok': False, 'latency_ms': 0, 'message': 'Credentials not configured'}

    try:
        start = time.time()
        from supabase import create_client
        client = create_client(url, key)
        # Simple ping: attempt to read from a known table
        client.table("active_positions").select("symbol").limit(1).execute()
        latency = (time.time() - start) * 1000
        return {'ok': True, 'latency_ms': round(latency, 1), 'message': 'Connected'}
    except Exception as e:
        return {'ok': False, 'latency_ms': 0, 'message': str(e)[:80]}


def _check_telegram() -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return {'ok': False, 'latency_ms': 0, 'message': 'BOT_TOKEN or CHAT_ID not set'}

    try:
        import requests
        start = time.time()
        url = f"https://api.telegram.org/bot{token}/getMe"
        resp = requests.get(url, timeout=5)
        latency = (time.time() - start) * 1000
        if resp.status_code == 200 and resp.json().get('ok'):
            bot_name = resp.json()['result'].get('username', 'Unknown')
            return {'ok': True, 'latency_ms': round(latency, 1), 'message': f'Bot: @{bot_name}'}
        else:
            return {'ok': False, 'latency_ms': round(latency, 1), 'message': f'API returned: {resp.status_code}'}
    except Exception as e:
        return {'ok': False, 'latency_ms': 0, 'message': str(e)[:80]}


def _check_yfinance() -> dict:
    try:
        import yfinance as yf
        start = time.time()
        ticker = yf.Ticker("^JKSE")
        info = ticker.history(period="1d")
        latency = (time.time() - start) * 1000
        if info is not None and not info.empty:
            return {'ok': True, 'latency_ms': round(latency, 1), 'message': f'IHSG data OK ({len(info)} rows)'}
        else:
            return {'ok': False, 'latency_ms': round(latency, 1), 'message': 'Empty response'}
    except Exception as e:
        return {'ok': False, 'latency_ms': 0, 'message': str(e)[:80]}


def _check_gsheets(config: dict) -> dict:
    gs_cfg = config.get('google_sheets', {})
    creds_file = gs_cfg.get('credentials_file', 'service_account.json')
    sheet_id = gs_cfg.get('spreadsheet_id', '')

    if not os.path.exists(creds_file):
        return {'ok': False, 'latency_ms': 0, 'message': f'{creds_file} not found'}

    if not sheet_id or 'YOUR_' in sheet_id:
        return {'ok': False, 'latency_ms': 0, 'message': 'spreadsheet_id not configured'}

    try:
        import gspread
        from google.oauth2.service_account import Credentials
        start = time.time()
        creds = Credentials.from_service_account_file(
            creds_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        latency = (time.time() - start) * 1000
        return {'ok': True, 'latency_ms': round(latency, 1), 'message': f'Sheet: {sh.title}'}
    except Exception as e:
        return {'ok': False, 'latency_ms': 0, 'message': str(e)[:80]}
