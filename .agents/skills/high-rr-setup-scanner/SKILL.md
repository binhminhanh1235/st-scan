---
name: high-rr-setup-scanner
description: >-
  Tự động quét và xếp hạng các cơ hội giao dịch có tỷ lệ Lợi nhuận / Rủi ro (Risk : Reward - R:R)
  thực tế cao nhất thị trường Việt Nam dựa trên nguyên tắc Lợi nhuận Tuyệt đối (Absolute Return).
  Tích hợp bộ lọc Xu hướng (Trend Filter > SMA50), Stop Loss động theo ATR_14 (chống Stop-hunt),
  Mục tiêu thực tế (Target 1 theo giá đóng cửa & Target 2 theo đỉnh Trading Range), và logic VPA chuyên sâu.
  Triggers: "cổ phiếu đáng mua nhất", "tỷ lệ r:r cao", "kèo ngon r:r", "mua sát đáy hỗ trợ", "điểm mua rủi ro thấp", "high rr setup", "tìm kèo r:r cao", "đối chiếu học hỏi", "so sánh hôm qua", "cải tiến kèo r:r", "review danh mục r:r", "so sánh kèo cũ".
---

# Kỹ năng Quét Cơ hội Giao dịch Tỷ lệ R:R Thực chiến V2.1 (High Risk:Reward Setup Scanner)

Kỹ năng này chuẩn hóa quy trình tìm kiếm các điểm mua **bất đối xứng (Asymmetric Risk:Reward)** theo triết lý **Lợi nhuận Tuyệt đối (Absolute Return)** kết hợp **Wyckoff & VPA**. Loại bỏ hoàn toàn tư duy "bắt dao rơi" (catching a falling knife) và bơm phồng tỷ lệ R:R ảo.

---

## 1. 6 Trụ cột Định lượng Thực chiến (Quantitative Pillars)

1. **Bộ lọc Thanh khoản Tuyệt đối cho Dòng vốn Lớn (ADTV Filter - Chống Trượt Giá):**
   * Không dùng khối lượng cổ phiếu thô (tránh bẫy cổ phiếu thị giá thấp).
   * Đo lường bằng **Giá trị Giao dịch Trung bình 20 phiên (Average Daily Trading Value - $ADTV_{20}$)** (đã lọc các phiên trần/sàn kẹt vol):
     $$ADTV_{20} = \frac{SMA20_{Volume} \times Price_{VND}}{10^9} \ge 15.0 \text{ tỷ VNĐ/phiên}$$
   * Đảm bảo tính thanh khoản tuyệt đối cho các vị thế vốn lớn, có thể giải ngân hoặc cắt lỗ mà không gây trượt giá (slippage) nghiêm trọng.

2. **Bộ lọc Xu hướng Động (Dynamic Trend Filter - Không Bắt Dao Rơi):**
   * Chỉ chọn cổ phiếu có $Price \ge SMA_{50} \times 0.965$ (đang trong Uptrend hoặc tích lũy lành mạnh trên/sát đường xu hướng trung hạn).
   * **Độ dốc Động $SMA_{50}$ (5 phiên):** $Slope_{5D} \ge -1.0\%$ nhằm loại bỏ dứt điểm các mã có đường xu hướng trung hạn đang cắm dốc đứng.

