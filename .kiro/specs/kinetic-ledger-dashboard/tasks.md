# Implementation Plan: Kinetic Ledger Dashboard Migration

## Overview

Migrate the Sovereign Quantitative Terminal V15 Pro to the Kinetic Ledger design system. All changes are confined to the presentation layer: `app.py` (view functions), `components/`, and `ui/terminal_style.py`. Core trading logic is untouched. Tasks follow the priority order defined in the design: critical bug fixes first, then foundation, then views by priority, then property-based tests, then error handling.

## Tasks

- [x] 1. Fix critical syntax bug in app.py
  - In `app.py` around line 658, replace the truncated f-string `{len(se` with the complete expression `{len(sells) - wins} / {len(sells)}</div>`
  - Verify the fix by running `python -c "import ast; ast.parse(open('app.py').read()); print('OK')"` — it must exit without error
  - _Requirements: 1.1, 1.5_

- [x] 2. Create `components/input_field.py` and verify CSS injection
  - [x] 2.1 Create `components/input_field.py` with `render_input_field(label, key, placeholder, value) -> str`
    - Wrap `st.text_input()` with the given parameters and return its current value
    - Add a label `<div>` above the input using `kl-label-sm` CSS class for consistent styling
    - Export the function from `components/__init__.py` if needed
    - _Requirements: 10.1, 10.2, 10.3_
  - [ ]* 2.2 Write unit test for `render_input_field`
    - Verify the function is importable and callable without error
    - Verify it returns a string value
    - _Requirements: 10.1, 10.3_
  - [x] 2.3 Verify CSS injection works end-to-end
    - Confirm `ui/terminal_style.py` reads `assets/design_system.css` relative to `__file__` and injects via `st.markdown`
    - Confirm the fallback CSS path is exercised when the file is missing (no exception raised)
    - _Requirements: 2.1, 1.2_

- [x] 3. Extract pure helper functions into module-level scope in `app.py`
  - Add `get_conviction_color_class(score: float) -> str` at module level — returns `"profit"` when score ≥ 6.5, `"neutral"` when 4.5 ≤ score < 6.5, `"loss"` otherwise
  - Add `get_pnl_color_class(pnl: float) -> str` at module level — returns `"profit"` when pnl ≥ 0, `"loss"` otherwise
  - Add `get_sector_bar_color(pct: float) -> str` at module level — returns `"#ffb3ac"` when pct > 40, `"#66d9cc"` otherwise
  - Add `add_ticker_if_not_exists(tickers: list, ticker: str) -> list` at module level — returns the list unchanged if ticker already present, otherwise returns list with ticker appended
  - Replace all inline color logic in view functions with calls to these helpers
  - _Requirements: 5.2, 5.3, 5.4, 7.6, 9.2_

- [x] 4. Implement View 1: Trading Command Center (`view_command`)
  - [x] 4.1 Add outer `try/except` error boundary wrapping the entire function body
    - On exception, call `st.error(f"View error: {e}")` and return
    - _Requirements: 1.6, 12.1_
  - [x] 4.2 Fix empty-state placeholder panel
    - When `active_sym == 'STANDBY'` or `current_df` is absent, render a `<div>` with height 420px, centered text `SELECT TARGET OR ENABLE AUTO-PILOT TO INITIATE STREAMING` in monospace font, background `#202020`, ghost border
    - _Requirements: 4.2_
  - [x] 4.3 Ensure candlestick chart renders with correct colors and layout
    - Increasing candles: `#88d982`, decreasing: `#ffb3ac`; height 380px; no rangeslider; standard Plotly config from design
    - _Requirements: 4.1, 2.8_
  - [x] 4.4 Ensure metric row uses correct P&L color logic
    - Use `get_pnl_color_class(daily_pnl)` to select color for Daily P&L card
    - _Requirements: 4.3, 4.4_
  - [x] 4.5 Ensure execution log table shows placeholder row when terminal_log is empty
    - When `log_rows` is empty after parsing, set `log_rows` to `[{"cells": ["--:--:--", "Awaiting system activity..."], "colors": ["muted", "muted"]}]`
    - _Requirements: 4.5, 4.6, 12.3_

- [x] 5. Implement View 3: Signals & Intelligence (`view_signals`)
  - [x] 5.1 Add outer `try/except` error boundary wrapping the entire function body
    - _Requirements: 1.6, 12.1_
  - [x] 5.2 Replace inline conviction color logic with `get_conviction_color_class`
    - Call `get_conviction_color_class(conv)` for each scan result row's color class
    - _Requirements: 5.2, 5.3, 5.4_
  - [x] 5.3 Ensure scan results table shows placeholder row when scan_results is empty
    - When `scan_rows` is empty, set to `[{"cells": ["--", "--", "--", "--", "--"], "colors": ["muted"]*5}]`
    - _Requirements: 5.5, 12.3_
  - [x] 5.4 Fix False Signal Tracker — complete the truncated expression
    - The `{len(se` truncation was fixed in Task 1; verify the full expression `{len(sells) - wins} / {len(sells)}` renders correctly in the Signal Quality panel
    - _Requirements: 1.5, 5.7_

