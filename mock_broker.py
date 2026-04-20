"""
Sovereign Quant V14 Pro — Mock Broker (Paper Trading Engine)

Simulates order execution with IDX fee structure for paper trading.
Tracks positions, equity, and trade history with full persistence.

Fee Structure (IDX Standard):
- Buy fee:  0.15%
- Sell fee:  0.25%
"""

import json
import os
import math
from datetime import datetime, date
from typing import Any

import pytz

from logger import get_logger

logger = get_logger(__name__)

TIMEZONE = pytz.timezone('Asia/Jakarta')
POSITIONS_FILE = "active_positions.json"
EQUITY_FILE = "portfolio_equity.json"
TRADE_LOG_FILE = "trade_log.json"


class MockBroker:
    """Paper trading broker that simulates IDX order execution.

    Manages portfolio state including cash balance, open positions,
    and trade history. All state is persisted to JSON files for
    cross-session continuity (e.g., GitHub Actions runs).

    Attributes:
        buy_fee: Buy transaction fee as decimal (0.0015 = 0.15%).
        sell_fee: Sell transaction fee as decimal (0.0025 = 0.25%).
        initial_equity: Starting portfolio equity in IDR.
    """

    def __init__(self, initial_equity: float = 50_000_000) -> None:
        self.buy_fee: float = 0.0015   # 0.15%
        self.sell_fee: float = 0.0025  # 0.25%
        self.initial_equity: float = initial_equity
        self.positions: dict[str, dict[str, Any]] = self._load_positions()
        self.equity: float = self._load_equity()
        self.peak_equity: float = self._load_peak_equity()
        self.trade_history: list[dict[str, Any]] = self._load_trade_history()

    # ── Persistence ────────────────────────────────────────

    def _load_positions(self) -> dict[str, dict[str, Any]]:
        """Load open positions from JSON file."""
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                logger.warning("Failed to load positions file, starting with empty positions")
                return {}
        return {}

    def _save_positions(self) -> None:
        """Persist open positions to JSON file."""
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(self.positions, f, indent=4)

    def _load_equity(self) -> float:
        """Load cash balance from JSON file."""
        if os.path.exists(EQUITY_FILE):
            try:
                with open(EQUITY_FILE, 'r') as f:
                    return json.load(f).get("balance", self.initial_equity)
            except Exception:
                logger.warning("Failed to load equity file, using initial equity")
                return self.initial_equity
        return self.initial_equity

    def _load_peak_equity(self) -> float:
        """Load peak equity for drawdown tracking."""
        if os.path.exists(EQUITY_FILE):
            try:
                with open(EQUITY_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get("peak_equity", max(data.get("balance", self.initial_equity), self.initial_equity))
            except Exception:
                pass
        return self.initial_equity

    def _save_equity(self) -> None:
        """Persist cash balance and peak equity to JSON file."""
        # Update peak equity if current balance exceeds it
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        with open(EQUITY_FILE, 'w') as f:
            json.dump({
                "balance": self.equity,
                "peak_equity": self.peak_equity,
                "last_updated": datetime.now(TIMEZONE).isoformat()
            }, f, indent=4)

    def _load_trade_history(self) -> list[dict[str, Any]]:
        """Load trade history from JSON file."""
        if os.path.exists(TRADE_LOG_FILE):
            try:
                with open(TRADE_LOG_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                logger.warning("Failed to load trade history, starting fresh")
                return []
        return []

    def _save_trade_history(self) -> None:
        """Persist trade history to JSON file."""
        with open(TRADE_LOG_FILE, 'w') as f:
            json.dump(self.trade_history, f, indent=2)

    def _record_trade(self, action: str, symbol: str, price: float,
                      qty: int, fee: float, reason: str = "",
                      realized_pnl: float = 0.0) -> None:
        """Append a trade record to the history log."""
        record = {
            "date": datetime.now(TIMEZONE).isoformat(),
            "action": action,
            "symbol": symbol,
            "price": price,
            "qty": qty,
            "fee": fee,
            "reason": reason,
            "realized_pnl": realized_pnl,
            "balance_after": self.equity,
        }
        self.trade_history.append(record)
        self._save_trade_history()

    # ── Public API ─────────────────────────────────────────

    def get_balance(self) -> float:
        """Return current cash balance in IDR."""
        return self.equity

    def get_peak_equity(self) -> float:
        """Return peak equity value (for drawdown tracking)."""
        return self.peak_equity

    def get_open_positions(self) -> dict[str, dict[str, Any]]:
        """Return dictionary of all open positions."""
        return self.positions

    def get_trade_history(self) -> list[dict[str, Any]]:
        """Return list of all executed trades."""
        return self.trade_history

    def get_daily_realized_pnl(self) -> float:
        """Sum of all realized P&L from today's trades."""
        today = date.today().isoformat()
        daily_pnl = 0.0
        for trade in self.trade_history:
            if trade["date"].startswith(today) and trade["action"] == "SELL":
                daily_pnl += trade.get("realized_pnl", 0.0)
        return daily_pnl

    # ── Performance Statistics ────────────────────────────

    def get_performance_stats(self) -> dict[str, Any]:
        """
        Calculate comprehensive trading performance metrics.
        Returns: dict with win_rate, avg_pnl_pct, max_drawdown_pct,
                 sharpe_ratio, sortino_ratio, total_trades, profit_factor
        """
        sells = [t for t in self.trade_history if t["action"] == "SELL"]

        if not sells:
            return {
                "win_rate": 0.0,
                "avg_pnl_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": None,
                "sortino_ratio": None,
                "total_trades": 0,
                "profit_factor": 0.0,
            }

        pnl_list = [t.get("realized_pnl", 0.0) for t in sells]
        total_trades = len(sells)
        winners = [p for p in pnl_list if p > 0]
        losers = [p for p in pnl_list if p < 0]

        # Win Rate
        win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else 0.0

        # Average P&L %
        avg_pnl = sum(pnl_list) / total_trades if total_trades > 0 else 0.0
        avg_pnl_pct = (avg_pnl / self.initial_equity) * 100

        # Max Drawdown (from equity curve via balance_after)
        equity_curve = [self.initial_equity]
        for t in self.trade_history:
            bal = t.get("balance_after", equity_curve[-1])
            equity_curve.append(bal)

        peak = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Sharpe Ratio (annualized, assuming daily trades)
        sharpe = None
        if len(pnl_list) >= 5:
            import numpy as np
            returns = np.array(pnl_list) / self.initial_equity
            mean_ret = np.mean(returns)
            std_ret = np.std(returns)
            if std_ret > 0:
                sharpe = round((mean_ret / std_ret) * math.sqrt(252), 2)

        # Sortino Ratio (only downside volatility)
        sortino = None
        if len(pnl_list) >= 5:
            import numpy as np
            returns = np.array(pnl_list) / self.initial_equity
            mean_ret = np.mean(returns)
            downside = returns[returns < 0]
            if len(downside) > 0:
                downside_std = np.std(downside)
                if downside_std > 0:
                    sortino = round((mean_ret / downside_std) * math.sqrt(252), 2)

        # Profit Factor
        total_win = sum(winners) if winners else 0
        total_loss = abs(sum(losers)) if losers else 0
        profit_factor = round(total_win / total_loss, 2) if total_loss > 0 else float('inf')

        return {
            "win_rate": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl_pct, 2),
            "max_drawdown_pct": round(max_dd, 1),
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "total_trades": total_trades,
            "profit_factor": profit_factor,
        }

    # ── Order Execution ───────────────────────────────────

    def execute_buy(self, symbol: str, price: float, lot: int,
                    reason: str = "",
                    stop_loss: float = 0, target_1: float = 0,
                    target_2: float = 0) -> tuple[bool, dict[str, Any] | str]:
        """Execute a mock buy order with IDX fee structure.

        Args:
            symbol: IDX ticker (e.g., 'BBCA.JK')
            price: Entry price per share in IDR
            lot: Number of shares (must be > 0, ideally multiple of 100)
            reason: Trade reason for logging
            stop_loss: ATR-based stop loss level to store in position
            target_1: First take-profit target
            target_2: Second take-profit target

        Returns:
            Tuple of (success, result_dict_or_error_string).
        """
        if lot <= 0:
            logger.error(f"[{symbol}] Invalid lot size: {lot}")
            return False, "Invalid lot size"

        qty = lot
        cost = qty * price
        fee = cost * self.buy_fee
        total_cost = cost + fee

        if self.equity < total_cost:
            logger.warning(
                f"[{symbol}] Insufficient balance — "
                f"Need {total_cost:,.0f}, Have {self.equity:,.0f}"
            )
            return False, f"Insufficient balance (Need {total_cost}, Have {self.equity})"

        self.equity -= total_cost

        if symbol in self.positions:
            # Average down/up existing position
            old_qty = self.positions[symbol]['quantity']
            old_price = self.positions[symbol]['avg_price']
            new_qty = old_qty + qty
            new_price = ((old_qty * old_price) + cost) / new_qty
            self.positions[symbol]['avg_price'] = new_price
            self.positions[symbol]['quantity'] = new_qty
            # Update risk levels
            if stop_loss > 0:
                self.positions[symbol]['stop_loss'] = stop_loss
            if target_1 > 0:
                self.positions[symbol]['target_1'] = target_1
            if target_2 > 0:
                self.positions[symbol]['target_2'] = target_2
            logger.info(
                f"[{symbol}] BUY (avg up/down) — "
                f"{qty:,} shares @ {price:,.0f}, total {new_qty:,} shares"
            )
        else:
            self.positions[symbol] = {
                'symbol': symbol,
                'avg_price': price,
                'quantity': qty,
                'entry_date': datetime.now(TIMEZONE).isoformat(),
                'tp1_hit': False,
                'highest_price': price,
                'stop_loss': stop_loss if stop_loss > 0 else price * 0.95,
                'target_1': target_1,
                'target_2': target_2,
                'reason': reason
            }
            logger.info(
                f"[{symbol}] BUY — "
                f"{qty:,} shares @ {price:,.0f} (fee: {fee:,.0f})"
            )

        self._save_positions()
        self._save_equity()
        self._record_trade("BUY", symbol, price, qty, fee, reason)

        return True, {
            "action": "BUY",
            "symbol": symbol,
            "price": price,
            "qty": qty,
            "fee": fee,
            "total_cost": total_cost,
            "balance": self.equity
        }

    def execute_sell(self, symbol: str, price: float, lot: int | None = None,
                     reason: str = "") -> tuple[bool, dict[str, Any] | str]:
        """Execute a mock sell order with IDX fee structure.

        Args:
            symbol: IDX ticker (e.g., 'BBCA.JK')
            price: Exit price per share in IDR
            lot: Number of shares to sell. If None, sells entire position.
            reason: Exit reason for audit trail

        Returns:
            Tuple of (success, result_dict_or_error_string).
        """
        if symbol not in self.positions:
            logger.error(f"[{symbol}] SELL failed — position not found")
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

        pnl_pct = (realized_pnl / (qty_to_sell * pos['avg_price'])) * 100
        logger.info(
            f"[{symbol}] SELL — {qty_to_sell:,} shares @ {price:,.0f} | "
            f"P&L: {realized_pnl:,.0f} ({pnl_pct:+.1f}%) | Reason: {reason}"
        )

        if pos['quantity'] <= 0:
            del self.positions[symbol]
        else:
            # Mark TP1 hit if partial sell
            if not pos.get('tp1_hit', False):
                pos['tp1_hit'] = True

        self._save_positions()
        self._save_equity()
        self._record_trade("SELL", symbol, price, qty_to_sell, fee, reason, realized_pnl)

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