3. **Cơ chế Phân loại Kép & Mật độ Hỗ trợ (Dual Archetypes & Support Density):**
   * **Kịch bản A: NỀN HỖ TRỢ (Range Rebound / Wyckoff LPS - Spring):**
     - Dành cho cổ phiếu tích lũy sát hỗ trợ: $\text{Support} = \min(Low_{-16:-1})$ (Đáy 15 phiên trước).
     - **Nếu $Price < Support \rightarrow$ LOẠI BỎ NGAY** (Không nới lỏng hỗ trợ).
     - **Đánh giá Mật độ Hỗ trợ (Support Density):** $\text{Density} = count(Low_{-41:-1} \in [\text{Support} \pm 1.5\%])$.
       - Nếu $\text{Density} < 2 \rightarrow$ Gắn tag `[WEAK_SUPPORT]`, tăng ATR buffer lên $1.2 \times ATR_{14}$ để chống quét râu nến, R:R thực tế giảm.
       - Nếu $\text{Density} \ge 3 \rightarrow$ Gắn tag `[STRONG_SUPPORT]`, giữ buffer $1.0 \times ATR_{14}$.
     - $\text{Stop Loss} = \text{Support} - (\text{buffer} \times ATR_{14})$ (Mức chịu rủi ro $\le 6.5\%$).
     - $\text{Target 1 (Close Peak)} = \max(Close_{40D})$, $\text{Target 2 (High Peak)} = \max(High_{40D})$.
   * **Kịch bản B: VƯỢT ĐỈNH NỀN GIÁ (Base Breakout / VCP Pivot):**
     - Dành cho siêu cổ phiếu dẫn dắt đang bứt phá đỉnh 40 phiên: $Price \ge \max(Close_{-41:-1}) \times 0.985$.
     - $\text{Pivot} = \max(Close_{-41:-1})$, $\text{Base Depth} = \text{Pivot} - \min(Low_{-41:-1})$ (Loại trừ nến hiện tại để tránh phồng base).
     - **Lọc Upthrust / False Breakout tại đỉnh:** Nếu $Close\_Position \le 30\%$ và $RVol \ge 1.2 \rightarrow$ LOẠI BỎ NGAY (Bứt phá xịt).
     - **Target Validity:** Nếu $\text{Base Depth} < 1.5 \times ATR_{14} \rightarrow$ LOẠI BỎ (Nền giá quá nông, measured move không tin cậy).
     - **Cắt lỗ Chặt Chẽ theo Nguyên lý False Breakout:**
       $$\mathbf{\text{Stop Loss} = \text{Pivot} - (1.0 \times ATR_{14})}$$
       (Có đệm chống nhiễu $0.8 \times ATR$ cho điểm mua tiệm cận Pivot).
     - **Mục tiêu theo Độ cao Nền (Measured Move):**
       - $\text{Target 1} = Price + (0.8 \times \text{Base Depth})$
       - $\text{Target 2 (Fib 1.3/1.618)} = Price + (1.3 \times \text{Base Depth})$
       - $R:R_1 \ge 1.8$ đảm bảo tỷ lệ lợi nhuận vượt trội.

4. **Logic VPA Đa phiên Xét Bối Cảnh (Context-Aware VPA):**
   * **Lọc bỏ Bearish VPA:** Loại bỏ các mã xuất hiện tín hiệu xả hoặc cạn cầu nguy hiểm.
   * **Bẫy "No Demand" Đa phiên (Grinding No Demand):** Nhận diện chuỗi 3 phiên giảm liên tiếp với volume cạn dần ($RVol_{3D} < 0.80$) hoặc sau phiên dump mạnh $\rightarrow$ Dán nhãn **"Cảnh báo: Chuỗi giảm cạn vol 3 phiên (Grinding No Demand)"** hoặc **"Cảnh báo: Thiếu cầu trên đà rơi (No Demand)"**, LOẠI BỎ NGAY.
   * **Tránh bẫy nhầm "No Supply" sau đà tăng nóng:** Nếu phiên $T-1$ là nến tăng trần/Buying Climax volume đột biến và phiên $T$ cạn vol đi ngang $\rightarrow$ Dán nhãn chuẩn xác là **"Tạm dừng sau tăng nóng (Inside bar)"**.
   * **No Supply Chuẩn:** Chỉ ghi nhận khi phiên $T-1$ không có áp lực xả đột biến, biên độ nến $T$ co hẹp (Spread hẹp), volume cạn kiệt ($RVol < 0.70$) và giá giữ vững trên nền hỗ trợ.
   * **Stopping Volume / Hấp thụ:** Sau phiên giảm mạnh, nến hiện tại rút chân hoặc đóng cửa nửa trên nền giá ($Close\ Position \ge 50\%$) kèm volume hấp thụ lớn.
   * **Bùng nổ Dòng tiền (SOS):** $Close\ Position \ge 65\%$, $Close_T > Close_{T-1}$, $RVol \ge 1.3$.
   * **Volume Trend 5 phiên:** Đánh giá độ dốc volume để nhận diện `[DRY_UP_ACCUMULATION]` (vol cạn dần khi giữ nền) vs `[HIDDEN_DISTRIBUTION]` (vol phồng to ở cản trên).

