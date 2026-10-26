-- =============================================================================
-- Supabase Cloud Database Schema for US Stock Momentum Screener
-- Copy and paste this entire script into the Supabase SQL Editor and click "Run"
-- =============================================================================

-- 1. Key-Value Store for Daily Overwritten EOD Stock Snapshot & S&P 500 Benchmark
-- (Overwrites each day so storage stays under ~1 MB forever)
CREATE TABLE IF NOT EXISTS public.screener_kv_store (
    key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Custom User Filter Presets (Layer 0 + Layer 1 configurations)
CREATE TABLE IF NOT EXISTS public.screener_presets (
    name TEXT PRIMARY KEY,
    description TEXT,
    layer0 JSONB NOT NULL,
    layer1 JSONB NOT NULL,
    saved_at_utc TEXT
);

-- 3. Historical Screening Run Logs
CREATE TABLE IF NOT EXISTS public.screener_run_history (
    run_id TEXT PRIMARY KEY,
    timestamp_utc TEXT NOT NULL,
    payload JSONB NOT NULL
);

-- Enable access for your API key
ALTER TABLE public.screener_kv_store DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.screener_presets DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.screener_run_history DISABLE ROW LEVEL SECURITY;
