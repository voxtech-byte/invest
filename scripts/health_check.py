import os
import sys
import json
from datetime import datetime
import yfinance as yf

# Ensure we can import from core/integrations
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import DatabaseManager
from integrations.alerts import TelegramNotifier

FAIL_THRESHOLD = 3
COUNTER_FILE = "heartbeat_fails.json"

def get_fail_count():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, 'r') as f:
            return json.load(f).get("fails", 0)
    return 0

def set_fail_count(count):
    with open(COUNTER_FILE, 'w') as f:
        json.dump({"fails": count}, f)

def run_diagnostics():
    components = {}
    is_ok = True
    error_msg = ""
    
    # 1. Supabase Check
    try:
        db = DatabaseManager()
        if db.use_cloud:
            # Simple query ping
            db.client.table("active_positions").select("id").limit(1).execute()
            components["supabase"] = "OK"
        else:
            components["supabase"] = "SKIPPED (Local Mode)"
    except Exception as e:
        components["supabase"] = f"ERROR: {e}"
        is_ok = False
        error_msg += f"Supabase: {e}\n"

    # 2. yfinance Check
    try:
        df = yf.download("BBCA.JK", period="1d", progress=False)
        if df.empty:
            raise ValueError("Returned empty dataframe")
        components["yf"] = "OK"
    except Exception as e:
        components["yf"] = f"ERROR: {e}"
        is_ok = False
        error_msg += f"YFinance: {e}\n"

    return is_ok, components, error_msg

if __name__ == "__main__":
    db = DatabaseManager()
    admin_bot = TelegramNotifier('admin')
    
    is_ok, components, error_msg = run_diagnostics()
    
    # Save to db
    status_data = {
        "status": "OK" if is_ok else "ERROR",
        "components": components,
        "created_at": datetime.utcnow().isoformat()
    }
    db.save_heartbeat(status_data)

    if not is_ok:
        fails = get_fail_count() + 1
        set_fail_count(fails)
        
        if fails >= FAIL_THRESHOLD:
            # Escalation
            admin_bot.send(
                f"🚨 *CRITICAL HEARTBEAT FAILURE*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Consecutive fails: {fails}/{FAIL_THRESHOLD}\n"
                f"Last error: \n{error_msg}\n"
                f"Action taken: Automated log generation.\n"
                f"Status: Bot may be running degraded.\n",
                msg_type="critical"
            )
    else:
        # Reset counter on success
        if get_fail_count() > 0:
            set_fail_count(0)
            admin_bot.send("✅ System recovered. Heartbeat OK.", msg_type="info")