- [x] 6. Implement View 4: Risk Management (`view_risk`)
  - [x] 6.1 Add outer `try/except` error boundary wrapping the entire function body
    - _Requirements: 1.6, 12.1_
  - [x] 6.2 Remove interactive shock slider; replace with fixed -5% scenario display
    - Call `run_scenario_analysis(broker, config, shock=-0.05)` directly (no slider widget)
    - Display estimated portfolio impact in Rupiah and as a percentage of AUM in a static card
    - _Requirements: 6.2_
  - [x] 6.3 Implement Portfolio Heat SVG radial gauge
    - Compute `heat_pct = (total_risk / broker.get_balance() * 100)` and `heat_normalized = min(100, (heat_pct / max_heat) * 100)`
    - Compute SVG offset: `offset = 283 - (283 * heat_normalized / 100)`
    - Color: `#ffb3ac` when heat_normalized > 80, `#bcc9c6` when 50–80, `#66d9cc` when < 50
    - _Requirements: 6.1_
  - [x] 6.4 Render Kelly Criterion readout (label text only) and four metric cards
    - Call `calculate_kelly_suggestion(broker, 1000, 950, config)` and display `kelly['label']`
    - Render four Metric_Cards: Daily Loss Limit, Max Drawdown, Active Strategies, Stress Test (PASS/FAIL)
    - Stress Test card: `"PASS"` with `profit` color when `heat_pct < max_heat`, else `"FAIL"` with `loss` color
    - _Requirements: 6.3, 6.4, 6.5_

- [x] 7. Implement View 2: Portfolio Analytics (`view_portfolio`)
  - [x] 7.1 Add outer `try/except` error boundary wrapping the entire function body
    - _Requirements: 1.6, 12.1_
  - [x] 7.2 Ensure equity curve chart renders correctly or shows placeholder
    - Check `len(eq_data) >= 2` before rendering Plotly chart; show placeholder text `Equity data will appear after the first sweep cycle.` otherwise
    - Chart: 1.5px `#66d9cc` line, dashed reference line at `config['portfolio']['initial_equity']`, standard Plotly config
    - _Requirements: 7.1, 7.2, 2.8, 12.4_
  - [x] 7.3 Replace inline sector bar color logic with `get_sector_bar_color`
    - Call `get_sector_bar_color(pct)` for each sector's progress bar color
    - _Requirements: 7.6_
  - [x] 7.4 Ensure active positions table shows placeholder row when no open positions
    - When `pos_rows` is empty, set to `[{"cells": ["--", "--", "--", "--"], "colors": ["muted"]*4}]`
    - _Requirements: 7.4, 7.5, 12.3_

- [x] 8. Implement View 5: Trade Journal (`view_journal`)
  - [x] 8.1 Add outer `try/except` error boundary wrapping the entire function body
    - _Requirements: 1.6, 12.1_
  - [x] 8.2 Implement closed trades table
    - Source from `broker.get_trade_history()` filtered to `action == 'SELL'`, reversed, limited to 20
    - Compute P&L % as `(realized_pnl / (price * qty)) * 100`; apply `profit`/`loss` color via `get_pnl_color_class`
    - When no SELL records exist, render placeholder row with `--` in all cells
    - _Requirements: 8.1, 8.2, 8.3, 12.3_
  - [x] 8.3 Implement monthly P&L bar chart or placeholder
    - Group sells by `datetime.fromisoformat(t['date']).strftime('%b')`; bar colors `#88d982` for profit months, `#ffb3ac` for loss months
    - No area fills, no legend inside plot area; standard Plotly config
    - When no sells exist, render placeholder card: `Trade history will appear after completed sell trades.`
    - _Requirements: 8.4, 8.5, 2.8, 12.4_

