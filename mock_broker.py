import json
import os
from datetime import datetime
import pytz

TIMEZONE = pytz.timezone('Asia/Jakarta')
POSITIONS_FILE = "active_positions.json"
EQUITY_FILE = "portfolio_equity.json"

class MockBroker:
    def __init__(self, initial_equity=50000000):
        self.buy_fee = 0.0015  # 0.15%
        self.sell_fee = 0.0025 # 0.25%
        self.initial_equity = initial_equity
        self.positions = self._load_positions()
        self.equity = self._load_equity()
        
    def _load_positions(self):
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
        
    def _save_positions(self):
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(self.positions, f, indent=4)
            
    def _load_equity(self):
        if os.path.exists(EQUITY_FILE):
            try:
                with open(EQUITY_FILE, 'r') as f:
                    return json.load(f).get("balance", self.initial_equity)
            except Exception:
                return self.initial_equity
        return self.initial_equity
        
    def _save_equity(self):
        with open(EQUITY_FILE, 'w') as f:
            json.dump({"balance": self.equity, "last_updated": datetime.now(TIMEZONE).isoformat()}, f, indent=4)
            
    def get_balance(self):
        return self.equity
        
    def get_open_positions(self):
        return self.positions

    def execute_buy(self, symbol, price, lot, reason=""):
        if lot <= 0:
            return False, "Invalid lot size"
            
        qty = lot
        cost = qty * price
        fee = cost * self.buy_fee
        total_cost = cost + fee
        
        if self.equity < total_cost:
            return False, f"Insufficient balance (Need {total_cost}, Have {self.equity})"
            
        self.equity -= total_cost
        
        if symbol in self.positions:
            # Average down/up
            old_qty = self.positions[symbol]['quantity']
            old_price = self.positions[symbol]['avg_price']
            new_qty = old_qty + qty
            new_price = ((old_qty * old_price) + cost) / new_qty
            self.positions[symbol]['avg_price'] = new_price
            self.positions[symbol]['quantity'] = new_qty
        else:
            self.positions[symbol] = {
                'symbol': symbol,
                'avg_price': price,
                'quantity': qty,
                'entry_date': datetime.now(TIMEZONE).isoformat(),
                'tp1_hit': False,
                'reason': reason
            }
            
        self._save_positions()
        self._save_equity()
        
        return True, {
            "action": "BUY",
            "symbol": symbol,
            "price": price,
            "qty": qty,
            "fee": fee,
            "total_cost": total_cost,
            "balance": self.equity
        }

    def execute_sell(self, symbol, price, lot=None, reason=""):
        if symbol not in self.positions:
            return False, "Position not found"
            
        pos = self.positions[symbol]
        qty_to_sell = lot if lot and lot <= pos['quantity'] else pos['quantity']
        
        revenue = qty_to_sell * price
        fee = revenue * self.sell_fee
        net_revenue = revenue - fee
        
        self.equity += net_revenue
        
        realized_pnl = net_revenue - (qty_to_sell * pos['avg_price'] * (1 + self.buy_fee))
        
        # Determine remaining
        pos['quantity'] -= qty_to_sell
        
        if pos['quantity'] <= 0:
            del self.positions[symbol]
        else:
            # Mark TP1 hit if partial sell
            if not pos.get('tp1_hit', False):
                pos['tp1_hit'] = True
                
        self._save_positions()
        self._save_equity()
        
        return True, {
            "action": "SELL",
            "symbol": symbol,
            "price": price,
            "qty": qty_to_sell,
            "fee": fee,
            "net_revenue": net_revenue,
            "realized_pnl": realized_pnl,
            "balance": self.equity,
            "reason": reason
        }
