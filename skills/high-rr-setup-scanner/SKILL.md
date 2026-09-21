---
name: high-rr-setup-scanner
description: >-
  Tự động quét và xếp hạng các cơ hội giao dịch có tỷ lệ Lợi nhuận / Rủi ro (Risk : Reward - R:R)
  thực tế cao nhất thị trường Việt Nam dựa trên nguyên tắc Lợi nhuận Tuyệt đối (Absolute Return).
  Tích hợp bộ lọc Xu hướng (Trend Filter > SMA50), Stop Loss động theo ATR_14 (chống Stop-hunt),
  Mục tiêu thực tế (Target 1 theo giá đóng cửa & Target 2 theo đỉnh Trading Range), và logic VPA chuyên sâu.
  Triggers: "cổ phiếu đáng mua nhất", "tỷ lệ r:r cao", "kèo ngon r:r", "mua sát đáy hỗ trợ", "điểm mua rủi ro thấp", "high rr setup", "tìm kèo r:r cao".
---

# Kỹ năng Quét Cơ hội Giao dịch Tỷ lệ R:R Thực chiến (High Risk:Reward Setup Scanner)

Kỹ năng này chuẩn hóa quy trình tìm kiếm các điểm mua **bất đối xứng (Asymmetric Risk:Reward)** theo triết lý **Lợi nhuận Tuyệt đối (Absolute Return)** kết hợp **Wyckoff & VPA**. Loại bỏ hoàn toàn tư duy "bắt dao rơi" (catching a falling knife) và bơm phồng tỷ lệ R:R ảo.

---

## 1. 5 Trụ cột Định lượng Thực chiến (Quantitative Pillars)

1. **Bộ lọc Thanh khoản Tuyệt đối cho Dòng vốn Lớn (ADTV Filter - Chống Trượt Giá):**
   * Không dùng khối lượng cổ phiếu thô (tránh bẫy cổ phiếu thị giá thấp).
   * Đo lường bằng **Giá trị Giao dịch Trung bình 20 phiên (Average Daily Trading Value - $ADTV_{20}$)**:
     $$ADTV_{20} = \frac{SMA20_{Volume} \times Price_{VND}}{10^9} \ge 15.0 \text{ tỷ VNĐ/phiên}$$
   * Đảm bảo tính thanh khoản tuyệt đối cho các vị thế vốn lớn, có thể giải ngân hoặc cắt lỗ mà không gây trượt giá (slippage) nghiêm trọng.

2. **Bộ lọc Xu hướng Động (Dynamic Trend Filter - Không Bắt Dao Rơi):**
   * Chỉ chọn cổ phiếu có $Price \ge SMA_{50} \times 0.965$ (đang trong Uptrend hoặc tích lũy lành mạnh trên/sát đường xu hướng trung hạn).
   * **Độ dốc Động $SMA_{50}$ (5 phiên):** $Slope_{5D} \ge -1.0\%$ nhằm loại bỏ dứt điểm các mã có đường xu hướng trung hạn đang cắm dốc đứng.

3. **Cơ chế Phân loại Kép (Dual Setup Archetypes - Mua Nền vs. Vượt Đỉnh):**
   * **Kịch bản A: NỀN HỖ TRỢ (Range Rebound / Wyckoff LPS - Spring):**
     - Dành cho cổ phiếu tích lũy sát hỗ trợ: $\text{Support} = \min(Low_{-16:-1})$ (Đáy 15 phiên trước).
     - **Nếu $Price < Support \rightarrow$ LOẠI BỎ NGAY** (Không nới lỏng hỗ trợ).
     - $\text{Stop Loss} = \text{Support} - (1.0 \times ATR_{14})$ (Mức chịu rủi ro $\le 6.5\%$).
     - $\text{Target 1 (Close Peak)} = \max(Close_{40D})$, $\text{Target 2 (High Peak)} = \max(High_{40D})$.
   * **Kịch bản B: VƯỢT ĐỈNH NỀN GIÁ (Base Breakout / VCP Pivot):**
     - Dành cho siêu cổ phiếu dẫn dắt đang bứt phá đỉnh 40 phiên: $Price \ge \max(Close_{-41:-1}) \times 0.985$.
     - $\text{Pivot} = \max(Close_{-41:-1})$, $\text{Base Depth} = \text{Pivot} - \min(Low_{40D})$.
     - **Cắt lỗ Chặt Chẽ theo Nguyên lý False Breakout:**
       $$\mathbf{\text{Stop Loss} = \text{Pivot} - (1.0 \times ATR_{14})}$$
       (Tuyệt đối không dùng `min` với đáy 5 phiên vì sẽ bị nới lỏng SL về đáy tay cầm sâu, bóp nghẹt R:R. Nếu giá bứt phá xong mà chui ngược xuống dưới Pivot quá $1.0 \times ATR$, đây là bứt phá xịt/Upthrust và phải cắt ngay). Có đệm chống nhiễu $0.8 \times ATR$ cho điểm mua tiệm cận Pivot.
     - **Mục tiêu theo Độ cao Nền (Measured Move):**
       - $\text{Target 1} = Price + (0.8 \times \text{Base Depth})$
       - $\text{Target 2 (Fib 1.3/1.618)} = Price + (1.3 \times \text{Base Depth})$
       - $R:R_1 \ge 1.8$ đảm bảo tỷ lệ lợi nhuận vượt trội.

