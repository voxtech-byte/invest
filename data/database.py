import os
import json
from datetime import datetime
from typing import Any, List, Dict
from supabase import create_client, Client
from logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    """
    Sovereign Data Layer: Supabase (Cloud) with Local JSON fallback.
    """
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.client: Client | None = None
        self.use_cloud = False
        
        if self.url and self.key and self.url != "YOUR_SUPABASE_URL":
            try:
                self.client = create_client(self.url, self.key)
                self.use_cloud = True
                logger.info("✅ Supabase Cloud connected successfully.")
            except Exception as e:
                logger.error(f"❌ Supabase connection failed: {e}. Falling back to Local.")
        else:
            logger.info("⚠️ Supabase credentials missing. Operating in LOCAL mode.")

    # ── POSITIONS ──────────────────────────────────────────────
    
    def get_active_positions(self) -> Dict[str, Any]:
        if self.use_cloud:
            try:
                res = self.client.table("active_positions").select("*").execute()
                # Convert list of rows to dict {symbol: data}
                return {row['symbol']: row['data'] for row in res.data}
            except Exception as e:
                logger.error(f"Supabase read error: {e}")
        
        # Fallback Local
        try:
            with open("active_positions.json", "r") as f:
                return json.load(f)
        except:
            return {}

    def save_position(self, symbol: str, data: Dict[str, Any]):
        if self.use_cloud:
            try:
                self.client.table("active_positions").upsert({
                    "symbol": symbol,
                    "data": data,
                    "updated_at": datetime.utcnow().isoformat()
                }).execute()
            except Exception as e:
                logger.error(f"Supabase save error: {e}")
        
        # Always update local for redundancy
        current = self.get_active_positions()
        current[symbol] = data
        with open("active_positions.json", "w") as f:
            json.dump(current, f, indent=4)

    def remove_position(self, symbol: str):
        if self.use_cloud:
            try:
                self.client.table("active_positions").delete().eq("symbol", symbol).execute()
            except Exception as e:
                logger.error(f"Supabase delete error: {e}")
        
        current = self.get_active_positions()
        if symbol in current:
            del current[symbol]
            with open("active_positions.json", "w") as f:
                json.dump(current, f, indent=4)

    # ── TRADE HISTORY ───────────────────────────────────────────

    def log_trade(self, trade_data: Dict[str, Any]):
        if self.use_cloud:
            try:
                self.client.table("trade_history").insert(trade_data).execute()
            except Exception as e:
                logger.error(f"Supabase history error: {e}")
        
        # Local Append
        with open("trade_log.json", "a") as f:
            f.write(json.dumps(trade_data) + "\n")

    # ── SCAN RESULTS ────────────────────────────────────────────

    def save_scan_results(self, results: List[Dict[str, Any]]):
        if self.use_cloud:
            try:
                # Batch upsert
                self.client.table("scan_results").upsert(results).execute()
            except Exception as e:
                logger.error(f"Supabase scan error: {e}")
        
        # Local overwrite
        with open("last_signals.json", "w") as f:
            json.dump(results, f, indent=4)
