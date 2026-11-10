---
name: invest-market-scanner
description: >-
  Unified quantitative market scanner for Vietnam equities combining 3-Tier VN-Index Market Regime Gate,
  Multi-Factor Convergence (WFE V3.5 Wyckoff Phase C/D, High R:R V2.2 Range Rebound & Breakout,
  MCDX Banker Flow BII, Mansfield Relative Strength Leaders, Sector Breadth, and 15D Foreign Flow).
  Outputs explicit Optimal Buy Zones (anti-T+2.5 trap), When NOT to Buy (veto rules), When MUST Sell
  (ATR Stop, 5-rule Spring Guard, 3-stage Trailing Stop, Climax Exit, Time-Stop), and Capital Allocation (% NAV).
  Triggers: "quét cổ phiếu", "cổ phiếu đáng mua nhất", "tỷ lệ r:r cao", "kèo ngon r:r", "mua sát đáy hỗ trợ",
  "điểm mua rủi ro thấp", "high rr setup", "tìm kèo r:r cao", "tìm cổ phiếu mạnh nhất", "cổ phiếu dẫn dắt",
  "top rs", "quét leader", "market leaders", "top cổ phiếu khỏe", "mcdx flow radar", "dòng tiền tạo lập",
  "quét mcdx", "dòng tiền lớn", "tiền to vào", "established flow", "emerging flow", "gom bí mật", "flow turn",
  "banker intensity", "bii", "quét pha c d", "wyckoff pha c", "wyckoff pha d", "tìm điểm mua lps",
  "test spring", "kèo pha c", "kèo lps", "wyckoff phase c d", "điểm mua đón lõng", "wfe v3", "cơ hội đầu tư".
---

# Unified Market Scanner (`invest-market-scanner`)

## 1. Execution Workflow (1-Call Pipeline)

Always call `scan_unified_opportunities` from the `vnstock` MCP server first:

```python
scan_unified_opportunities(
    preset="all",            # "all" (default convergence) | "high_rr" | "wfe" | "leaders" | "mcdx"
    min_rr=1.8,
    max_risk_pct=6.5,
    min_avg_val_bil=15.0,
    top_n=10,
    symbols=None,            # Optional custom ticker list
    include_foreign_flow=True
)
```

- **Preset Selection:**
  - General / best opportunities / multi-factor scan $\rightarrow$ `preset="all"`
  - Explicit High R:R request $\rightarrow$ `preset="high_rr"`
  - Explicit Wyckoff Phase C/D or WFE V3.5 request $\rightarrow$ `preset="wfe"` (or call `scan_wfe_v3` if full L5 trace snapshot is requested)
  - Explicit RS Market Leaders request $\rightarrow$ `preset="leaders"`
  - Explicit MCDX Banker Flow request $\rightarrow$ `preset="mcdx"` (automatically includes entry/SL/target & governance plan — no extra tool calls needed)
- **Persist Recommended Setups:** When presenting actionable recommendations, call `evaluate_positions_and_exits(action="upsert", positions=[...])` with the top 3–5 actionable setups so future sessions automatically track them.

---

## 2. Quantitative Architecture & Hard Governance Rules

1. **3-Tier Market Regime Gate (VN-Index vs SMA50):**
   - `BULL` ($\text{VNINDEX} \ge \text{SMA50}$, $\text{Slope}_{5D} \ge -0.5\%$, $\text{DistDays}_{10D} \le 3$): Max portfolio equity = **100% NAV** ($\le 25\%$ NAV/stock). Both Archetype A (Support/Spring) and Archetype B (Breakout/LPS) enabled.
   - `CAUTION` ($\text{VNINDEX} \in [0.96 \times \text{SMA50}, \text{SMA50})$ or $\ge 4$ distribution days): Max portfolio equity capped at **40% NAV** ($\le 12.5\%$ NAV/stock, keep $\ge 60\%$ cash). **Breakout setups (Type B) are VETOED**. Only allow Support/Spring setups with $\text{RS\_Score} \ge +3\%$ and $\text{MCDX Red}_{20} > 5.0$.
   - `BEAR` ($\text{VNINDEX} < 0.96 \times \text{SMA50}$ with $\text{Slope}_{5D} < -1.0\%$): **LOCK large deployments** (hold 90–100% cash; max 0–10% NAV T0 probe on extreme capitulation).
2. **MCDX 24HMoney Scale Normalization:**
   - $\text{Red}_{20} = \text{flow\_trend}_{100} / 5.0$ (0–20 scale).
   - $\text{Red}_{20} > 5.0$ ($>25\%$): Tag `[FLOW_CONFIRMED]`. Never tag `[NO_FLOW]` when $\text{Red}_{20} > 5.0$.
   - $\text{Red}_{20} \le 5.0$ and not Emerging: Tag `[NO_FLOW]` and cut recommended position size by **50%**.
   - $\text{flow\_dist}_{100} \ge 70$: Tag `[CẢNH BÁO PHÂN PHỐI]` and VETO new buys.
