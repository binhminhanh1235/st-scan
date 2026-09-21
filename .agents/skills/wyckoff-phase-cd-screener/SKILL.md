---
name: wyckoff-phase-cd-screener
description: >-
  Tự động quét và nhận diện các cơ hội giải ngân rủi ro cực thấp theo phương pháp Wyckoff (V7.0)
  tại Pha C (Test of Spring / Terminal Shakeout) và Pha D (BU / LPS - Last Point of Support).
  Tích hợp kiểm định Stationarity hộp TR, chống nhiễu Minor SOS (%CP >= 66%), gắn cờ Regime Counter-Trend,
  chiết khấu Target 2 theo Supply Zone và kế hoạch giải ngân đa tầng (Tranche Scaling 2 giai đoạn).
  Triggers: "quét pha c d", "wyckoff pha c", "wyckoff pha d", "tìm điểm mua lps", "test spring",
  "kèo pha c", "kèo lps", "wyckoff phase c d", "điểm mua đón lõng".
---

# Kỹ Năng Quét Điểm Mua Wyckoff Pha C & D (Wyckoff Phase C/D Screener V7.0)

Kỹ năng này chuyên biệt hóa việc tìm kiếm và phân loại các cơ hội giải ngân **Đón Lõng (Anticipatory Quantitative Model)** rủi ro thấp nhất theo phương pháp Wyckoff nguyên bản, chuyển đổi từ "dự báo danh nghĩa" sang "dự báo có kiểm soát rủi ro" qua quản lý trạng thái, chiết khấu mục tiêu và giải ngân đa tầng.

---

## 1. 5 Trụ Cột Định Lượng Thực Chiến (Quantitative Pillars V7.0)

### 1. Bộ lọc Thanh khoản Dòng Vốn Lớn (ADTV Filter)
* **Giá trị Giao dịch Trung bình 20 phiên:**
  $$ADTV_{20} = \frac{SMA20_{\text{Volume}} \times \text{Price}_{\text{VND}}}{10^6} \ge 15.0 \text{ tỷ VNĐ/phiên}$$
* Khối lượng tối thiểu $SMA20_{\text{Vol}} \ge 200,000$ cp/phiên. Loại bỏ hoàn toàn nguy cơ trượt giá (slippage).

### 2. Bản vá 1: Chống nhiễu Minor SOS & Gắn cờ Regime (Counter-trend)
* **Siết điều kiện Minor SOS (Pha D):** Nến bứt phá qua $TR\_Mid$ với $RVol \ge 1.25$ phải có giá đóng cửa nằm ở $1/3$ trên biên độ:
  $$\frac{Close - Low}{High - Low} \ge 0.66 \quad (\%CP \ge 66\%)$$
  Loại bỏ triệt để nến râu trên dài (Shooting Star / Upthrust giả mạo).
* **Gắn cờ Regime (Xu hướng đỉnh lớn):**
  $$Peak_{Old} = \max(High_{-120:-60}), \quad Peak_{New} = \max(High_{-60:-20})$$
  Nếu $Peak_{New} < Peak_{Old} \times 0.95 \rightarrow$ Thị trường đang trong xu hướng giảm (Lower Highs).
  * Gắn tag `[Counter-Trend]` vào `setup_type`.
  * Điều chỉnh `position_sizing`: **Giảm 50% quy mô (Half-size)**. Ngược lại là **Full-size**.

### 3. Bản vá 2: Đóng băng Snapshot Hộp TR (Kiểm định Stationarity 3 Khung)
* Tính $TR\_High$ trên 3 rolling windows:
  * $TR_{Primary}: [-90:-20]$
  * $TR_{Shift1}: [-100:-25]$
  * $TR_{Shift2}: [-80:-15]$
* Nếu $TR\_High$ của $TR_{Primary}$ lệch quá $5\%$ so với $TR_{Shift1}$ hoặc $TR_{Shift2} \rightarrow$ Kích hoạt `is_box_unstable = True`:
  * Gắn tag `[Box Unstable]` vào `setup_type`.
  * **Cấm in Target 2 dài hạn:** Gán $Target_2 = \text{None}$, $Reward_{2\%} = \text{None}$, $RR_2 = \text{None}$.

### 4. Bản vá 3: Chiết khấu Target 2 theo Kháng cự Vùng Cung (Supply Zone)
* Xác định Vùng Cung lớn nhất lịch sử 130 phiên: $Major\_Supply = \max(High_{-130:-1})$.
* $Target_{2\_Raw} = TR\_High + (TR\_High - TR\_Low) \times 0.5$.
* Nếu $Target_{2\_Raw} \ge Major\_Supply \times 0.97 \rightarrow$ Ép lùi mục tiêu về sát dưới Vùng Cung:
  $$Target_2 = \text{round}(Major\_Supply \times 0.98, 2)$$
  Kèm ghi chú `target_2_note = "Bị giới hạn bởi Supply Zone cũ"`.

