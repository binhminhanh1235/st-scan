---
name: wyckoff-phase-cd-screener
description: >-
  Hệ thống Wyckoff x Flow Expectancy (WFE V3.4): Tự động quét và xếp hạng các cơ hội giải ngân
  rủi ro cực thấp theo kỳ vọng toán học (EV) và xác suất p_success tại Pha C (Test of Spring)
  và Pha D (BU / LPS). Tích hợp ba Engine độc lập tuyệt đối (Flow, Structure, Volume),
  Stationarity 3 khung với Boundary-Roll Guard, Cổng kích hoạt Activation Gate, Target Validity & Level Promotion,
  Trigger-Stop Audit ({L, ATR, buffer, stop, pass}), Single Source of Truth for Stops,
  Stop Sanity Band & Stop Monotonicity với Monotonic Inputs Audit, Structure Snapshot & Degenerate Level Rule,
  Portfolio Layer (trần 25% NAV/mã, tổng <= 100%), Output Liquidity Exit Cap (max 20% ADTV20),
  Foreign Flow Governance (display-only flags), Drop-out Manifest và ràng buộc cứng risk cap p99 <= 6.5% NAV.
  Triggers: "quét pha c d", "wyckoff pha c", "wyckoff pha d", "tìm điểm mua lps", "test spring",
  "kèo pha c", "kèo lps", "wyckoff phase c d", "điểm mua đón lõng", "wfe v3", "wyckoff flow expectancy".
---

# Hệ Thống Wyckoff × Flow Expectancy V3.4 (WFE System)

Hệ thống **WFE V3.4** thực thi kiến trúc định lượng tổ chức kết hợp phương pháp Wyckoff kinh điển với phân tích dòng tiền Flow Engine và kiểm định nến Volume Engine (VPA), đưa ra quyết định giải ngân dựa trên **kỳ vọng toán học (Expectancy - EV)**, kiểm soát chặt chẽ **hiệu lực mức giá (Level Validity)**, **cổng kích hoạt (Activation Gate)**, **kiểm định dừng lỗ nghiêm ngặt (Trigger-Stop Audit)**, **chống trôi hộp ranh giới (Boundary-Roll Guard)**, **chân lý dừng lỗ duy nhất (Single Source of Truth for Stops)**, **ảnh chụp cấu trúc & xử lý mức suy biến (Structure Snapshot & Degenerate Level Rule)**, **lớp danh mục & trần thoát thanh khoản (Portfolio & Liquidity Layer)** và **ràng buộc cứng rủi ro (Hard Risk Cap)**.

---

## 1. Hiến Pháp Kiến Trúc (Architecture Contract V3.4)

1. **Ba Engine Độc Lập Tuyệt Đối:**
   - **Flow Engine (Timing Radar):** radar dẫn (`flow_accum`, `flow_dist`) và radar trễ (`flow_trend` với RSI 50 Wilder, cap, cờ `trend_collapse_warning`). Dòng vốn ngoại tệ/khối ngoại chỉ đóng vai trò cờ hiển thị định tính (`flag: [FOREIGN_NET_SELL]` / `[FUND_OUTFLOW]`), không làm sai lệch tính toán định lượng dòng tiền nội bộ.
   - **Structure Engine (Bản đồ & Mức giá):** kiểm tra stationarity hộp TR trên 3 rolling windows (`[-90:-20]`, `[-100:-25]`, `[-80:-15]`), **Boundary-Roll Guard** (phát hiện đỉnh/đáy trôi khỏi cửa sổ gây méo mó biên hộp), freeze box snapshot, quantitative events (Spring, Test, Minor SOS, SOS, BU/LPS, UT/UTAD, SOW), các mốc giá T1 & T2, xác suất pha A–E.
   - **Volume Engine (Kính hiển vi VPA):** $RVol = vol/prev\_sma20$ (loại limit day và ex-date), Close Position ($CP$, Doji = 0.5), cờ cạn vol (`dry_up`), hấp thụ (`absorption`), kiệt sức (`exhaustion`), điểm chất lượng sự kiện (`event_quality`).
