"""
Sovereign Quant V15 — Position Reconciliation Module

Ensures consistency between MockBroker (local JSON) and Database (Supabase).
Detects and resolves sync issues automatically.
"""

import json
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from logger import get_logger

logger = get_logger(__name__)


class PositionReconciler:
    """
    Reconciles positions between multiple storage backends:
    - Local JSON (MockBroker)
    - Cloud Database (Supabase)
    """
    
    def __init__(self, broker, database):
        self.broker = broker
        self.db = database
    
    def reconcile_positions(self) -> Dict[str, Any]:
        """
        Perform full position reconciliation.
        
        Returns:
            Dict with sync status and any issues found
        """
        # Get positions from both sources
        broker_positions = self.broker.get_open_positions()
        db_positions = self.db.get_active_positions()
        
        issues = []
        fixes_applied = []
        
        # Check 1: Positions in broker but not in DB
        for symbol, pos in broker_positions.items():
            if symbol not in db_positions:
                issues.append(f"Position {symbol} exists in broker but not in database")
                # Auto-fix: sync to DB
                try:
                    self.db.save_position(symbol, pos)
                    fixes_applied.append(f"Synced {symbol} to database")
                except Exception as e:
                    issues.append(f"Failed to sync {symbol} to DB: {e}")
        
        # Check 2: Positions in DB but not in broker (orphaned)
        for symbol, pos in db_positions.items():
            if symbol not in broker_positions:
                issues.append(f"Position {symbol} exists in database but not in broker (orphaned)")
                # Auto-fix: remove from DB
                try:
                    self.db.remove_position(symbol)
                    fixes_applied.append(f"Removed orphaned {symbol} from database")
                except Exception as e:
                    issues.append(f"Failed to remove orphaned {symbol}: {e}")
        
        # Check 3: Position mismatch (same symbol, different quantities/prices)
        for symbol in set(broker_positions.keys()) & set(db_positions.keys()):
            broker_pos = broker_positions[symbol]
            db_pos = db_positions[symbol]
            
            mismatches = []
            
            # Check quantity
            if broker_pos.get('quantity') != db_pos.get('quantity'):
                mismatches.append(f"qty: {broker_pos.get('quantity')} vs {db_pos.get('quantity')}")
            
            # Check avg_price
            broker_price = broker_pos.get('avg_price', 0)
            db_price = db_pos.get('avg_price', 0)
            if abs(broker_price - db_price) > 0.01:  # Allow small rounding diff
                mismatches.append(f"price: {broker_price:.0f} vs {db_price:.0f}")
            
            if mismatches:
                issue_msg = f"Position {symbol} mismatch: {', '.join(mismatches)}"
                issues.append(issue_msg)
                # Auto-fix: use broker as source of truth (more recent)
                try:
                    self.db.save_position(symbol, broker_pos)
                    fixes_applied.append(f"Updated DB {symbol} to match broker")
                except Exception as e:
                    issues.append(f"Failed to sync {symbol}: {e}")
        
        # Log results
        if issues:
            logger.warning(f"📊 Position Reconciliation: {len(issues)} issues found")
            for issue in issues:
                logger.warning(f"  - {issue}")
        
        if fixes_applied:
            logger.info(f"📊 Auto-fixes applied: {len(fixes_applied)}")
            for fix in fixes_applied:
                logger.info(f"  - {fix}")
        
        if not issues:
            logger.info("📊 Position Reconciliation: All positions in sync ✓")
        
        return {
            "status": "SYNCED" if not issues else "ISSUES_FOUND",
            "broker_count": len(broker_positions),
            "db_count": len(db_positions),
            "issues": issues,
            "fixes_applied": fixes_applied,
            "timestamp": datetime.now().isoformat()
        }
    
    def validate_position_integrity(self, symbol: str, position: Dict) -> Tuple[bool, List[str]]:
        """
        Validate position data integrity.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        required_fields = ['symbol', 'quantity', 'avg_price', 'entry_date']
        for field in required_fields:
            if field not in position:
                errors.append(f"Missing required field: {field}")
        
        # Validate quantity
        qty = position.get('quantity', 0)
        if qty <= 0:
            errors.append(f"Invalid quantity: {qty}")
        if qty % 100 != 0:
            errors.append(f"Quantity not in lot size: {qty}")
        
        # Validate price
        price = position.get('avg_price', 0)
        if price <= 0:
            errors.append(f"Invalid avg_price: {price}")
        
        # Validate entry_date format
        entry_date = position.get('entry_date', '')
        try:
            datetime.fromisoformat(entry_date)
        except (ValueError, TypeError):
            errors.append(f"Invalid entry_date format: {entry_date}")
        
        return len(errors) == 0, errors
    
    def sync_position(self, symbol: str, force_direction: Optional[str] = None) -> bool:
        """
        Force sync a specific position.
        
        Args:
            symbol: Stock symbol to sync
            force_direction: 'to_db' (broker→DB), 'from_db' (DB→broker), or None (auto)
            
        Returns:
            True if sync successful
        """
        broker_pos = self.broker.get_open_positions().get(symbol)
        db_pos = self.db.get_active_positions().get(symbol)
        
        if force_direction == 'to_db':
            if broker_pos:
                self.db.save_position(symbol, broker_pos)
                logger.info(f"Synced {symbol} broker → database")
                return True
        elif force_direction == 'from_db':
            if db_pos:
                self.broker.positions[symbol] = db_pos
                self.broker._save_positions()
                logger.info(f"Synced {symbol} database → broker")
                return True
        else:
            # Auto: use whichever is newer or broker as default
            if broker_pos:
                self.db.save_position(symbol, broker_pos)
                return True
            elif db_pos:
                self.broker.positions[symbol] = db_pos
                self.broker._save_positions()
                return True
        
        return False


def run_reconciliation(broker, database) -> Dict[str, Any]:
    """
    Convenience function to run position reconciliation.
    
    Usage:
        from core.position_sync import run_reconciliation
        result = run_reconciliation(broker, db)
    """
    reconciler = PositionReconciler(broker, database)
    return reconciler.reconcile_positions()
