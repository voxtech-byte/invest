# Requirements Document

## Introduction

Sovereign Quantitative Terminal V15 Pro is an institutional-grade algorithmic trading system for the Indonesia Stock Exchange (IDX). The system currently runs on a Streamlit frontend (`app.py`) that ties the auto-pilot scanning loop to the browser session. This migration replaces the Streamlit layer with a React 18 + Vite frontend and a FastAPI backend, achieving three goals:

1. **Decoupled auto-pilot** — APScheduler runs the scan loop 24/7 as a background process, independent of any browser session.
2. **Pixel-perfect UI** — The React frontend matches the HTML prototypes in `/dashboard_design/` exactly, using the Kinetic Ledger design system defined in `DESIGN.md`.
3. **Zero logic changes** — All core trading modules (`core/`, `mock_broker.py`, `data/`, `integrations/`) remain untouched.

The migration is additive: `app.py` continues to run as a fallback during the transition period and is only removed after one week of stable production operation.

---

## Glossary

- **System**: The Sovereign React Migration system as a whole (FastAPI backend + React frontend + APScheduler scanner).
- **API_Server**: The FastAPI application that exposes REST and WebSocket endpoints.
- **React_Dashboard**: The React 18 + Vite single-page application served to the browser.
- **Background_Scanner**: The APScheduler-based process that runs the conviction scoring engine on a fixed schedule.
- **Supabase**: The PostgreSQL-backed cloud database used as the primary data store.
- **MockBroker**: The existing paper-trading engine in `mock_broker.py` that manages positions, equity, and trade history.
- **Conviction_Score**: A 0–10 numeric score produced by `core/signals.py` representing the strength of a trading signal.
- **WIB**: Waktu Indonesia Barat (UTC+7), the timezone used for all scheduled operations.
- **IDX**: Indonesia Stock Exchange — the market this system trades.
- **IHSG**: Jakarta Composite Index (`^JKSE`), used as the macro benchmark.
- **Wyckoff_Phase**: A market cycle label (e.g., ACCUMULATION, MARKUP, SPRING) produced by `core/signals.py`.
- **WebSocket_Client**: A browser tab running the React_Dashboard that has an active WebSocket connection to the API_Server.
- **Scan_Result**: A JSON object containing the full output of `evaluate_signals()` for one ticker, including conviction score, Wyckoff phase, stop loss, targets, and all V15 alpha fields.
- **Design_Token**: A named color, spacing, or typography value defined in the Tailwind config extracted from the HTML prototypes (e.g., `primary` = `#66D9CC`, `tertiary` = `#FFB3AC`).
- **Ghost_Border**: A 1px border using `outline-variant` (#3D4947) at 20% opacity, as specified in DESIGN.md.
- **Tonal_Layer**: A surface elevation tier defined by background color (e.g., `surface-container` = #202020, `surface-container-high` = #2A2A2A).
- **Market_Hours**: IDX trading hours, Monday through Friday, 09:00–16:00 WIB.
- **Scan_Schedule**: The four fixed daily times at which the Background_Scanner runs: 08:30, 09:00, 13:30, and 16:00 WIB.
- **Auto_Pilot**: The operational mode in which the Background_Scanner runs on the Scan_Schedule without any browser session required.
- **Circuit_Breaker**: A safety gate in `core/executive.py` that halts new trade execution when daily loss limits, max positions, macro crash conditions, or max drawdown thresholds are breached.

---

## Requirements

### Requirement 1: FastAPI Backend — REST Endpoints

**User Story:** As a trader, I want a REST API that serves all dashboard data, so that the React frontend can display portfolio state, scan results, risk metrics, trade history, and system configuration without depending on a browser session.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `GET /api/portfolio` endpoint that returns the current MockBroker balance, all open positions with their average price and quantity, and the daily realized P&L.
2. THE API_Server SHALL expose a `GET /api/signals` endpoint that returns the most recent Scan_Result for every ticker in the watchlist, as persisted in Supabase.
3. THE API_Server SHALL expose a `GET /api/risk` endpoint that returns portfolio heat percentage, current drawdown from peak equity, daily loss limit status, and the most recent stress test scenario output from `run_scenario_analysis()`.
4. THE API_Server SHALL expose a `GET /api/journal` endpoint that returns the full trade history from MockBroker, including symbol, action, price, quantity, fee, realized P&L, and timestamp for each trade.
5. THE API_Server SHALL expose a `GET /api/settings` endpoint that returns all editable values from `config.json` and the current health status of Supabase, Telegram API, and market data feed connections.
6. THE API_Server SHALL expose a `POST /api/settings/watchlist` endpoint that accepts an `action` field (`add` or `remove`) and a `ticker` field, updates the `stocks` list in `config.json`, and returns the updated watchlist.
7. THE API_Server SHALL expose a `POST /api/settings` endpoint that accepts a JSON body of parameter key-value pairs, validates them against the config schema via `core/config_validator.py`, persists valid changes to `config.json`, and returns the updated config.
8. THE API_Server SHALL expose a `GET /api/ihsg` endpoint that returns the current IHSG index value, daily percentage change, trend label, and volatility regime from `fetch_ihsg()`.
9. THE API_Server SHALL expose a `POST /api/autopilot/start` endpoint that activates the Background_Scanner and returns the current scheduler status.
10. THE API_Server SHALL expose a `POST /api/autopilot/stop` endpoint that deactivates the Background_Scanner and returns the current scheduler status.
11. WHEN a REST endpoint receives a request, THE API_Server SHALL respond within 2000ms under normal operating conditions.
12. IF a REST endpoint encounters an unhandled exception, THEN THE API_Server SHALL return an HTTP 500 response with a JSON body containing an `error` field describing the failure.
13. THE API_Server SHALL configure CORS to allow requests from the React_Dashboard origin.
14. THE API_Server SHALL support at least 10 concurrent WebSocket connections without degraded response times.

---

### Requirement 2: FastAPI Backend — WebSocket Endpoints

**User Story:** As a trader, I want real-time push updates from the server, so that scan results and portfolio changes appear in the dashboard within seconds of occurring, without requiring a page refresh.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `WS /ws/scan` endpoint that accepts WebSocket connections from WebSocket_Clients.
2. WHEN the Background_Scanner completes processing a ticker, THE API_Server SHALL broadcast the Scan_Result for that ticker to all connected `/ws/scan` WebSocket_Clients within 5 seconds of scan completion.
3. THE API_Server SHALL expose a `WS /ws/portfolio` endpoint that accepts WebSocket connections from WebSocket_Clients.
4. WHEN MockBroker executes a buy or sell order, THE API_Server SHALL broadcast the updated portfolio state to all connected `/ws/portfolio` WebSocket_Clients within 5 seconds of order execution.
5. WHEN a WebSocket_Client disconnects, THE API_Server SHALL remove the client from the active connection pool without raising an unhandled exception.
6. WHEN a WebSocket_Client connects to `/ws/scan`, THE API_Server SHALL immediately send the most recent cached Scan_Result for each ticker so the client has a complete initial state.
7. IF no WebSocket_Clients are connected, THEN THE API_Server SHALL buffer scan results in memory and deliver them upon the next client connection.

---

### Requirement 3: Background Scanner — APScheduler Integration

**User Story:** As a trader, I want the conviction scoring engine to run automatically on a fixed schedule, so that scan results are always fresh in Supabase regardless of whether I have a browser tab open.

#### Acceptance Criteria

1. THE Background_Scanner SHALL run `evaluate_signals()` from `core/signals.py` for every ticker in the `stocks` list of `config.json` at each time in the Scan_Schedule (08:30, 09:00, 13:30, 16:00 WIB).
2. THE Background_Scanner SHALL persist each Scan_Result to Supabase before broadcasting it over the `/ws/scan` WebSocket endpoint.
3. WHILE Auto_Pilot is active, THE Background_Scanner SHALL operate independently of any browser session or WebSocket_Client connection.
4. WHEN the Background_Scanner produces a Scan_Result with a signal type of `AUTO_TRADE_BUY` or `AUTO_TRADE_SELL`, THE Background_Scanner SHALL invoke the corresponding MockBroker execution method and send a Telegram alert via `integrations/alerts.py`.
5. WHEN the Background_Scanner produces a Scan_Result with a signal type of `ALERT_ONLY_BUY`, THE Background_Scanner SHALL send a Telegram alert without executing a MockBroker order.
6. IF the Background_Scanner encounters an exception while processing a single ticker, THEN THE Background_Scanner SHALL log the error and continue processing the remaining tickers in the same scan cycle without aborting.
7. THE Background_Scanner SHALL call `check_safety_gates()` from `core/executive.py` before executing any buy order, and SHALL skip execution if the safety gates return `is_safe = False`.
8. THE Background_Scanner SHALL call `calculate_indicators()` from `core/indicators.py` on the fetched price data before passing it to `evaluate_signals()`.
9. THE Background_Scanner SHALL fetch IHSG data via `fetch_ihsg()` once per scan cycle and pass it to `evaluate_signals()` for all tickers in that cycle.
10. WHEN the Background_Scanner completes a full scan cycle, THE Background_Scanner SHALL log the cycle completion time, number of tickers processed, and number of signals generated to the Python logging system.

---

### Requirement 4: Background Scanner — Market Hours Enforcement

**User Story:** As a trader, I want the scanner to respect IDX market hours, so that it does not generate or act on signals outside of valid trading windows.

#### Acceptance Criteria

1. THE Background_Scanner SHALL only execute scheduled scan jobs on weekdays (Monday through Friday).
2. IF a scheduled scan time falls on a Saturday or Sunday, THEN THE Background_Scanner SHALL skip that job without logging an error.
3. WHILE the current WIB time is outside Market_Hours (before 09:00 or after 16:00), THE Background_Scanner SHALL not execute any MockBroker buy orders even if a valid `AUTO_TRADE_BUY` signal is produced.
4. THE Background_Scanner SHALL use the WIB timezone (UTC+7) for all schedule calculations and market hours checks.
5. WHEN the `POST /api/autopilot/start` endpoint is called, THE API_Server SHALL activate the APScheduler job and return the next scheduled run time in WIB.

---

### Requirement 5: React Dashboard — Shell and Navigation

**User Story:** As a trader, I want a persistent navigation shell that matches the Kinetic Ledger design exactly, so that I can switch between all six views without a page reload and always know which view is active.

#### Acceptance Criteria

1. THE React_Dashboard SHALL render a sidebar navigation on screens wider than 768px containing links to all six views: Command, Portfolio, Signals, Risk, Journal, and Settings.
2. THE React_Dashboard SHALL render a top navigation bar on all screen sizes containing the brand name "KINETIC LEDGER", clickable view links (on screens wider than 768px), a notifications icon, a wallet icon, and a profile avatar.
3. WHEN a navigation link is clicked, THE React_Dashboard SHALL update the active view without a full page reload.
4. THE React_Dashboard SHALL apply the active state style (teal left border, `bg-neutral-800`, `text-teal-400`) to the currently active sidebar link.
5. THE React_Dashboard SHALL apply the active state style (teal bottom border, `text-teal-400`) to the currently active top navigation link.
6. THE React_Dashboard SHALL use the Design_Token color palette: `primary` = #66D9CC, `secondary` = #88D982, `tertiary` = #FFB3AC, `background` = #131313, `surface-container` = #202020, `surface-container-high` = #2A2A2A.
7. THE React_Dashboard SHALL use Inter for all non-numeric UI text and a monospace font (JetBrains Mono or system monospace) for all prices, timestamps, ticker symbols, and numeric values.
8. THE React_Dashboard SHALL render all six views without JavaScript errors when the API returns empty arrays or null values for all data fields.

---

### Requirement 6: React Dashboard — Trading Command Center View

**User Story:** As a trader, I want the Command Center view to show my portfolio summary, a live execution log, and the system conviction gauge, so that I can assess overall system health and recent activity at a glance.

#### Acceptance Criteria

1. THE React_Dashboard SHALL render three metric cards in the Command Center view displaying: Portfolio Balance (from `GET /api/portfolio`), Daily P&L (colored `secondary` for positive, `tertiary` for negative), and Open Positions count.
2. THE React_Dashboard SHALL render an Execution Log table in the Command Center view showing the most recent trade events from MockBroker, with columns for Time and Event, using monospace font for all values.
3. THE React_Dashboard SHALL render a System Conviction SVG radial gauge in the Command Center view displaying the average Conviction_Score across all scan results as a percentage (0–100%), with the arc colored `secondary` when ≥ 65%, `primary` when 45–64%, and `tertiary` when < 45%.
4. THE React_Dashboard SHALL render a Scan Status panel in the Command Center view showing the online/offline status of the Alpha Engine, Market Feed, and IHSG connection.
5. THE React_Dashboard SHALL render an Auto-Pilot toggle in the Command Center view that calls `POST /api/autopilot/start` when enabled and `POST /api/autopilot/stop` when disabled.
6. WHEN a new scan result arrives via the `/ws/scan` WebSocket, THE React_Dashboard SHALL update the System Conviction gauge and Execution Log without a full page reload.
7. THE React_Dashboard SHALL match the layout of `dashboard_design/trading_command_center/code.html` exactly, including the 9-column left / 3-column right grid split on xl screens.

---

### Requirement 7: React Dashboard — Portfolio Analytics View

**User Story:** As a trader, I want the Portfolio Analytics view to show my equity curve, drawdown, active positions, and sector exposure, so that I can monitor portfolio health and concentration risk.

#### Acceptance Criteria

1. THE React_Dashboard SHALL render an Equity Curve chart in the Portfolio Analytics view using SVG polylines, displaying portfolio equity over time from Supabase equity snapshots, with a dashed baseline at the initial equity value.
2. THE React_Dashboard SHALL render a Max Drawdown chart in the Portfolio Analytics view using SVG, displaying the drawdown percentage over time colored with `tertiary` (#FFB3AC).
3. THE React_Dashboard SHALL render an Active Positions table in the Portfolio Analytics view with columns for Symbol, Average Price, Current Price, and P&L %, using zebra striping (`surface-container-low` for even rows, `surface-container-high` for odd rows).
4. THE React_Dashboard SHALL color P&L % values in the Active Positions table with `secondary` for positive values and `tertiary` for negative values.
5. THE React_Dashboard SHALL render a Sector Exposure treemap in the Portfolio Analytics view showing the percentage allocation per sector derived from open positions and the `sectors` map in `config.json`.
6. WHEN a portfolio update arrives via the `/ws/portfolio` WebSocket, THE React_Dashboard SHALL refresh the Active Positions table and metric values without a full page reload.
7. THE React_Dashboard SHALL match the 2×2 grid layout of `dashboard_design/portfolio_analytics/code.html` on large screens.

---

### Requirement 8: React Dashboard — Signals Intelligence View

**User Story:** As a trader, I want the Signals Intelligence view to show the latest scan results for all watchlist tickers, so that I can identify high-conviction opportunities and review institutional flow indicators.

#### Acceptance Criteria

1. THE React_Dashboard SHALL render a Scan Results table in the Signals Intelligence view with columns for Symbol, Conviction (as a percentage of the 0–10 scale), Wyckoff Phase, SMI Score, and Volume Profile bar.
2. THE React_Dashboard SHALL color Conviction values in the Scan Results table with `secondary` when ≥ 65%, `on-surface` when 45–64%, and `tertiary` when < 45%.
3. THE React_Dashboard SHALL render an Institutional Flow card and a Dark Pool Activity card below the Scan Results table, populated from the `inst_footprint` and dark pool fields in the Scan_Result.
4. THE React_Dashboard SHALL render a Signal Quality Metrics panel on the right column showing the aggregate win rate from MockBroker performance stats and a false signal tracker.
5. WHEN a new Scan_Result arrives via the `/ws/scan` WebSocket, THE React_Dashboard SHALL update the corresponding row in the Scan Results table in place without re-rendering the entire table.
6. THE React_Dashboard SHALL display the timestamp of the last scan update in the Scan Results table header using monospace font.
7. THE React_Dashboard SHALL match the layout of `dashboard_design/signals_intelligence/code.html` exactly, including the 2-column left / 1-column right split on xl screens.

---

### Requirement 9: React Dashboard — Risk Management View

**User Story:** As a trader, I want the Risk Management view to show portfolio heat, scenario simulation, and circuit breaker status, so that I can monitor and respond to aggregate risk exposure.

#### Acceptance Criteria

1. THE React_Dashboard SHALL render a Portfolio Heat SVG radial gauge in the Risk Management view displaying the current portfolio heat percentage from `GET /api/risk`, with the arc colored `tertiary` when heat ≥ 70%, `primary` when 40–69%, and `secondary` when < 40%.
2. THE React_Dashboard SHALL render a Scenario Simulator card in the Risk Management view showing the estimated portfolio impact of an IHSG shock, using data from `run_scenario_analysis()` as returned by `GET /api/risk`.
3. THE React_Dashboard SHALL render metric cards for Daily Loss Limit (with a progress bar showing current loss vs. limit), Max Drawdown (YTD peak-to-trough), Circuit Breakers (active/halted status per strategy), and Stress Test result.
4. THE React_Dashboard SHALL color the Daily Loss Limit progress bar with `tertiary` when usage exceeds 75% of the limit.
5. THE React_Dashboard SHALL display margin usage, leverage, and liquidity figures below the Portfolio Heat gauge, as shown in `dashboard_design/risk_management/code.html`.
6. THE React_Dashboard SHALL match the bento grid layout of `dashboard_design/risk_management/code.html` exactly, including the 8-column gauge / 4-column simulator split on lg screens.

---

### Requirement 10: React Dashboard — Trade Journal View

**User Story:** As a trader, I want the Trade Journal view to show all closed trades with expandable detail rows and a monthly performance chart, so that I can review execution quality and identify patterns.

#### Acceptance Criteria

1. THE React_Dashboard SHALL render a Closed Trades table in the Trade Journal view with columns for Symbol, Type (LONG/SHORT badge), Entry price, Exit price, P&L, and Reason/Tags, populated from `GET /api/journal`.
2. THE React_Dashboard SHALL color P&L values in the Closed Trades table with `secondary` for profitable trades and `tertiary` for losing trades.
3. WHEN a row in the Closed Trades table is clicked, THE React_Dashboard SHALL expand that row to show a price action overlay chart, trade notes, Risk/Reward ratio, and hold time.
4. THE React_Dashboard SHALL render a Monthly Performance bar chart below the Closed Trades table, showing net P&L per month with bars colored `secondary` for profitable months and `tertiary` for losing months.
5. THE React_Dashboard SHALL render a search input above the Closed Trades table that filters rows by ticker symbol or tag in real time as the user types.
6. THE React_Dashboard SHALL render an Export CSV button that triggers a download of the full trade history as a CSV file.
7. THE React_Dashboard SHALL match the layout of `dashboard_design/trade_journal/code.html` exactly.

---

### Requirement 11: React Dashboard — Settings & Configuration View

**User Story:** As a trader, I want the Settings view to let me manage the watchlist, tune execution parameters, and check system health, so that I can configure the system without editing JSON files directly.

#### Acceptance Criteria

1. THE React_Dashboard SHALL render a Watchlist Manager panel in the Settings view listing all tickers from `GET /api/settings`, with each ticker showing its sector tags and a hover-revealed Remove button.
2. WHEN the Remove button for a ticker is clicked, THE React_Dashboard SHALL call `POST /api/settings/watchlist` with `action: "remove"` and update the displayed list upon a successful response.
3. THE React_Dashboard SHALL render an Add Symbol input in the Watchlist Manager panel that calls `POST /api/settings/watchlist` with `action: "add"` when submitted.
4. THE React_Dashboard SHALL render a Parameter Tuning panel in the Settings view with sliders for Execution Threshold (`execution.auto_trade_threshold`), Volatility Multiplier (`execution.trailing_stop_atr_multiplier`), and Max Drawdown Limit (`portfolio.max_drawdown_pct`), bound to values from `GET /api/settings`.
5. WHEN a parameter slider value is changed and the Deploy Config button is clicked, THE React_Dashboard SHALL call `POST /api/settings` with the updated parameter values, and THE API_Server SHALL persist the changes to `config.json` and return HTTP 200 on success or HTTP 400 with a validation error message on failure.
6. THE React_Dashboard SHALL render a Health Check panel in the Settings view showing the connection status and latency for Supabase, Telegram API, and Market Data Feed, using a green dot (`secondary`) for healthy and a red dot (`tertiary`) for degraded connections.
7. THE React_Dashboard SHALL render a terminal-style log block in the Health Check panel showing the last system status message, last sync time, and average latency.
8. THE React_Dashboard SHALL match the 3-column layout of `dashboard_design/settings_configuration/code.html` exactly on lg screens.

---

### Requirement 12: Config Persistence and Scan Cycle Integration

**User Story:** As a trader, I want configuration changes made in the Settings view to take effect on the next scan cycle, so that parameter tuning has a predictable and immediate impact on system behavior.

#### Acceptance Criteria

1. WHEN `config.json` is updated via `POST /api/settings`, THE API_Server SHALL reload the configuration from disk before the next scan cycle begins.
2. THE Background_Scanner SHALL read `config.json` at the start of each scan cycle, so that any changes deployed between cycles are applied without restarting the API_Server process.
3. THE API_Server SHALL validate all incoming configuration values against the schema of the existing `config.json` before writing to disk, and SHALL return an HTTP 400 response with a descriptive error if validation fails.
4. IF `config.json` cannot be written due to a filesystem error, THEN THE API_Server SHALL return an HTTP 500 response and SHALL NOT apply the partial configuration change.

---

### Requirement 13: Data Consistency and State Integrity

**User Story:** As a trader, I want the API to always return data that is consistent with what MockBroker and the core modules actually produced, so that the dashboard never shows stale or contradictory information.

#### Acceptance Criteria

1. THE API_Server SHALL read MockBroker state (positions, equity, trade history) from the same JSON persistence files (`active_positions.json`, `portfolio_equity.json`, `trade_log.json`) that MockBroker writes to, ensuring consistency between API reads and broker state.
2. THE Background_Scanner SHALL persist each Scan_Result to Supabase before broadcasting it over the WebSocket, so that a client connecting after a scan always receives the same data as one that was connected during the scan.
3. THE API_Server SHALL return data from `GET /api/portfolio` that is consistent with the MockBroker state at the time of the request, with no more than one scan cycle of staleness.
4. FOR ALL Scan_Results stored in Supabase, the `conviction` field SHALL be a float in the range [0.0, 10.0] as produced by `evaluate_signals()` in `core/signals.py`.
5. THE API_Server SHALL not modify any data in `core/signals.py`, `core/executive.py`, `core/indicators.py`, `core/dark_pool.py`, `core/monte_carlo.py`, `core/black_swan.py`, `core/sector_rotation.py`, `core/institutional.py`, `mock_broker.py`, `data/data_fetcher.py`, `data/database.py`, `integrations/alerts.py`, `google_sheets_logger.py`, or `config.json` except through the designated `POST /api/settings` and `POST /api/settings/watchlist` endpoints.

---

### Requirement 14: Migration Strategy and Fallback

**User Story:** As a trader, I want the migration to be additive and reversible during the transition period, so that I can fall back to `app.py` immediately if the new system has a critical issue.

#### Acceptance Criteria

1. THE System SHALL be structured so that `app.py` can continue to run as a Streamlit fallback during Weeks 1 through 5 of the migration without any code changes to `app.py`.
2. THE API_Server and React_Dashboard SHALL be deployed as a separate process from `app.py`, sharing only the Supabase database and the JSON persistence files.
3. WHEN the React + FastAPI system has been running in production for 7 consecutive days without a critical incident, THE System documentation SHALL indicate that `app.py` is eligible for deletion.
4. THE Background_Scanner SHALL not run concurrently with the Streamlit auto-pilot loop; only one scanning process SHALL be active at a time to prevent duplicate trade execution.

---

### Requirement 15: Design System Fidelity

**User Story:** As a trader, I want the React frontend to match the HTML prototypes pixel-for-pixel, so that the production system delivers the same visual quality as the approved designs.

#### Acceptance Criteria

1. THE React_Dashboard SHALL implement the complete Tailwind CSS Design_Token set from the HTML prototypes, including all named colors, border radius values (`DEFAULT` = 2px, `lg` = 4px, `xl` = 8px, `full` = 12px), and font family assignments.
2. THE React_Dashboard SHALL apply Ghost_Border styling (1px, `outline-variant` at 20% opacity) to all card and table container elements, matching the HTML prototypes.
3. THE React_Dashboard SHALL implement Tonal_Layer surface hierarchy: `background` (#131313) as the page canvas, `surface-container-low` (#1B1B1C) for sidebars and de-emphasized zones, `surface-container` (#202020) for primary cards, and `surface-container-high` (#2A2A2A) for interactive elements within cards.
4. THE React_Dashboard SHALL implement hover transitions of 200ms ease-in-out on all interactive elements (navigation links, table rows, buttons) as specified in the HTML prototypes.
5. THE React_Dashboard SHALL use zebra striping for all data tables: `surface-container-low` (#1B1B1C) for even rows and `surface-container-high` (#2A2A2A) for odd rows.
6. THE React_Dashboard SHALL render all SVG gauges (System Conviction, Portfolio Heat) using inline SVG with `stroke-dasharray` and `stroke-dashoffset` animation, matching the gauge designs in the HTML prototypes.
7. THE React_Dashboard SHALL not use drop shadows, gradients, or area fills under line charts, in compliance with the Kinetic Ledger "no visual fluff" design principle from DESIGN.md.

---

### Requirement 16: Performance Baseline

**User Story:** As a trader, I want the dashboard to load quickly and update smoothly, so that I can act on signals without waiting for the UI.

#### Acceptance Criteria

1. THE React_Dashboard SHALL achieve a First Contentful Paint of under 2 seconds on a standard broadband connection when served from a local or cloud host.
2. THE React_Dashboard SHALL render all six views without visible layout shift or jank when switching between views.
3. THE API_Server SHALL serve `GET /api/signals` within 500ms when Supabase has cached results from the most recent scan cycle.
4. THE React_Dashboard SHALL handle WebSocket reconnection automatically if the connection drops, with a maximum reconnect delay of 5 seconds, without requiring a page reload.
5. THE React_Dashboard SHALL not re-render the entire Scan Results table when a single row is updated via WebSocket — only the affected row SHALL be updated in the DOM.

---

### Requirement 17: Property-Based Correctness

**User Story:** As a developer, I want automated property tests that verify the system's core invariants, so that regressions in data flow between the scanner, API, and frontend are caught before production.

#### Acceptance Criteria

1. FOR ANY Scan_Result produced by `evaluate_signals()`, WHEN it is serialized to JSON by the API_Server and deserialized by the React_Dashboard, THE `conviction` field SHALL remain a number in the range [0.0, 10.0] with no precision loss beyond 1 decimal place.
2. FOR ANY portfolio state produced by MockBroker, WHEN `GET /api/portfolio` is called, THE sum of `(position.quantity × position.avg_price)` for all open positions plus the cash balance SHALL equal the total portfolio value within a rounding tolerance of 1 IDR.
3. FOR ANY ticker added via `POST /api/settings/watchlist` with `action: "add"`, WHEN `GET /api/settings` is subsequently called, THE ticker SHALL appear exactly once in the returned watchlist regardless of how many times the add request was made.
4. FOR ANY ticker removed via `POST /api/settings/watchlist` with `action: "remove"`, WHEN `GET /api/settings` is subsequently called, THE ticker SHALL not appear in the returned watchlist.
5. FOR ANY conviction score value in [0.0, 10.0], THE React_Dashboard conviction color mapping SHALL return exactly one of `secondary` (≥ 6.5), `on-surface` (4.5–6.4), or `tertiary` (< 4.5) — the three ranges SHALL be exhaustive and mutually exclusive.