3. **VPA & Candle Anatomy Precision:**
   - **No Supply:** Strictly down or flat bar ($\text{Close}_T \le \text{Close}_{T-1}$) with $\text{RVol} < 0.70$. Never call an up bar "No Supply".
   - **Hammer vs Marubozu:** Lower shadow $\ge 20\%$ of range is Hammer/Test of Supply, never Marubozu.
   - **Anti-T+2.5 Trap:** If price is stretched $> 1.5 \times \text{ATR}_{14}$ above support/pivot, or $\text{RSI}_{14} \ge 68$, or $\text{RVol} > 3.0$ with $>4\%$ surge, enforce `[WAIT_PULLBACK_LIMIT]` at `optimal_buy_zone`.
4. **Zero Fluff / No Disclaimers:**
   - Never output legal/system disclaimers or hype words (*"bảo kê", "chắc thắng", "siêu cổ", "tuyệt đối"*).
   - If `is_box_unstable=True`, state verbatim: *"Hộp tích lũy không ổn định, hủy bỏ mục tiêu sóng dài"* and omit Target 2.

---

## 3. Mandatory Output Structure (Vietnamese, Concise)

Present results in Vietnamese with these exact 4 sections:

### 1. Chế độ Thị trường (Market Regime) & Phân bổ Tổng Vốn (% NAV)
- **VN-Index:** `[Điểm số]` vs `SMA50 ([Giá trị])` | **Độ dốc 5D:** `[...]%` | **Phân loại:** `[BULL / CAUTION / BEAR]`
- **Khuyến nghị Phân bổ Danh mục:** Tối đa `[X]% NAV` cổ phiếu / `[100-X]% NAV` tiền mặt.
- **Top Ngành Dẫn dắt (Sector Breadth):** Liệt kê Top 2–3 ngành có `% mã RS > 0` cao nhất.

### 2. Bảng Xếp hạng Cơ hội Hội tụ Đa Tín hiệu
| Hạng | Mã (Ngành) | Điểm Hội tụ (Tín hiệu) | Setup | Giá | Vùng Mua Tối Ưu | SL (ATR) | T1 / T2 | R:R₁ | RSI₁₄ | RS | MCDX (Red/20) | Ngoại (15D) | Vốn (% NAV) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |

### 3. Kế hoạch Giao dịch Chi tiết cho Top Cơ hội (Mua / Không Mua / Phải Bán / Chia Vốn)
For each Top 3–5 stock, explicitly output:
- **luận điểm Hội tụ & VPA:** (`converged_signals`, `vpa_status`, `volume_trend_5d`, `support_tag`).
- **💰 Phân bổ vốn bao nhiêu (`capital_allocation`):**
  - Tổng tỷ trọng khuyến nghị: `[X]% NAV` (chia **Tranche 1 thăm dò:** `[T1_pct]% NAV` tại vùng `[buy_low - buy_high]`; **Tranche 2 gia tăng:** `[T2_pct]% NAV` chỉ khi hàng T1 đã về T+2.5 và giá vượt `[trigger]` kèm $\text{RVol} \ge 1.2$).
- **🚫 Khi nào KHÔNG ĐƯỢC MUA (`when_not_to_buy`):**
  - Liệt kê cụ thể các mức giá/điều kiện cấm mua từ trường `when_not_to_buy` (mua đuổi vượt vùng mua tối ưu, RSI quá mua, thủng hỗ trợ đầu phiên, hoặc VN-Index vi phạm Regime).
- **🚨 Khi nào PHẢI BÁN (`when_must_sell`):**
  - **Cắt lỗ bắt buộc (Hard Stop):** Đóng cửa $\le \text{SL}$ (`[stop_loss]`, rủi ro `-[risk_pct]%`), trừ khi thỏa đủ 5 điều kiện `[SPRING_TEST]` (nhúng thủng SL nhưng rút chân $\text{CP} \ge 70\%$, $\text{RVol} \ge 1.0$, biên độ $\ge \text{median}_{20D}$, chờ xác nhận $T+1$).
  - **Chốt lời & Khóa lãi Giai đoạn 2:** Chạm $\text{T1}$ (`[target_1]`) hoặc lãi $\ge +5\% \rightarrow$ Chốt 50%, nâng cứng $\text{Operative SL} = \max(\text{Entry}, \min(\text{Low}_{3D}))$.
  - **Chốt lời chủ động Giai đoạn 3 / Đỉnh Climax:** Bán 100% tại $\text{T2}$ (`[target_2]`) hoặc ngay khi xuất hiện nến Upthrust/Buying Climax ($\text{RSI}_{14} \ge 72$, $\text{CP} \le 40\%$, $\text{RVol} \ge 1.4$).
  - **Time-Stop (T+8):** Quá 8 phiên đi ngang $\pm 1.5\%$ quanh giá vốn kèm dòng tiền suy yếu $\rightarrow$ Bán cơ cấu.