5. **Bộ lọc Sức mạnh Tương đối (RS Filter — Loại mã yếu thị trường):**
   * Tính $RS\_Score = 0.6 \times RS_{20D} + 0.4 \times RS_{5D}$ so sánh hiệu suất với VNINDEX (tích hợp inline trong scanner).
   * **Nếu $RS\_Score < -5.0\% \rightarrow$ LOẠI BỎ NGAY** (Kèo R:R đẹp trên biểu đồ nhưng cổ phiếu yếu hơn thị trường chung thường là bẫy giảm giá).
   * Nếu $RS\_Score \ge 0 \rightarrow$ Ưu tiên cộng điểm trong bảng xếp hạng Composite Score (cổ phiếu Outperform).

6. **Spring Wash-out Guard & Trailing Stop (Chống bán đáy & Khóa lời):**
   * **Spring Wash-out Guard (Siết chặt 5 điều kiện):**
     Kích hoạt KHI VÀ CHỈ KHI thỏa mãn ĐỒNG THỜI cả 5 điều kiện:
     1. $Low_T < Stop\_Loss$ trong phiên (Giá nhúng thủng SL)
     2. $Close\_Position \ge 70\%$ (Rút chân đóng cửa mạnh mẽ nửa trên)
     3. $Spread\_pct \ge median(Spread_{20D})$ (Biên độ nến đủ rộng, không phải doji nhỏ)
     4. $RVol \ge 1.00$ (Có dòng tiền hấp thụ thực tế)
     5. KHÔNG PHẢI đang giảm liên tục 3 phiên trước ($Close_T < Close_{T-1}$)
     $\rightarrow$ Gắn tag `[SPRING_TEST]`, **KHÔNG cắt lỗ hoảng loạn ngay**.
     $\rightarrow$ Phiên $T+1$: Nếu $Close_{T+1} > Close_T \rightarrow$ Spring xác nhận, **DUY TRÌ vị thế**.
     $\rightarrow$ Phiên $T+1$: Nếu $Close_{T+1} < Low_T \rightarrow$ Spring thất bại, **CẮT LỖ KỶ LUẬT NGAY** tại giá mở cửa $Open_{T+2}$.
   * **Trailing Stop Rules (Quy tắc Duy nhất - Single Source of Truth):**
     - **Giai đoạn 1 (Vào lệnh $\rightarrow$ Target 1 hoặc lãi $\ge 5\%$):** Giữ nguyên Stop Loss ban đầu (theo ATR). Tuyệt đối không dịch chuyển sớm.
     - **Giai đoạn 2 (Sau khi chạm Target 1 hoặc lãi $\ge 5\%$):**
       $$\mathbf{Operative\_SL = \max(Entry\_Price, \min(Low_{-3:-1}))}$$
       (Tự động nâng SL lên mức cao hơn giữa giá vốn Breakeven và đáy swing 3 phiên gần nhất $\rightarrow$ Đảm bảo không bao giờ biến lệnh thắng thành lệnh lỗ).
     - **Giai đoạn 3 (Sau khi chạm Target 2):** Chốt lời 100% vị thế còn lại.

---

## 2. Quy trình Thực thi Chuẩn (SOP - 4+1 Bước)

### Bước 1: Quét Lọc Định lượng qua Local MCP
Gọi công cụ `scan_high_rr_setups(min_rr=1.8, max_risk_pct=6.5, min_avg_val_bil=15.0)` từ `vnstock` MCP:
* Tự động quét và phân loại toàn bộ cổ phiếu theo 2 kịch bản (Nền Hỗ trợ vs. Vượt đỉnh).
* Tự động lọc thanh khoản $ADTV_{20} \ge 15$ tỷ VNĐ/phiên, lọc phiên trần/sàn.
* Tự động loại bỏ mã $RS\_Score < -5.0\%$, lọc VPA tiêu cực (Grinding No Demand, Upthrust, No Demand).
* Trả về bảng xếp hạng theo **Composite Score** cân bằng:
  $$\text{Composite} = 0.35 \times \text{R:R}_1 + 0.25 \times \text{VPA} + 0.20 \times \text{RS} + 0.10 \times \text{SupportDensity} + 0.10 \times \text{ADTV}$$

### Bước 2: Thẩm định Dòng tiền Tổ chức (Smart Money Flow)
Đối với các mã lọt Top:
1. Gọi `get_market_depth_and_foreign(symbol)` để kiểm tra động thái Khối ngoại (gom ròng hay bán ròng).
2. Gọi `get_historical_candles(symbol, count=15)` để kiểm tra cấu trúc nến VPA 3 phiên gần nhất.