### 5. Bản vá 4: Cấu trúc Giải ngân Đa tầng (Tranche Scaling 2 Giai đoạn)
* **Tranche 1 (Thăm dò Anticipatory):** Mua tại $Price_{current}$ với Stop Loss động theo ATR ($0.8 \times ATR_{14}$).
* **Tranche 2 (Gia tăng Confirmatory):** Kích hoạt khi giá đóng cửa vượt $TR\_High$ (Pha D) hoặc $TR\_Mid$ (Pha C). Stop Loss toàn bộ vị thế dời lên $TR\_Mid$ (Pha D) hoặc $event\_low$ (Pha C).

---

## 2. Quy Tắc Bắt Buộc Dành Cho AI Agent (LLM Rules)

> [!CRITICAL]
> 1. **Luật Báo cáo Target 2:** Nếu biến `target_2` trả về `null` hoặc cờ `[Box Unstable]` xuất hiện, AI **tuyệt đối KHÔNG ĐƯỢC tự bịa ra Target 2 hoặc tự tính R:R2**. Bắt buộc ghi rõ: *"Hộp tích lũy không ổn định, hủy bỏ mục tiêu sóng dài"*.
> 2. **Luật Cảnh báo Chế độ (Regime):** Nếu có cờ `[Counter-Trend]`, AI **bắt buộc phải cảnh báo người dùng**: *"Mã này đang đi ngược xu hướng chính (Counter-trend), chỉ giải ngân 50% quy mô (Half-size), ưu tiên đánh ngắn chốt lời tại Target 1 và tuân thủ kỷ luật Tranche 1"*.

---

## 3. Quy Trình Thực Thi Chuẩn (SOP - 3 Bước)

### Bước 1: Quét Lọc Định Lượng Wyckoff Pha C/D V7.0
Gọi công cụ `scan_wyckoff_phase_c_d(min_rr=1.8, max_risk_pct=6.5, min_avg_val_bil=15.0)` từ `vnstock` MCP:
* Tự động kiểm tra Stationarity, lọc Minor SOS chuẩn (%CP >= 66%), gắn cờ Counter-Trend và Box Unstable.
* Nhận các trường Tranche Scaling (`tranche_1_entry`, `tranche_1_sl`, `tranche_2_trigger`, `tranche_2_sl`).

### Bước 2: Thẩm định Dòng Tiền & Vị Thế Khối Ngoại
Với các mã lọt Top:
1. Gọi `get_market_depth_and_foreign(symbol)` để kiểm tra động thái Khối ngoại.
2. Gọi `get_historical_candles(symbol, count=15)` để kiểm tra cấu trúc nến VPA.

### Bước 3: Lập Báo Cáo Kế Hoạch Giải Ngân Đa Tầng
Trình bày báo cáo theo đúng format chuẩn bên dưới.

---

## 4. Mẫu Báo Cáo Đầu Ra Chuẩn (Report Template)

```markdown
# Báo Cáo Cơ Hội Giao Dịch Wyckoff (Anticipatory Quantitative Model)

*(Lưu ý Hệ thống: Setup này là điểm mua dự báo sớm [Anticipatory], chưa phải Pha D kinh điển. Chỉ xác nhận khi phá kháng cự, phủ định khi vi phạm SL).*

## 1. Bảng Xếp Hạng Kèo Đón Lõng (Vốn Lớn > 15 Tỷ/Phiên)
| Mã | Trạng Thái Hộp | Setup (Gắn cờ) | Tỷ Trọng | Giá Entry | Tranche 1 SL | Target 1 | R:R_1 | Target 2 (Note) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| ... | Ổn định / Unstable | LPS [Counter-Trend] | 50% Size | ... | ... | ... | 1 : ... | ... (Limit by Supply) |

## 2. Kế Hoạch Giải Ngân Đa Tầng (Tranche Scaling Plan)
### 🎯 Mã [SYMBOL] 
- **Bối cảnh VPA:** ...
- **TRANCHE 1 (Thăm dò Anticipatory - 50% Vị thế):**
  - Mua tại vùng: `[tranche_1_entry]`
  - Cắt lỗ rủi ro hẹp (ATR): `[tranche_1_sl]`
  - Mục tiêu ngắn (Target 1): `[target_1]`
- **TRANCHE 2 (Gia tăng Confirmatory - 50% Vị thế còn lại):**
  - Điều kiện kích hoạt: Đóng cửa vượt mốc `[tranche_2_trigger]`.
  - Cắt lỗ cấu trúc (Nâng SL toàn bộ lệnh): `[tranche_2_sl]`.
  - Mục tiêu sóng lớn (Target 2): `[target_2]` *(Bỏ qua nếu Hộp Unstable)*.
```
