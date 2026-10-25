# US Stock Momentum Screener (Layer 0 + Layer 1)

An End-of-Day (EOD) US equity screening web application implementing **Layer 0 (Candidate Universe Pre-Filter)** and **Layer 1 (Mark Minervini's 8-Condition Trend Template + Short-Term Swing Alignment + Dynamic S&P 500 1M/6M Outperformance)**.

---

## Features Built

### 1. Layer 0: Candidate Universe Pre-Filter (12 Adjustable Controls)
All figures can be modified on the fly with sub-second (`<1s`) recalculation:
- **Min / Max Market Cap (\$B):** Default `>= $3.0B` (adjustable anytime e.g. to `$2.0B`).
- **Min Share Price (\$):** Default `>= $10.0`.
- **Multi-Horizon Volume Filters:** Independent inputs for **1D Volume**, **10D Avg Vol**, **30D Avg Vol**, **60D Avg Vol**, and **90D Avg Vol** (all default `> 500,000` shares).
- **Min Dollar Volume (`Price × Vol`):** Default `> $50M USD`.
- **US Exchanges & Security Types:** `NYSE`, `NASDAQ`, `AMEX`, Exclude ETFs/Funds toggle, and Include ADRs toggle.

### 2. Layer 1: Extended 11-Condition Trend & Momentum Template
Every condition has an independent **ON/OFF toggle** and adjustable thresholds:
- **C1:** $\text{Close} > \text{SMA}_{150}$ and $\text{Close} > \text{SMA}_{200}$
- **C2:** $\text{SMA}_{150} > \text{SMA}_{200}$
- **C3:** $\text{SMA}_{200}$ trending upward over $N$ lookback trading days (default `20` days $\approx 1$ month)
- **C4:** $\text{SMA}_{50} > \text{SMA}_{150} > \text{SMA}_{200}$
- **C5:** $\text{Close} > \text{SMA}_{50}$
- **C6:** $\text{Close} \ge \text{52W Low} \times (1 + X\%)$ (default `30%` above 52W low)
- **C7:** $\text{Close} \ge \text{52W High} \times (1 - Y\%)$ (default within `25%` of 52W high)
- **C8:** Pool-wide **Relative Strength (RS) Percentile** $\ge P$ (default `70` out of 1–99, weighted $40\% \times 3\text{M} + 20\% \times 6\text{M} + 20\% \times 9\text{M} + 20\% \times 12\text{M}$)
- **C9:** Short-term swing alignment: $\text{SMA}_{10} \ge \text{SMA}_{20}$
- **C10:** **1M Performance > Dynamic S&P 500 Target** (`2.0x` S&P 500 1M return when S&P $\ge 0\%$; `0.5x` when S&P $< 0\%$, plus manual override)
- **C11:** **6M Performance > Dynamic S&P 500 Target** (`2.0x` S&P 500 6M return when S&P $\ge 0\%$; `0.5x` when S&P $< 0\%$, plus manual override)

---

## Step-by-Step Guide to Run Locally or Deploy Free to the Cloud

### Option 1: Run Locally on Your PC
1. Open a terminal in `c:\BKCHO\Job\USStockVCP` and install the dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
2. Run the unit tests to verify the math engine:
   ```powershell
   python -m tests.test_screener
   ```
3. Launch the interactive web dashboard:
   ```powershell
   streamlit run app.py
   ```

---

### Option 2: Deploy 100% Free to Streamlit Community Cloud + GitHub Actions
1. **Create a GitHub Repository:**
   - Go to [github.com/new](https://github.com/new) and create a repository (e.g., `us-stock-vcp-screener`).
   - Push this folder (`c:\BKCHO\Job\USStockVCP`) to your GitHub repository:
     ```powershell
     git init
     git add .
     git commit -m "Initial commit: US Stock Momentum Screener Layer 0 + Layer 1"
     git branch -M main
     git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/us-stock-vcp-screener.git
     git push -u origin main
     ```
2. **Automatic Daily EOD Data Updates (GitHub Actions):**
   - The workflow in [`.github/workflows/daily_eod_update.yml`](file:///c:/BKCHO/Job/USStockVCP/.github/workflows/daily_eod_update.yml) will automatically run **Monday–Friday at 21:30 UTC (after US market close)**, fetch the latest TradingView + Yahoo Finance EOD data and S&P 500 benchmark, and save the updated snapshot to `data/daily_snapshot.parquet`.
   - You can also trigger it manually anytime from your GitHub repo's **Actions** tab → **Daily EOD US Stock Screener Data Update** → **Run workflow**.
3. **Connect to Streamlit Community Cloud (Free 24/7 Web URL):**
   - Go to [share.streamlit.io](https://share.streamlit.io) and sign in with your GitHub account.
   - Click **Create app** → select your `us-stock-vcp-screener` repository, branch `main`, and main file path `app.py`.
   - Click **Deploy!** Within ~2 minutes, you will have a permanent `https://...streamlit.app` web link accessible from your computer or phone.