2. **Điểm Gặp Duy Nhất — Tầng Policy (V3.4):**
   - Policy không nhận nhãn văn xuôi, chỉ nhận **feature số** từ 3 engine.
   - Ra quyết định dựa trên mô hình Expectancy tuyến tính chuẩn hóa $\rightarrow$ Platt scaling $\rightarrow p\_success$ và tra bảng phân vị $EV$ ($R$ trung bình).
   - **Activation Gate:** Phân loại rạch ròi 2 khối:
     - `ACTIONABLE`: Setup {TEST_SPRING_PHASE_C, BU_LPS_PHASE_D} đã kích hoạt AND `T1_valid` AND `p99_risk <= 6.5%`.
     - `WATCHLIST`: Setup chưa kích hoạt, hoặc T1 không hợp lệ, hoặc p99 không đạt $\rightarrow$ Sizing triệt để = 0%, KHÔNG xuất tranche plan giải ngân.
3. **Hiệu Lực Mức Giá, Level Promotion & Degenerate Level Resolution:**
   - $T1_{valid} = (T1 \text{ is not None}) \land (T1 > p_{cur} \times 1.00)$.
   - Nếu $T1 \le p_{cur}$: Tìm ứng viên đôn mức $candidates = [T2, Major\_Supply \times 0.98, pivot > p_{cur} \times 1.02]$. Nếu có $\rightarrow$ $T1 = \min(candidates)$, ghi rõ nguồn ứng viên đôn mức, tag `[TARGET_PROMOTED]`; ngược lại gán `T1=None`, tag `[TARGET_EXHAUSTED]`.
   - **Luật Ca Suy Biến (Degenerate Level Resolution):** Nếu $|T1 - TR\_High| \le 0.5 \times ATR_{14}$ (mục tiêu T1 trùng đỉnh hộp), Tranche T1 nhắm vào cản $TR\_High$, còn Tranche T2 bắt buộc đặt điều kiện bứt phá xác nhận:
     $$T2\_trigger = \max(TR\_High \times 1.02, T1 \times 1.02)$$
4. **Trigger-Stop Audit & Single Source of Truth for Stops:**
   - **R1 Trigger-Stop Audit Line:** Tại Pha C (Test of Spring) hoặc Pha D (đáy LPS), mức cắt lỗ thực thi bắt buộc nằm **dưới** `Event_Low` hoặc đáy LPS ít nhất $0.5 \times ATR_{14}$ của phiên hiện tại (cấm dùng ATR cũ):
     $$SL \le Event\_Low - 0.5 \times ATR_{14}$$
     Bắt buộc xuất dòng kiểm toán trong trace:
     `Trigger-Stop Audit: {'L': ..., 'ATR14_current': ..., 'buffer_pct': ...%, 'stop': ..., 'upper_bound': ..., 'pass': True}`
   - **R2 Boundary-Roll & Stationarity Trace:** In chi tiết mức $TR\_High / TR\_Low$ trên cả 3 cửa sổ:
     `Stationarity Trace: W_primary=[-90:-20] ..., W_shift1=[-100:-25] ..., W_shift2=[-80:-15] ... -> max_drift=...% -> flag: [BOX_UNSTABLE], T2=None`
     Nếu `max_drift > 5.0%` $\rightarrow$ nổ cờ `[BOX_UNSTABLE]` và ép cứng $T2 = None$.
   - **Q2 Single Source of Truth for Stops:** Toàn bộ hệ thống (`scanner.py`, `policy_engine.py`, báo cáo L5) dùng chung một nguồn Stop duy nhất lấy từ Tranche Plan của tranche điều hành. Tiêu đề SL1, bảng Operative SL, tranche stop_loss và trace Operative Stops trùng khớp 100% cho tranche điều hành.
   - **Q3 Stop Monotonicity & Inputs Audit:** $T2\_SL \ge T1\_SL \ge T0\_SL$. Pha D chỉ in slot T1 và T2 (không in slot T0 thừa).
