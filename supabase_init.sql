-- ══════════════════════════════════════════════════════════════
-- SOVEREIGN QUANT V14 — SUPABASE SCHEMA (REVISED & ROBUST)
-- ══════════════════════════════════════════════════════════════
-- Fixes: "date" reserved word issue and ensures columns match code.
-- ══════════════════════════════════════════════════════════════

-- OPTIONAL: Uncomment the following lines if you want to start FRESH
-- WARNING: This will delete existing data in these tables.
-- DROP TABLE IF EXISTS active_positions CASCADE;
-- DROP TABLE IF EXISTS trade_history CASCADE;
-- DROP TABLE IF EXISTS equity_snapshots CASCADE;
-- DROP TABLE IF EXISTS scan_results CASCADE;
-- DROP TABLE IF EXISTS system_logs CASCADE;


-- ══════════════════════════════════════════════════════════════
-- 1. ACTIVE POSITIONS TABLE
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS active_positions (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL UNIQUE,
    data        JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON active_positions (symbol);


-- ══════════════════════════════════════════════════════════════
-- 2. TRADE HISTORY TABLE
-- Renamed `date` to `trade_date` to avoid SQL reserved word issues.
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trade_history (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      TIMESTAMPTZ NOT NULL DEFAULT now(),
    action          TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    symbol          TEXT NOT NULL,
    price           NUMERIC(12, 2) NOT NULL,
    qty             INTEGER NOT NULL,
    fee             NUMERIC(12, 2) NOT NULL DEFAULT 0,
    reason          TEXT DEFAULT '',
    realized_pnl    NUMERIC(14, 2) DEFAULT 0,
    balance_after   NUMERIC(16, 2) DEFAULT 0,
    conviction      NUMERIC(4, 1) DEFAULT 0,
    wyckoff_phase   TEXT DEFAULT '',
    weekly_trend    TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index update to match renamed column
CREATE INDEX IF NOT EXISTS idx_trades_trade_date ON trade_history (trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trade_history (symbol);


-- ══════════════════════════════════════════════════════════════
-- 3. EQUITY SNAPSHOTS TABLE
-- Renamed `date` to `snapshot_date` for clarity.
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL UNIQUE,
    balance         NUMERIC(16, 2) NOT NULL,
    open_positions  INTEGER DEFAULT 0,
    daily_pnl       NUMERIC(14, 2) DEFAULT 0,
    total_equity    NUMERIC(16, 2) DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_equity_snapshot_date ON equity_snapshots (snapshot_date DESC);


-- ══════════════════════════════════════════════════════════════
-- 4. SCAN RESULTS TABLE
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS scan_results (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    close           NUMERIC(12, 2),
    conviction      NUMERIC(4, 1),
    wyckoff_phase   TEXT DEFAULT '',
    bee_score       NUMERIC(4, 1) DEFAULT 0,
    bee_label       TEXT DEFAULT '',
    stop_loss       NUMERIC(12, 2),
    target_1        NUMERIC(12, 2),
    target_2        NUMERIC(12, 2),
    atr             NUMERIC(10, 2),
    weekly_trend    TEXT DEFAULT '',
    vwap            NUMERIC(12, 2),
    scanned_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scan_symbol_recent ON scan_results (symbol, scanned_at DESC);


-- ══════════════════════════════════════════════════════════════
-- 5. SYSTEM LOGS TABLE
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS system_logs (
    id          BIGSERIAL PRIMARY KEY,
    level       TEXT NOT NULL DEFAULT 'INFO' CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    source      TEXT DEFAULT 'main',
    message     TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_logs_created_at ON system_logs (created_at DESC);


-- ══════════════════════════════════════════════════════════════
-- 6. FEEDBACK TABLE (NPS & User Feedback)
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS feedback (
    id          BIGSERIAL PRIMARY KEY,
    user_email  TEXT,
    nps_score   INTEGER NOT NULL CHECK (nps_score >= 0 AND nps_score <= 10),
    message     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback (created_at DESC);


-- ══════════════════════════════════════════════════════════════
-- 7. HEARTBEAT LOGS TABLE
-- ══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS heartbeat_logs (
    id          BIGSERIAL PRIMARY KEY,
    status      TEXT NOT NULL CHECK (status IN ('OK', 'ERROR', 'CRITICAL')),
    components  JSONB DEFAULT '{}',
    latency_ms  INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_created_at ON heartbeat_logs (created_at DESC);


-- ══════════════════════════════════════════════════════════════
-- RLS POLICIES (Service Role Full Access)
-- ══════════════════════════════════════════════════════════════
ALTER TABLE active_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE equity_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE heartbeat_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all" ON active_positions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON trade_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON equity_snapshots FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON scan_results FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON system_logs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON feedback FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON heartbeat_logs FOR ALL USING (true) WITH CHECK (true);