- [x] 9. Implement View 6: Settings & Configuration (`view_settings`)
  - [x] 9.1 Add outer `try/except` error boundary wrapping the entire function body
    - _Requirements: 1.6, 12.1_
  - [x] 9.2 Implement Watchlist Manager using `render_input_field` and duplicate-check logic
    - Use `render_input_field` from `components/input_field.py` for the ticker input
    - On submit, call `add_ticker_if_not_exists(config['stocks'], new_ticker)` before writing `config.json`
    - _Requirements: 9.1, 9.2, 10.1_
  - [x] 9.3 Replace parameter sliders with read-only text display
    - Remove any `st.slider` widgets for RSI Length, ATR Period, Conviction Threshold
    - Render each as `st.markdown(f'<div class="kl-mono-sm">{value}</div>', unsafe_allow_html=True)`
    - _Requirements: 9.3_
  - [x] 9.4 Remove "Run Health Check" button; show last-known cached status only
    - Remove any `st.button` that triggers a health check ping
    - Read from `st.session_state.health_results` (defaulting to `{}` if absent) and render four `render_status_indicator` rows
    - When `health_results` is not set, render all four services with `offline` status and description `Not checked`
    - _Requirements: 9.4, 9.5, 9.8_
  - [x] 9.5 Render terminal readout and Institutional Data Hub
    - Terminal readout: MODE (DEMO/PAPER TRADING), LAST_SYNC in WIB, SYSTEM.STATUS
    - Data Hub: multi-select for tickers + download button calling `compile_institutional_data`
    - _Requirements: 9.6, 9.7_

- [x] 10. Checkpoint — Ensure all views render without errors
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Write property-based tests using `hypothesis`
  - Create `tests/test_kinetic_ledger.py` with the following sub-tasks:
  - [ ]* 11.1 Write property test for conviction color mapping (Property 1)
    - **Property 1: Conviction score maps to exactly one color class**
    - Use `@given(st.floats(min_value=0.0, max_value=10.0))` with `@settings(max_examples=100)`
    - Assert `get_conviction_color_class(score)` returns exactly one of `"profit"`, `"neutral"`, `"loss"` with correct boundary logic
    - **Validates: Requirements 5.2, 5.3, 5.4**
  - [ ]* 11.2 Write property test for P&L color mapping (Property 2)
    - **Property 2: P&L sign maps to exactly one color class**
    - Use `@given(st.floats(allow_nan=False, allow_infinity=False))` with `@settings(max_examples=100)`
    - Assert `get_pnl_color_class(pnl)` returns `"profit"` when pnl ≥ 0 and `"loss"` when pnl < 0
    - **Validates: Requirements 8.2**
  - [ ]* 11.3 Write property test for sector bar color threshold (Property 3)
    - **Property 3: Sector allocation threshold maps to correct bar color**
    - Use `@given(st.floats(min_value=0.0, max_value=100.0))` with `@settings(max_examples=100)`
    - Assert `get_sector_bar_color(pct)` returns `"#ffb3ac"` when pct > 40 and `"#66d9cc"` otherwise
    - **Validates: Requirements 7.6**
  - [ ]* 11.4 Write property test for duplicate ticker prevention (Property 4)
    - **Property 4: Duplicate ticker prevention preserves list length**
    - Use `@given(st.lists(st.text(min_size=1), min_size=1), st.integers(min_value=0))` with `@settings(max_examples=100)`
    - Deduplicate the generated list, pick an existing ticker by index, assert `add_ticker_if_not_exists` returns a list of the same length
    - **Validates: Requirements 9.2**
  - [ ]* 11.5 Write property test for empty table placeholder row (Property 5)
    - **Property 5: Empty table input always produces at least one rendered row**
    - Extract a `render_kinetic_table_to_html(headers, rows) -> str` helper (or test via the existing function's HTML output captured from `st.markdown` mock)
    - Assert the HTML contains at least 2 `<tr>` elements (thead + 1 tbody placeholder) when rows is empty
    - **Validates: Requirements 12.3**
  - [ ]* 11.6 Write property test for view resilience on empty data (Property 6)
    - **Property 6: View functions do not propagate exceptions on empty data**
    - Mock `broker`, `db`, and `st.session_state` to return empty collections
    - Assert each of the six view functions does not raise when called with empty data
    - **Validates: Requirements 1.6, 12.1, 12.2**

- [x] 12. Add view router with error wrapping
  - Replace the bare view dispatch at the bottom of `app.py` with a `view_map` dict and a `try/except` wrapper:
    ```python
    view_map = {"command": view_command, "portfolio": view_portfolio, "signals": view_signals, "risk": view_risk, "journal": view_journal, "settings": view_settings}
    current_view = st.session_state.get('kl_active_view', 'command')
    view_fn = view_map.get(current_view, view_command)
    try:
        view_fn()
    except Exception as e:
        st.error(f"Failed to render view: {e}")
    ```
  - Ensure the auto-pilot state machine block follows immediately after the view router, unchanged
  - _Requirements: 3.5, 12.2_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Pure helper functions (Task 3) must be extracted before view tasks (Tasks 4–9) so they are available to all views
- Property tests (Task 11) require the pure helpers from Task 3 to be importable at module level
- The auto-pilot state machine block at the bottom of `app.py` must not be modified at any point