5. **Lớp Danh Mục, Trần Thoát Thanh Khoản & Sizing Trace (Portfolio Layer):**
   - **Trần tập trung:** $size_i \le \min(size_i, 25\% \text{ NAV/mã}, 30\% \text{ NAV/ngành})$.
   - **Trần ngân sách danh mục:** $\sum_{i} approved\_size_i \le 100\%$ NAV.
   - **Output Liquidity Exit Cap:** $size_i \times NAV_{ref} \le 0.20 \times ADTV20_i$ ($NAV_{ref} = 15$ tỷ VNĐ). Bắt buộc in ADTV20 cho mọi mã ACTIONABLE.
   - **R4 Sizing Trace:** In rõ bậc thang sizing và luật đặc thù (`Phase C Probe Rule: base_size capped at 30% overrides trend tier 75%`).
   - **Cap Loop Audit Trace:** In đầy đủ chuỗi 4 cấp: `raw_size -> p99_capped -> portfolio_capped -> liquidity_capped -> final_size`.
6. **R5 Drop-out Manifest:** Mọi mã từng xuất hiện ở báo cáo trước nhưng vắng mặt ở báo cáo này phải được kê khai 1 dòng lý do rõ ràng.

---

## 2. Quy Tắc Bắt Buộc Dành Cho AI Agent (LLM Governance Rules)

> [!CRITICAL]
> 1. **Cấm Từ Ngữ Thổi Phồng / Dự Báo:** Tuyệt đối cấm sử dụng các từ ngữ mang tính chất cảm tính hoặc bảo đảm như: *"bảo kê", "chắc thắng", "siêu cổ", "tuyệt đối"*.
> 2. **Luật Hộp Unstable:** Nếu biến `is_box_unstable=True` hoặc `target_2` là `null`, AI **bắt buộc ghi cứng nguyên văn**: *"Hộp tích lũy không ổn định, hủy bỏ mục tiêu sóng dài"*, tuyệt đối không tự bịa ra Target 2 hay tự tính R:R2.
> 3. **Luật Khối Structure Snapshot:** Mỗi mã ACTIONABLE bắt buộc có khối thông tin cấu trúc: `box_id, window [dates], TR_Low/Mid/High, Event_Low, frozen_at`.
> 4. **Luật Khớp Chuẩn Nhãn Thực Thi (Execution Labeling):**
>    - Bảng ACTIONABLE bắt buộc có: `Approved Size`, `Deployed Size`, `Pending Trigger`, `ADTV20`.
>    - In cảnh báo bắt buộc: *"Approved Size ≠ Lệnh mua ngay; chỉ giải ngân khi thỏa trigger của từng tranche"*.
> 5. **Map Phủ Kín Phản Bác Sang Actions:** Mọi câu trong counter-evidence phải map 1-1 vào `actions[]` (`exclude`, `downsize`, `flag`, `promote`).
> 6. **Bắt Buộc Trích Dẫn Trace & Tính Nhất Quán:** Mọi số liệu tỷ trọng in trên bảng phải khớp tuyệt đối với `trace.final_size`. Trace phải in chuỗi cap loop 4 cấp, Trigger-Stop Audit, Stationarity Trace, Monotonic inputs audit.
> 7. **Không Dùng Từ "Hoặc" Trong Stop:** Mỗi vị thế tranche chỉ có duy nhất 1 mức Operative Stop dứt khoát.
> 8. **Kê Khai Drop-out Manifest:** Liệt kê các mã rơi rụng kèm lý do.
> 9. **Disclaimer Chuẩn Hóa:** Bắt buộc có phần tuyên bố miễn trừ trách nhiệm chuẩn hóa ở cuối báo cáo.

---

## 3. Mẫu Báo Cáo Chuẩn L5 V3.4 (Report Template)