### Bước 2.5: Cross-check Flow Engine (MCDX Radar — Bắt Buộc Chuẩn Hóa Thang Đo)
Gọi `scan_mcdx_radar(symbols=[top_candidates], mode="both")` từ `vnstock` MCP:
* **Quy tắc Thang Đo MCDX 24HMoney (Thang 0–20):**
  - Tỷ lệ Banker/Tạo lập (%) = $\text{Red} / 20 \times 100\%$.
  - $\text{Red} > 5.0$ ($> 25\%$): Giai đoạn Gom hàng (Accumulation) / Emerging Flow.
  - $\text{Red} > 10.0$ ($> 50\%$): Giai đoạn Đẩy giá (Markup) / Established Flow.
  - $\text{Red} > 15.0$ ($> 75\%$): Giai đoạn Tạo lập kiểm soát tuyệt đối (Banker Control / Parabolic Phase).
* **Quy tắc Gán Tag Flow:**
  - Nếu $\text{Red} > 5.0$ (tức $> 25\%$ hoặc $flow\_trend \ge 25$) $\rightarrow$ BẮT BUỘC gắn tag `[FLOW_CONFIRMED]` (Dòng tiền tạo lập hiện diện).
  - CẤM TUYỆT ĐỐI gắn `[NO_FLOW]` cho cổ phiếu có $\text{Red} > 5.0$ (đặc biệt khi $\text{Red} > 15.0$ như MSB ~ 79.7% kiểm soát tạo lập).
  - Chỉ gắn tag `[NO_FLOW]` khi $\text{Red} \le 5.0$ ($\le 25\%$) và chưa xuất hiện tín hiệu Flow Turn / Gom bí mật.

### Bước 3: Lập Báo cáo Kế hoạch Vào lệnh (Absolute Return Plan V2.1)
Trình bày rõ ràng kịch bản giao dịch theo từng phân loại setup, tỷ trọng giải ngân, kế hoạch chốt lời và trailing stop 3 giai đoạn theo Mẫu Báo cáo Chuẩn V2.1. Đảm bảo Target 1 đồng nhất tuyệt đối giữa Bảng Xếp hạng, Kế hoạch Vào lệnh và Bảng Tracking.

### Bước 4: So sánh Đối chiếu Đa phiên & Học hỏi (Multi-Day Tracking & Refinement)
*(Kích hoạt khi người dùng yêu cầu đối chiếu hoặc qua triggers: "đối chiếu học hỏi", "so sánh hôm qua", "review danh mục r:r", "so sánh kèo cũ")*
* Tra cứu ngược dữ liệu lịch sử qua `get_historical_candles(symbol, count=5)` cho các mã đã khuyến nghị:
  - So sánh giá đóng cửa phiên sau vs. Stop Loss đã đặt $\rightarrow$ Có vi phạm?
  - So sánh giá cao nhất kể từ khuyến nghị vs. Target 1, Target 2 $\rightarrow$ Đã chạm?
  - So sánh giá thấp nhất vs. SL $\rightarrow$ Có nhúng thủng rồi rút chân Spring?
* Phân loại trạng thái chuẩn:
  - `[ĐẠT TARGET 1]`: $\max(High) \ge Target_1 \rightarrow$ Chốt 50%, nâng SL lên Breakeven.
  - `[ĐẠT TARGET 2]`: $\max(High) \ge Target_2 \rightarrow$ Chốt 100%.
  - `[ĐANG GIỮ — AN TOÀN]`: $\min(Low) > SL$ và chưa chạm Target $\rightarrow$ Tiếp tục nắm giữ.
  - `[RÚT CHÂN SPRING]`: $\min(Low) < SL$ nhưng đóng cửa nến $> SL \rightarrow$ Kích hoạt Spring Guard.
  - `[VI PHẠM SL — CẮT LỖ]`: Đóng cửa bất kỳ phiên $\le SL \rightarrow$ Cắt lỗ kỷ luật, ghi nhận -1.0R.
* Tính toán các chỉ số học hỏi: $\text{Win Rate}$, $\text{Avg Realized R}$, $\text{Spring Save Rate}$, $\text{False Signal Rate}$.

