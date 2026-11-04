"""
US Stock Momentum Screener — Modular 4-Tier Package Root.
- `src.config`: Default filter settings, URL helpers, and built-in strategy presets
- `src.infrastructure`: Supabase PostgREST client, market snapshot repo, and user preferences repo
- `src.providers`: TradingView scanner, Yahoo Finance 252-day OHLCV provider, and EOD sync service
- `src.layers`: Pluggable multi-layer screening engine (Layer 0, Layer 1, Pipeline, and Future Layers 2–5)
- `src.ui`: Modular Streamlit presentation components
"""