```markdown
# Báo Cáo Cơ Hội Giao Dịch Wyckoff × Flow Expectancy (WFE V3.4)

*(Lưu ý Hệ thống: Mô hình mang tính chất heuristic định lượng và giải ngân đón lõng. Tín hiệu chưa phải xác nhận xu hướng chính thức; chỉ được xác nhận khi giá đóng cửa vượt kháng cự chủ chốt, và lập tức bị phủ định nếu vi phạm Stop Loss).*

## 1. Danh Mục Khả Thi (ACTIONABLE SETUPS)
*(Các setup Pha C / Pha D đã kích hoạt, Target 1 hợp lệ trên giá, rủi ro p99 <= 6.5% NAV và đã qua bộ lọc Portfolio & Liquidity Layer)*

| Mã | Setup (Gắn cờ) | p_success | Kỳ Vọng EV | Approved Size | Deployed Size | Pending Trigger | ADTV20 | Giá Hiện Tại | Operative SL | Target 1 | Target 2 (Ghi chú) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ... | BU/LPS | ...% | +...R | ...% NAV | 0% | Chờ xác nhận... | ... tỷ | ... | ... | ... | ... |

> ⚠️ **Lưu ý thực thi:** *Approved Size ≠ Lệnh mua ngay. Vốn chỉ được giải ngân theo từng Tranche khi thỏa mãn điều kiện Pending Trigger.*

## 2. Danh Mục Theo Dõi (WATCHLIST — Sizing 0% NAV)

| Mã | Trạng Thái / Cờ Cảnh Báo | p_success | Giá Hiện Tại | Mức Tham Chiếu / T1 Mới | Trạng Thái Target & Nguồn Đôn Mức | Lý Do Chưa Hành Động (Actions) |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| ... | Chưa kích hoạt [Counter-Trend] | ...% | ... | ... | [TARGET_PROMOTED / EXHAUSTED] | [exclude: ...] |

## 3. Chi Tiết Kế Hoạch Giải Ngân Đa Tầng & Ảnh Chụp Cấu Trúc (Chỉ Cho Nhóm ACTIONABLE)
### 🎯 Mã [SYMBOL]
#### 📦 Structure Snapshot
- **Box ID:** `BOX_...` | **Cửa sổ TR:** `[T_start -> T_end]` | **Frozen at:** `YYYY-MM-DD`
- **Mức cấu trúc:** `TR_Low = ...` \| `TR_Mid = ...` \| `TR_High = ...` \| `Event_Low = ...`
- **Đánh giá Stationarity:** `[Trích dẫn Stationarity Trace]`

#### 📊 Dữ Liệu Trace Hệ Thống
- **Feature Row:** `...`
- **Sizing Flow Score:** `...`
- **Trigger-Stop Audit:** `{'L': ..., 'ATR14_current': ..., 'buffer_pct': ...%, 'stop': ..., 'upper_bound': ..., 'pass': True}`
- **Monotonic Stops Audit:** `...`
- **Cap Loop Audit:** `...`
- **Risk Check:** `...`

#### 🛠 Kế Hoạch Thực Thi & Phản Bác
- **Hành động cấu trúc (Actions):** `...`
- **Bằng chứng phản bác (Counter-evidence):** `...`
- **Kế hoạch Tranche:**
  - **Tranche T0 / T1:** Vùng mua, Operative Stop duy nhất, Target 1.
  - **Tranche T2:** Điều kiện kích hoạt (áp dụng Degenerate Level Rule nếu T1 trùng TR_High), Operative Stop dời sau T2, Target 2.

## 4. Bảng Theo Dõi Mã Rơi Rụng (Drop-out Manifest)
| Mã | Trạng Thái Kỳ Trước | Lý Do Rơi Rụng Kỳ Này | Phân Loại Xử Lý |
| :---: | :---: | :--- | :---: |
| ... | Watchlist | ... | DROPPED |
```