### Bước 5: Đúc kết Bài học Thực chiến (Continuous Refinement)
Tổng hợp 3 bài học then chốt từ thực tế thị trường: (1) Nhịp rũ bỏ Spring Wash-out, (2) Sự dịch chuyển của dòng tiền tạo lập giữa các ngành, (3) Bẫy vượt đỉnh xịt / False Breakout.

---

## 3. Mẫu Báo cáo Đầu ra Chuẩn V2.0 (Report Template)

```markdown
# Báo cáo Cơ hội Giao dịch Tỷ lệ R:R Thực chiến V2.0 (Absolute Return Model)

*(Lưu ý Hệ thống: Mô hình mang tính chất heuristic. Tín hiệu R:R là ước lượng dựa trên dữ liệu lịch sử, không phải bảo đảm lợi nhuận. Luôn tuân thủ kỷ luật cắt lỗ ATR.)*

## 1. Bảng Xếp hạng Kèo R:R Thực tế (Dòng Vốn Lớn)
| Top | Mã | Phân loại | Giá | SL (ATR) | T1 | T2 | Risk% | R:R₁ | R:R₂ | ADTV₂₀ | VPA Tag | RS Score | Flow Tag | Composite |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | ... | Nền / Vượt đỉnh | ... | ... | ... | ... | ...% | 1:... | 1:... | ...tỷ | ... | +...% | [FLOW_CONFIRMED] | ... |

## 2. Bảng So sánh Đối chiếu Thực chiến Đa phiên (Tracking Table)
*(Chỉ xuất hiện khi user yêu cầu đối chiếu hoặc khi có dữ liệu phiên trước)*

| Mã | Ngày KN | Giá KN | SL | T1 | Giá Hiện tại | Trạng thái | Lãi/Lỗ (%) | Realized R |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ... | 25/09 | ... | ... | ... | ... | [ĐẠT TARGET 1] | +...% | +...R |
| ... | 23/09 | ... | ... | ... | ... | [VI PHẠM SL] | -...% | -1.0R |

**Tỷ lệ thắng (Win Rate):** .../... = ...%  |  **Avg R:** +...R  |  **Spring Save Rate:** ...%

## 3. Đúc kết Bài học & Tinh chỉnh Thực chiến (Continuous Refinement)
1. **Bài học 1:** [Ví dụ: "DGW nhúng SL rồi rút chân Spring — Spring Guard cứu vị thế thành công"]
2. **Bài học 2:** [Ví dụ: "Ngành Bất động sản dòng tiền dịch chuyển mạnh — ưu tiên quét nhóm dẫn dắt"]
3. **Bài học 3:** [Ví dụ: "Mã có RS < -5% liên tục vi phạm SL — siết chặt bộ lọc RS Filter"]

## 4. Phân tích Chi tiết & Kế hoạch Vào lệnh cho Top Cơ hội Hàng đầu
### 🎯 1. Mã [SYMBOL] — [Phân loại Setup]
- **Vị thế Kỹ thuật & Bối cảnh:** ...
- **Support Density:** ... touch / 40 phiên $\rightarrow$ [STRONG_SUPPORT / WEAK_SUPPORT / BREAKOUT_PIVOT]
- **RS Score:** ...% (Outperforming / Underperforming VNINDEX)
- **Bối cảnh VPA Đa phiên:** [No Supply chuẩn / SOS / Stopping Volume...]
- **Flow Cross-check:** [FLOW_CONFIRMED / NO_FLOW / Không kiểm tra]
- **Thanh khoản Dòng vốn Lớn:** $ADTV_{20} = ...$ tỷ VNĐ/phiên
- **Quản trị Rủi ro (ATR Stop Loss):**
  - Operative SL: ... ($ATR_{14} = ...$, Buffer = ...×)
  - Spring Wash-out Guard: [ACTIVE / SẴN SÀNG]
- **Kịch bản Chốt lời & Trailing Stop 3 Giai đoạn:**
  - **Giai đoạn 1 (Vào lệnh):** Đặt SL tại ...
  - **Giai đoạn 2 (Chốt 50% tại Target 1 = ...):** Nâng SL lên $\max(Entry, \min(Low_{-3:-1})) = ...$
  - **Giai đoạn 3 (Chốt 50% còn lại tại Target 2 = ...):** Chốt toàn bộ vị thế.
- **Xác nhận Dòng tiền Khối ngoại:** ...

## 5. Cảnh báo Kỷ luật Giao dịch
- Tuyệt đối không dời Stop Loss khi giá vi phạm ngưỡng cắt lỗ ATR (trừ trường hợp Spring Wash-out Guard kích hoạt).
- Khi giá chạm Target 1, trailing stop tự động nâng lên theo quy tắc Giai đoạn 2.
- Mã chưa có dòng tiền tạo lập xác nhận (`[NO_FLOW]`) bắt buộc giảm sizing 50% so với thông thường.
- *Báo cáo này mang tính chất tham khảo. Mọi quyết định đầu tư là của cá nhân nhà đầu tư. Luôn tuân thủ kỷ luật cắt lỗ.*
```

