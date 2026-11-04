# US Stock Momentum Screener (Modular 4-Tier Architecture)

An End-of-Day (EOD) US equity screening web application implementing **Layer 0 (Candidate Universe Pre-Filter)** and **Layer 1 (Mark Minervini's 8-Condition Trend Template + Short-Term Swing Alignment + Dynamic S&P 500 1M/6M Outperformance)**, structured on a clean **4-Tier Modular Architecture** ready for **Layers 2–5 (Sector Strength, VCP Tightness, Entry Pivot Signals, and Position Sizing)**.

---

## Modular Software Architecture

```text
USStockVCP/
├── app.py                              # Thin ~55-line orchestrator (wires UI + Screening Pipeline)
├── requirements.txt
├── supabase_schema.sql
├── .github/workflows/
│   └── daily_eod_update.yml            # Weekday EOD cron job (`python -m src.providers.eod_sync_service`)
│
├── src/
│   ├── config/                         # 1. CONFIGURATION & BUILT-IN PRESETS
│   │   ├── settings.py                 # Threshold defaults, URL helpers, condition metadata
│   │   └── builtin_presets.py          # Built-in strategy presets (Bryan's Full, TV, BRD)
│   │
│   ├── infrastructure/                 # 2. CLOUD DATABASE & PERSISTENCE ADAPTERS (100% Online Supabase)
│   │   ├── supabase_client.py          # PostgREST HTTP client + URL normalizer
│   │   ├── market_repo.py              # Load/Save EOD stock snapshot & S&P 500 benchmark
│   │   └── user_prefs_repo.py          # Load/Save Custom Presets, Run Logs, & BKCHO Layout ID
│   │
│   ├── providers/                      # 3. EXTERNAL MARKET DATA PROVIDERS
│   │   ├── tradingview_scanner.py      # Fetches US stock metadata & volumes from TradingView
│   │   ├── yahoo_finance.py            # Fetches S&P 500 benchmark & 252-day SMA/RS history
│   │   └── eod_sync_service.py         # End-of-day batch pipeline combining providers -> Supabase
│   │
│   ├── layers/                         # 4. PLUGGABLE MULTI-LAYER SCREENING ENGINE
│   │   ├── base.py                     # ScreeningPipelineResult & ScreeningLayer contract
│   │   ├── layer0_universe.py          # Layer 0: Universe Pre-Filter (Mkt Cap, Price, Vol, Exch)
│   │   ├── layer1_trend.py             # Layer 1: 11 Trend/Momentum Rules + Bottleneck stats
│   │   ├── pipeline.py                 # Sequential runner: L0 -> L1 (-> future L2/L3/L4/L5)
│   │   └── future/                     # Ready-to-implement extension modules:
│   │       ├── layer2_sector.py        # Layer 2: Sector & Industry Group Strength
│   │       ├── layer3_vcp.py           # Layer 3: VCP Tightness & Contraction Detection
│   │       ├── layer4_entry.py         # Layer 4: M.E.T.A. Pivot Breakout Trigger
│   │       └── layer5_risk.py          # Layer 5: Stop-Loss & Position Sizing Calculator
│   │
│   └── ui/                             # 5. PRESENTATION LAYER (MODULAR STREAMLIT COMPONENTS)
│       ├── theme.py                    # Custom CSS styles (hidden sidebar, top pill styling)
│       ├── state_manager.py            # Session state init, active row index, preset switching
│       ├── top_header.py               # Title, DB badge, Preset picker, BKCHO URL, Refresh
│       ├── pills/                      # Modular Top Filter Pill Bars:
│       │   ├── layer0_pills.py         # 11 Layer 0 Universe pills (2 wide rows)
│       │   └── layer1_pills.py         # 11 Layer 1 Trend/Momentum pills (2 wide rows)
│       ├── bottleneck_strip.py         # Color-coded condition pass-rate chip bar
│       ├── watchlist_grid.py           # Toolbar, active row highlight table, CSV export
│       └── tradingview_cockpit.py      # Prev/Next bar, PgUp/PgDn/Space JS, & live TV widget
│
└── tests/                              # 6. AUTOMATED UNIT TESTS PER LAYER
    ├── test_layer0.py
    ├── test_layer1.py
    └── test_pipeline.py
```

---

## Local Verification & Launch

1. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Run the automated unit test suite:
   ```powershell
   python -m unittest discover -s tests -v
   ```
3. Launch the Streamlit web app:
   ```powershell
   streamlit run app.py
   ```
