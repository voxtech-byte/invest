import os
import json
from datetime import datetime
from typing import Any, List, Dict
from supabase import create_client, Client
from logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    """
    Sovereign Data Layer: Supabase (Cloud) primary with Local JSON mirror.
    Ensures state persists across ephemeral GHA runs.
    """
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.client: Client | None = None
        self.use_cloud = False
        
        if self.url and self.key and "YOUR_SUPABASE" not in self.url:
            try:
                self.client = create_client(self.url, self.key)
                self.use_cloud = True
                logger.info("✅ SOVEREIGN CLOUD: Supabase connected (Primary Store).")
            except Exception as e:
                logger.error(f"❌ SOVEREIGN CLOUD: Connection failed: {e}. Falling back to Local JSON.")
        else:
            logger.info("⚠️ SOVEREIGN CLOUD: Credentials missing. Operating in LOCAL mode.")

    # ── POSITIONS ──────────────────────────────────────────────
    
    def get_active_positions(self) -> Dict[str, Any]:
        positions = {}
        
        # 1. Try Cloud Primary
        if self.use_cloud:
            try:
                res = self.client.table("active_positions").select("*").execute()
                positions = {row['symbol']: row['data'] for row in res.data}
                if positions:
                    # Sync to local mirror
                    with open("active_positions.json", "w") as f:
                        json.dump(positions, f, indent=4)
                    return positions
            except Exception as e:
                logger.error(f"Supabase read error: {e}")
        
        # 2. Fallback Local
        try:
            if os.path.exists("active_positions.json"):
                with open("active_positions.json", "r") as f:
                    positions = json.load(f)
        except Exception as e:
            logger.error(f"Local state read error: {e}")
            
        return positions

    def save_position(self, symbol: str, data: Dict[str, Any]):
        # 1. Save to Cloud
        if self.use_cloud:
            try:
                self.client.table("active_positions").upsert({
                    "symbol": symbol,
                    "data": data,
                    "updated_at": datetime.utcnow().isoformat()
                }).execute()
            except Exception as e:
                logger.error(f"Supabase save error: {e}")
        
        # 2. Update local mirror
        current = self.get_active_positions()
        current[symbol] = data
        with open("active_positions.json", "w") as f:
            json.dump(current, f, indent=4)

    def remove_position(self, symbol: str):
        # 1. Delete from Cloud
        if self.use_cloud:
            try:
                self.client.table("active_positions").delete().eq("symbol", symbol).execute()
            except Exception as e:
                logger.error(f"Supabase delete error: {e}")
        
        # 2. Update local mirror
        current = self.get_active_positions()
        if symbol in current:
            del current[symbol]
            with open("active_positions.json", "w") as f:
                json.dump(current, f, indent=4)

    # ── TRADE HISTORY ───────────────────────────────────────────

    def log_trade(self, trade_data: Dict[str, Any]):
        # 1. Log to Cloud
        if self.use_cloud:
            try:
                # Map 'date' from code to 'trade_date' in Supabase to avoid reserved word issues
                db_data = trade_data.copy()
                if "date" in db_data:
                    db_data["trade_date"] = db_data.pop("date")
                
                self.client.table("trade_history").insert(db_data).execute()
            except Exception as e:
                logger.error(f"Supabase history error: {e}")
        
        # 2. Log to local mirror (JSONL format for trade_log.json)
        try:
            with open("trade_log.json", "a") as f:
                f.write(json.dumps(trade_data) + "\n")
        except Exception as e:
            logger.error(f"Local history log error: {e}")

    # ── SCAN RESULTS ────────────────────────────────────────────

    def save_scan_results(self, results: List[Dict[str, Any]]):
        if self.use_cloud:
            try:
                # Batch upsert
                self.client.table("scan_results").upsert(results).execute()
            except Exception as e:
                logger.error(f"Supabase scan error: {e}")
        
        # Local overwrite mirror
        try:
            with open("last_signals.json", "w") as f:
                json.dump(results, f, indent=4)
        except Exception as e:
            logger.error(f"Local scan results save error: {e}")