---

## 4. Quy Tắc Bắt Buộc Dành Cho AI Agent (LLM Governance)

1. **Cấm Từ Ngữ Thổi Phồng:** Tuyệt đối cấm các từ ngữ *"bảo kê", "chắc thắng", "siêu cổ", "tuyệt đối"* nhằm bảo đảm tính khách quan định lượng.
2. **Luật Support Yếu (`[WEAK_SUPPORT]`):** Nếu nến tích lũy có độ dày $< 2$ touch trong 40 phiên, bắt buộc ghi rõ: *"Vùng hỗ trợ mỏng (< 2 touch), SL mở rộng 1.2×ATR, R:R thực tế giảm"*.
3. **Luật Spring Wash-out Guard:** Khi nến nhúng thủng SL nhưng rút chân thỏa mãn 5 điều kiện, bắt buộc ghi: *"Spring Test — quan sát phiên T+1, chưa cắt lỗ vội"*. Nếu phiên T+1 đóng nến thủng đáy nến Spring, bắt buộc ghi: *"Spring thất bại — cắt lỗ kỷ luật ngay tại Open T+2"*.
4. **Luật No Flow (`[NO_FLOW]`):** Đối với mã Top R:R nhưng chưa có dòng tiền tạo lập xác nhận qua MCDX Radar ($\text{Red} \le 5.0$), bắt buộc ghi: *"Chưa có dòng tiền tạo lập xác nhận, giảm sizing khuyến nghị 50%"*.
5. **Quy tắc Giải phẫu Nến & VPA:**
   - **Marubozu:** Chỉ dùng khi nến có thân đặc chiếm $\ge 90\%$ biên độ (râu trên và râu dưới $< 10\%$). Nến có râu dưới rõ rệt (ví dụ râu dưới chiếm $\ge 20\%$ biên độ như HAH) tuyệt đối không được gọi là Marubozu mà phải gọi là Hammer / Nến rút chân.
   - **No Supply:** Bắt buộc phải là nến Giảm hoặc Đi ngang ($Close \le Close_{prev}$) kèm volume cạn kiệt dưới 2 phiên trước và dưới MA20. Cấm tuyệt đối gọi nến Tăng ($Close > Close_{prev}$) là "No Supply".
6. **Cảnh báo Quá mua RSI:** Khi $RSI \ge 70$, bắt buộc phải công bố cảnh báo quá mua và rủi ro rung lắc, không khuyến nghị fomo mua đuổi Breakout tại cựu đỉnh.
7. **Tính Nhất Quán của Target 1 & R:R:**
   - Target 1 của cùng một mã phải đồng nhất giữa Bảng xếp hạng, Bảng tracking và Kế hoạch chi tiết.
   - R:R bắt buộc tính theo khoảng cách giá thực tế $\frac{Target - Entry}{Entry - SL}$, cấm chia 2 số phần trăm đã làm tròn dẫn đến sai số.
8. **Đơn vị Đo lường Khối lượng:** Phân biệt rõ giữa Khối lượng cổ phiếu giao dịch (Shares / triệu CP) và Giá trị giao dịch khớp lệnh ($ADTV = Shares \times Price$, tính bằng tỷ VNĐ).
9. **Disclaimer Bắt Buộc:** Mọi báo cáo phải kết thúc bằng tuyên bố miễn trừ trách nhiệm chuẩn: *"Báo cáo này mang tính chất tham khảo. Mọi quyết định đầu tư là của cá nhân nhà đầu tư. Luôn tuân thủ kỷ luật cắt lỗ."*
