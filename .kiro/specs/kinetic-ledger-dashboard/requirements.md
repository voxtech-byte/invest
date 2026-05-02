# Requirements Document

## Introduction

The Kinetic Ledger Dashboard Migration replaces the broken and placeholder UI of the Sovereign Quantitative Terminal V15 Pro with a complete, professional "Kinetic Ledger" design system. The terminal is an institutional-grade algorithmic trading dashboard for the Indonesia Stock Exchange (IDX), built on Streamlit with a Python backend. The migration covers six views: Command Center, Signals & Intelligence, Risk Management, Portfolio Analytics, Trade Journal, and Settings & Configuration. All core trading logic (signals, executive, indicators, auto-pilot state machine) is preserved without modification. The scope includes fixing critical import and syntax bugs, creating the missing `input_field` component, and implementing every view to the Kinetic Ledger design specification.

---

## Glossary

- **Dashboard**: The Streamlit application defined in `app.py` that renders all six views.
- **Design_System**: The CSS token set defined in `assets/design_system.css` and the rules in `dashboard_design/axiom_institutional/DESIGN.md`.
- **View**: One of the six named pages rendered by the Dashboard: Command Center, Signals & Intelligence, Risk Management, Portfolio Analytics, Trade Journal, Settings & Configuration.
- **Component**: A reusable Python module in the `components/` directory that emits HTML via `st.markdown`.
- **Auto_Pilot**: The state machine at the bottom of `app.py` that iterates over the watchlist, evaluates signals, and executes trades without user interaction.
- **Conviction_Score**: A numeric value in the range 0–10 produced by `core/signals.py` that represents the algorithmic confidence in a trade signal.
- **Portfolio_Heat**: The ratio of total open-position risk capital to current portfolio balance, expressed as a percentage.
- **Kinetic_Table**: The `render_kinetic_table` component in `components/data_table.py` that renders zebra-striped, borderless data tables.
- **Metric_Card**: The `render_metric_card` component in `components/metric_card.py` that renders a labeled numeric value card.
- **Status_Indicator**: The `render_status_indicator` component in `components/status_indicator.py` that renders a dot-and-label service health row.
- **Broker**: The `MockBroker` instance in `app.py` that manages paper-trading positions, balance, and trade history.
- **DB**: The `DatabaseManager` instance in `app.py` that persists equity snapshots and trade records.
- **IHSG**: The Jakarta Composite Index benchmark data fetched via `fetch_ihsg`.
- **WIB**: Western Indonesia Time (UTC+7), the timezone used for all timestamps.
- **IDX**: Indonesia Stock Exchange, the market this terminal operates on.
- **Ghost_Border**: A 1px border using `outline-variant` (#3D4947) at 20% opacity, as defined in the Design_System.
- **Tonal_Layer**: A surface elevation step achieved by using a darker or lighter `surface-container` tier rather than a drop shadow.

---

## Requirements

### Requirement 1: Critical Bug Fixes and Import Integrity

**User Story:** As a developer, I want the Dashboard to start without any Python errors, so that all six views are accessible immediately on launch.

#### Acceptance Criteria

1. THE Dashboard SHALL load without raising any `SyntaxError`, `ImportError`, or `NameError` during startup.
2. WHEN `app.py` is executed, THE Dashboard SHALL successfully import `inject_terminal_theme` from `ui.terminal_style` without raising an `ImportError`.
3. WHEN `app.py` is executed, THE Dashboard SHALL successfully import `generate_correlation_heatmap` from `ui.heatmap` without raising an `ImportError`.
4. THE Dashboard SHALL contain a `components/input_field.py` module that exports a `render_input_field` function callable without error.
5. THE Dashboard SHALL NOT contain the truncated string literal `{len(se` at line ~658 of `app.py`; the expression SHALL be syntactically complete and evaluable.
6. WHEN any View function raises an unhandled exception due to empty or missing data, THE Dashboard SHALL render a placeholder state for that View rather than crashing the entire application.

---

### Requirement 2: Design System Application

**User Story:** As a trader, I want every view to look and feel consistent with the Kinetic Ledger design language, so that I can scan data quickly without visual noise.

#### Acceptance Criteria

1. WHEN the Dashboard renders any View, THE Design_System CSS from `assets/design_system.css` SHALL be injected into the page via `inject_terminal_theme` before any View content is rendered.
2. THE Dashboard SHALL NOT render any emoji character in any UI label, page header, button label, table cell, metric card, or status indicator; emoji are permitted only in outbound Telegram alert strings inside `integrations/alerts.py`.
3. THE Dashboard SHALL NOT apply CSS `box-shadow`, `drop-shadow`, or gradient fills to any card, button, or chart element.
4. THE Dashboard SHALL NOT use the color value `#000000` (pure black) as a background or text color in any inline style or CSS class.
5. WHEN the Dashboard renders any numeric value (price, percentage, P&L, score, timestamp), THE Component SHALL apply the `font-family: var(--font-mono)` token or an equivalent monospace stack.
6. THE Dashboard SHALL apply Ghost_Border styling (1px solid `rgba(61,73,71,0.2)`) to all card and table container boundaries.
7. THE Dashboard SHALL use a border-radius of 4px (`var(--radius-lg)`) as the default for all card, button, and table container elements.
8. WHEN the Dashboard renders a chart using Plotly, THE chart SHALL use a stroke width of 1.5px for line traces, SHALL NOT include area fills under line traces, and SHALL place legends outside the chart plot area.

---

### Requirement 3: Navigation and Routing

**User Story:** As a trader, I want to switch between the six views instantly using the top navigation bar or sidebar, so that I can move between analysis contexts without page reloads.

#### Acceptance Criteria

1. THE Dashboard SHALL render a top navigation bar via `render_topnav` that displays all six View labels: Command, Portfolio, Signals, Risk, Journal, Settings.
2. WHEN a user selects a View from the sidebar navigation, THE Dashboard SHALL update `st.session_state.kl_active_view` to the corresponding view key and re-render the selected View.
3. WHILE a View is active, THE Dashboard SHALL highlight the corresponding navigation link with the primary color `#66d9cc` and a 2px bottom border.
4. THE Dashboard SHALL render a page header via `render_page_header` at the top of each View that displays the View title and the current system time in WIB format.
5. IF `st.session_state.kl_active_view` is not set or contains an unrecognized key, THEN THE Dashboard SHALL default to rendering the Command Center view.

---

### Requirement 4: Command Center View

**User Story:** As a trader, I want a single-screen command center that shows the active chart, key portfolio metrics, the execution log, and system scan status, so that I can monitor and control the auto-pilot from one place.

#### Acceptance Criteria

1. WHEN `st.session_state.current_df` is populated and `st.session_state.active_symbol` is not `'STANDBY'`, THE Command_Center SHALL render a candlestick chart using Plotly with increasing candles colored `#88d982` and decreasing candles colored `#ffb3ac`.
2. WHEN `st.session_state.current_df` is empty or `st.session_state.active_symbol` equals `'STANDBY'`, THE Command_Center SHALL render a placeholder panel with the text `SELECT TARGET OR ENABLE AUTO-PILOT TO INITIATE STREAMING` in monospace font.
3. THE Command_Center SHALL render exactly three Metric_Cards in a horizontal row displaying: Portfolio Balance (in Rupiah), Daily P&L (in Rupiah with sign prefix), and Open Positions count.
4. WHEN Daily P&L is greater than or equal to zero, THE Metric_Card for Daily P&L SHALL apply the `profit` color (`#88d982`); WHEN Daily P&L is less than zero, THE Metric_Card SHALL apply the `loss` color (`#ffb3ac`).
5. THE Command_Center SHALL render an Execution Log as a Kinetic_Table with columns `Time` and `Event`, displaying up to 15 of the most recent entries from `st.session_state.terminal_log`.
6. WHEN `st.session_state.terminal_log` is empty, THE Kinetic_Table SHALL display a single placeholder row with the text `Awaiting system activity...`.
7. THE Command_Center SHALL render a System Conviction SVG radial gauge that maps the average Conviction_Score of `st.session_state.scan_results` to a 0–100% arc, colored `#88d982` when above 65%, `#66d9cc` when 45–65%, and `#ffb3ac` when below 45%.
8. THE Command_Center SHALL render a Scan Status group via `render_status_group` showing at minimum: Alpha Engine status, Market Feed status (active when market is open, offline otherwise), and IHSG Data status when IHSG data is available.
9. THE Command_Center SHALL render an AUTO-PILOT toggle that reads from and writes to `st.session_state.auto_pilot`, triggering `st.rerun()` on state change.
10. THE Command_Center SHALL render a Re-Scan button that sets `st.session_state.stock_idx` to 0, sets `st.session_state.auto_pilot` to `True`, and calls `st.rerun()`.

---

### Requirement 5: Signals & Intelligence View

**User Story:** As a trader, I want to see ranked scan results and institutional flow indicators, so that I can identify the highest-conviction trade candidates at a glance.

#### Acceptance Criteria

1. THE Signals_View SHALL render a Kinetic_Table titled `Scan Results` with columns: Symbol, Conviction, Wyckoff Phase, SMI Score, Volume Profile; rows SHALL be sorted by Conviction_Score descending and limited to 15 entries.
2. WHEN a row's Conviction_Score is greater than 6.5, THE Kinetic_Table cell for that score SHALL apply the `profit` color class (`#88d982`).
3. WHEN a row's Conviction_Score is between 4.5 and 6.5 inclusive, THE Kinetic_Table cell SHALL apply the `neutral` color class (`#e5e2e1`).
4. WHEN a row's Conviction_Score is less than 4.5, THE Kinetic_Table cell SHALL apply the `loss` color class (`#ffb3ac`).
5. WHEN `st.session_state.scan_results` is empty, THE Kinetic_Table SHALL render a single placeholder row with `--` in all cells.
6. THE Signals_View SHALL render two Institutional Factor cards: one for Institutional Flow (showing anomaly count and Elevated/Normal status) and one for Accumulation Signals (showing count of stocks with 3 or more accumulation days).
7. THE Signals_View SHALL render a Signal Quality panel displaying the aggregate win rate as a percentage with a progress bar, colored `#88d982` when win rate is 50% or above and `#ffb3ac` when below 50%.
8. THE Signals_View SHALL render a Run Scan button that sets `st.session_state.auto_pilot` to `True`, sets `st.session_state.stock_idx` to 0, and calls `st.rerun()`.

---

### Requirement 6: Risk Management View

**User Story:** As a risk manager, I want to see the live portfolio heat gauge, a fixed stress-test scenario, and four risk status cards, so that I can assess exposure without navigating away from the dashboard.

#### Acceptance Criteria

1. THE Risk_View SHALL render a Portfolio Heat SVG radial gauge that displays the current Portfolio_Heat percentage, colored `#ffb3ac` when Portfolio_Heat exceeds 80% of the configured heat limit, `#bcc9c6` when between 50% and 80%, and `#66d9cc` when below 50%.
2. THE Risk_View SHALL render a fixed Scenario Simulator panel that applies a -5% IHSG shock via `run_scenario_analysis` and displays the estimated portfolio impact in Rupiah and as a percentage of total AUM; THE Risk_View SHALL NOT render an interactive shock slider.
3. THE Risk_View SHALL render a Kelly Criterion readout sourced from `calculate_kelly_suggestion` displaying the label text only.
4. THE Risk_View SHALL render exactly four Metric_Cards in a horizontal row: Daily Loss Limit (current daily P&L), Max Drawdown (YTD peak-to-trough percentage), Active Strategies (count of open positions), and Stress Test result (PASS or FAIL based on whether Portfolio_Heat is below the configured limit).
5. WHEN the Stress Test result is PASS, THE Metric_Card SHALL apply the `profit` color; WHEN the result is FAIL, THE Metric_Card SHALL apply the `loss` color.
6. THE Risk_View SHALL NOT render a Political Risk Gauge component.

---

### Requirement 7: Portfolio Analytics View

**User Story:** As a portfolio manager, I want to see the equity curve, drawdown tracker, active positions table, and sector exposure breakdown, so that I can evaluate overall portfolio health.

#### Acceptance Criteria

1. WHEN `db.get_equity_snapshots()` returns two or more records, THE Portfolio_View SHALL render a Plotly line chart of portfolio equity over time with a 1.5px `#66d9cc` line and a dashed reference line at the initial equity value.
2. WHEN `db.get_equity_snapshots()` returns fewer than two records, THE Portfolio_View SHALL render a placeholder message: `Equity data will appear after the first sweep cycle.`
3. THE Portfolio_View SHALL render a Drawdown Tracker card displaying the current peak-to-trough drawdown percentage in `#ffb3ac`, the configured drawdown limit, and the peak equity value.
4. THE Portfolio_View SHALL render an Active Positions Kinetic_Table with columns: Symbol, Avg Price, Current, P&L %; the P&L % cell SHALL apply `profit` color when positive and `loss` color when negative.
5. WHEN `broker.get_open_positions()` returns an empty dict, THE Active Positions Kinetic_Table SHALL render a single placeholder row with `--` in all cells.
6. THE Portfolio_View SHALL render a Sector Exposure panel that groups open positions by sector from `config['sectors']`, displays each sector as a labeled progress bar, and colors the bar `#ffb3ac` when sector allocation exceeds 40% of total open positions.
7. WHEN `broker.get_open_positions()` returns an empty dict, THE Sector Exposure panel SHALL render the message `No open positions for sector analysis.`

---

### Requirement 8: Trade Journal View

**User Story:** As a trader, I want to review all closed trades and monthly P&L performance, so that I can evaluate the strategy's historical effectiveness.

#### Acceptance Criteria

1. THE Journal_View SHALL render a Kinetic_Table titled `Closed Trades` with columns: Symbol, Type, Price, P&L %, P&L (Rp), Reason/Tags; rows SHALL be sourced from `broker.get_trade_history()` filtered to `action == 'SELL'`, limited to the 20 most recent entries in reverse chronological order.
2. WHEN a trade's `realized_pnl` is greater than or equal to zero, THE Kinetic_Table cells for P&L % and P&L (Rp) SHALL apply the `profit` color class; WHEN negative, THE cells SHALL apply the `loss` color class.
3. WHEN `broker.get_trade_history()` contains no SELL records, THE Kinetic_Table SHALL render a single placeholder row with `--` in all cells.
4. WHEN at least one SELL record exists, THE Journal_View SHALL render a Plotly bar chart of monthly net P&L grouped by calendar month; profit months SHALL use bar color `#88d982` and loss months SHALL use `#ffb3ac`; the chart SHALL have no area fills and no legend inside the plot area.
5. WHEN no SELL records exist, THE Journal_View SHALL render a placeholder card with the message `Trade history will appear after completed sell trades.`

---

### Requirement 9: Settings & Configuration View

**User Story:** As an operator, I want to manage the watchlist, view system parameters, and check service health, so that I can configure and monitor the terminal without editing files directly.

#### Acceptance Criteria

1. THE Settings_View SHALL render a Watchlist Manager panel that displays the current list of tickers from `config['stocks']`, allows adding a new ticker via a text input and button, and persists changes to `config.json` on submission.
2. WHEN a ticker is added that already exists in `config['stocks']`, THE Settings_View SHALL NOT add a duplicate entry.
3. THE Settings_View SHALL render a Parameter Display panel that shows the current values of RSI Length, ATR Period, and Conviction Threshold as read-only text; THE Settings_View SHALL NOT render interactive sliders for these parameters.
4. THE Settings_View SHALL render a Health Check panel that displays the last-known status of four services: Supabase Database, Telegram API, Market Data Feed, and Google Sheets; each service SHALL be rendered via `render_status_indicator` with the appropriate status dot.
5. WHEN `st.session_state.health_results` is not set, THE Health Check panel SHALL render all four services with `offline` status and the description `Not checked`.
6. THE Settings_View SHALL render a terminal readout panel showing system mode (DEMO or PAPER TRADING), last sync time in WIB, and system status summary.
7. THE Settings_View SHALL render an Institutional Data Hub section with a multi-select for tickers and a button to generate and download a CSV export via `compile_institutional_data`.
8. THE Settings_View SHALL NOT render real-time ping buttons for health check services; health status SHALL reflect the last-known cached result only.

---

### Requirement 10: Input Field Component

**User Story:** As a developer, I want a reusable `render_input_field` component that follows the Kinetic Ledger design, so that all text inputs across the dashboard are visually consistent.

#### Acceptance Criteria

1. THE `components/input_field.py` module SHALL export a function `render_input_field` that accepts at minimum the parameters: `label` (str), `key` (str), `placeholder` (str, optional), and `value` (str, optional).
2. WHEN `render_input_field` is called, THE Component SHALL render a Streamlit text input styled with `surface-container-highest` background and a Ghost_Border bottom edge only, consistent with the Design_System input field specification.
3. THE `render_input_field` function SHALL return the current string value of the input field.

---

### Requirement 11: Auto-Pilot State Machine Preservation

**User Story:** As a trader, I want the auto-pilot scanning and execution loop to continue operating correctly after the UI migration, so that live signal detection and trade execution are not disrupted.

#### Acceptance Criteria

1. THE Auto_Pilot state machine in `app.py` SHALL NOT have any of its logic modified, removed, or reordered as part of the UI migration.
2. WHILE `st.session_state.auto_pilot` is `True`, THE Auto_Pilot SHALL iterate through `config['stocks']` using `st.session_state.stock_idx`, evaluate exit conditions for open positions in Phase 0, evaluate entry signals in Phase 1, and call `st.rerun()` after each iteration.
3. WHEN the Auto_Pilot executes a BUY or SELL trade, THE Auto_Pilot SHALL log the event to `st.session_state.terminal_log` via `log_to_terminal` with `is_critical=True`.
4. WHEN the Auto_Pilot encounters an unhandled exception, THE Auto_Pilot SHALL set `st.session_state.auto_pilot` to `False` and render an error message via `st.error` without crashing the Dashboard.
5. THE Auto_Pilot SHALL continue to call `sheet_logger.log_trade` for every executed BUY and SELL trade after the UI migration.

---

### Requirement 12: Empty and Error State Resilience

**User Story:** As a developer, I want every view to render a valid placeholder state when data is unavailable, so that the dashboard never shows a Python traceback to the user.

#### Acceptance Criteria

1. FOR ALL Views, WHEN the underlying data source (Broker, DB, scan results, config) returns an empty collection or raises an exception, THE View SHALL render a designated placeholder element rather than propagating the exception to the Streamlit error boundary.
2. THE Dashboard SHALL wrap each View function call in the view router with exception handling such that a crash in one View does not prevent navigation to other Views.
3. WHEN a Kinetic_Table has zero data rows, THE Component SHALL render at least one placeholder row containing `--` values rather than an empty `<tbody>`.
4. WHEN a Plotly chart has insufficient data points (fewer than 2), THE Dashboard SHALL render a text placeholder instead of an empty or malformed chart.