4. **Logic VPA Đa phiên Xét Bối Cảnh (Context-Aware VPA):**
   * **Tránh bẫy "No Demand" (Thiếu cầu nguy hiểm):** Nếu phiên $T-1$ là nến xả hoảng loạn (Marubozu/biên độ giảm rộng kèm vol lớn) và phiên $T$ giá tiếp tục trôi với volume thấp $\rightarrow$ Dán nhãn **"Cảnh báo: Thiếu cầu trên đà rơi (No Demand)"**, tuyệt đối không ngộ nhận là cạn cung.
   * **Tránh bẫy nhầm "No Supply" sau đà tăng nóng:** Nếu phiên $T-1$ là nến tăng trần/Buying Climax volume đột biến và phiên $T$ cạn vol đi ngang $\rightarrow$ Dán nhãn chuẩn xác là **"Tạm dừng sau tăng nóng (Inside bar)"**.
   * **No Supply Chuẩn:** Chỉ ghi nhận khi phiên $T-1$ không có áp lực xả đột biến, biên độ nến $T$ co hẹp (Spread hẹp), volume cạn kiệt ($RVol < 0.70$) và giá giữ vững trên nền hỗ trợ.
   * **Stopping Volume / Hấp thụ:** Sau phiên giảm mạnh, nến hiện tại rút chân hoặc đóng cửa nửa trên nền giá ($Close\ Position \ge 50\%$) kèm volume hấp thụ.
   * **Bùng nổ Dòng tiền (SOS):** $Close\ Position \ge 65\%$, $Close_T > Close_{T-1}$, $RVol \ge 1.3$.

---

## 2. Quy trình Thực thi Chuẩn (SOP - 3 Bước)

### Bước 1: Quét Lọc Định lượng Thực tế qua Local MCP
Gọi công cụ `scan_high_rr_setups(min_rr=1.8, max_risk_pct=6.5, min_avg_val_bil=15.0)` từ `vnstock` MCP:
* Tự động quét và phân loại toàn bộ cổ phiếu theo 2 kịch bản (Nền Hỗ trợ vs. Vượt đỉnh).
* Tự động lọc các mã không đạt thanh khoản 15 tỷ VNĐ/ngày.
* Trả về bảng kết quả chi tiết $SL, Target_1, Target_2, R:R_1, R:R_2$ và nhãn VPA bối cảnh.

### Bước 2: Thẩm định Dòng tiền Tổ chức (Smart Money Flow)
Đối với các mã lọt Top:
1. Gọi `get_market_depth_and_foreign(symbol)` để kiểm tra động thái Khối ngoại (ưu tiên mã được gom ròng hoặc ngừng bán ròng).
2. Gọi `get_historical_candles(symbol, count=15)` để kiểm tra cấu trúc nến VPA 3 phiên gần nhất.

### Bước 3: Lập Báo cáo Kế hoạch Vào lệnh (Absolute Return Plan)
Trình bày rõ ràng kịch bản giao dịch theo từng phân loại setup, tỷ trọng giải ngân và kế hoạch chốt lời 2 giai đoạn.

---

## 3. Mẫu Báo cáo Đầu ra Chuẩn (Report Template)

```markdown
# Báo cáo Cơ hội Giao dịch Tỷ lệ R:R Thực chiến (Absolute Return Model)

## 1. Bảng Xếp hạng Kèo R:R Thực tế (Dòng Vốn Lớn)
| Top | Mã | Phân loại Setup | Giá hiện tại | SL theo ATR | Target 1 | Target 2 | Risk (%) | R:R_1 | R:R_2 | ADTV (20P) | Bối cảnh VPA |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 | ... | Vượt đỉnh / Nền hỗ trợ | ... | ... | ... | ... | ...% | 1 : ... | 1 : ... | ... tỷ/phiên | No Supply chuẩn / SOS... |
| 2 | ... | ... | ... | ... | ... | ... | ...% | 1 : ... | 1 : ... | ... tỷ/phiên | ... |

## 2. Phân tích Chi tiết Kế hoạch Vào lệnh cho Top Cơ hội Hàng đầu
### 🎯 1. Mã [SYMBOL_1] - [Phân loại Setup]
- **Vị thế Kỹ thuật & Bối cảnh:** Đang [Vượt đỉnh VCP / Tích lũy sát nền], cách hỗ trợ/pivot ...%.
- **Thanh khoản Dòng vốn Lớn:** $ADTV_{20} = ...$ tỷ VNĐ/phiên (Khả năng hấp thụ lệnh lớn tốt).
- **Quản trị Rủi ro (ATR Stop Loss):** $ATR_{14} = ... \rightarrow$ Đặt SL tại ... (Mức chịu rủi ro: ...%).
- **Kịch bản Chốt lời Đa tầng:**
  - **Chốt lời 1 (50% vị thế):** Giá ... (Lợi nhuận: ...% | $R:R = 1 : ...$).
  - **Chốt lời 2 (50% còn lại):** Giá ... (Lợi nhuận: ...% | $R:R = 1 : ...$).
- **Xác nhận Dòng tiền Khối ngoại & VPA Đa phiên:** ...

## 3. Cảnh báo Kỷ luật Giao dịch
- Tuyệt đối không dời Stop Loss khi giá vi phạm ngưỡng cắt lỗ ATR.
- Khi giá chạm Target 1, tự động nâng Stop Loss lên giá vốn (Breakeven).
```
