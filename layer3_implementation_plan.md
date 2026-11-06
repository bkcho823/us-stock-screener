# Layer 3: 形態與結構確認 (Pattern & Structure Confirmation) 實作方案

**核心定位：** 從 Layer 1–2 精選出的全美最強動能與行業龍頭股（約 30–60 隻）中，進一步篩選出**「形態已經充分收縮蓄勢、浮額洗淨、即將或正在進入低風險買點」**的高勝率名單。

---

## 1. 兩大核心邏輯來源與量化指標定義

根據我們先前討論的系統架構與文獻拆解，Layer 3 由兩大互補模組構成：

### 模組 A：JLaw 核心趨勢結構（21 EMA & 50 EMA 多頭排列）
* **A1. 均線排列（EMA Alignment）：** $\text{Close} > \text{EMA}_{21} > \text{EMA}_{50}$（短線趨勢在長線之上，股價企於兩線上方）。
* **A2. 回調不破線（Pullback Support）：** 回調低點測試 21 EMA 或 50 EMA 但未跌破（距 21 EMA 不超過 $-1.5\%$ 或獲得反彈支撐）。

### 模組 B：Mark Minervini 經典 VCP（波動收縮形態）
* **B1. 前置漲幅（Prior Uptrend）：** 過去 1–3 個月曾有強勢主升段（漲幅 $\ge 20\%$）。
* **B2. 波動逐步遞減（Contraction Sequence）：**
  - 出現 2–4 次回調收縮（波幅如 $15\% \to 8\% \to 4\%$，波幅逐次縮小約一半）。
  - **最後一節收窄（Tight Close）：** 最近 5–10 個交易日內的高低波幅通常極其緊湊（通常在 $3\% - 8\%$ 以內）。
* **B3. 供應枯竭與量價背馳（Volume Contraction / Dry-up）：**
  - 在形態整固與收縮末端，成交量顯著萎縮至 **50 日均量的 30%–60% 以下**（代表浮額與賣壓已經枯竭）。

---

## 2. 數據獲取與指標計算架構

為了保持系統「< 1 秒即時篩選」的高效體驗：
1. **TradingView Scanner 數據補充：**
   - 擴展 `src/providers/tradingview_scanner.py` 中的查詢欄位，加入 TradingView 原生提供的 `EMA20` / `EMA50` / `Volatility.D` / `ATR` 等欄位（1 秒即可獲取全市場數據）。
2. **Yahoo Finance 歷史 K 線增強（yfinance）：**
   - 在每日 EOD 批量計算中，直接計算精確的 `EMA21`、`EMA50` 以及近 20–60 天波段高低收縮率（ATR 緊湊度）。
3. **VCP 緊湊度評分（VCP Tightness Score, 0–100）：**
   - 結合波幅收縮比例與量能枯竭比率，算出客觀的分數，並標記出形態等級（如 `VCP 3T (3次收縮)`, `Tight Consolidation`）。

---

## 3. 預計新增之 UI 膠囊（Top Pills）與觀察清單呈現

在頂部新增第 7 排精簡膠囊：
```text
[ ✅ L3: VCP 形態過濾: ON ▾ ]   [ 📈 EMA21 > 50 多頭排列 ▾ ]   [ 📉 量能枯竭要求 (<60% 均量) ▾ ]   [ 🎯 緊湊度門檻 (Tightness ≥ 60) ▾ ]
```

觀察清單表格新增：
* **`VCP Status`**（如 `VCP 3T (Tight: 4.2%)` 或 `Pullback 21EMA`）。
* **`Vol Dry-up`**（收縮量能比率，如 `38% of 50MA`）。
* **`VCP Score`**（0–100 緊湊度評分）。
