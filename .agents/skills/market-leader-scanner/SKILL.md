---
name: market-leader-scanner
description: >-
  Tự động quét và xếp hạng các cổ phiếu dẫn dắt (Market Leaders) mạnh nhất thị trường Việt Nam
  dựa trên Sức mạnh giá tương đối (RS Score so với VNINDEX), Khối lượng (RVol), bộ lọc thanh khoản dòng vốn lớn (ADTV >= 10 tỷ VNĐ),
  và dấu chân dòng tiền Smart Money (Khối ngoại).
  Triggers: "tìm cổ phiếu mạnh nhất", "cổ phiếu dẫn dắt", "top rs", "quét leader", "lọc cổ phiếu wyckoff", "market leaders", "top cổ phiếu khỏe".
---

# Kỹ năng Quét Cổ phiếu Dẫn dắt Thị trường (Market Leader Scanner)

Kỹ năng này chuẩn hóa quy trình phát hiện sớm các **Cổ phiếu dẫn dắt (Market Leaders)** trên thị trường chứng khoán Việt Nam, kết hợp thuật toán đo lường sức mạnh tương quan (**Mansfield Relative Strength - RS**) với phương pháp **Wyckoff SOS (Sign of Strength)** và theo vết dòng tiền lớn (Smart Money).

---

## 1. Công thức & Tiêu chí Lọc Định lượng

1. **Thuật toán Chấm điểm Sức mạnh Tương đối (RS Score):**
   $$\text{RS}_{5D} = \% \text{Cổ phiếu}_{5D} - \% \text{VNINDEX}_{5D}$$
   $$\text{RS}_{20D} = \% \text{Cổ phiếu}_{20D} - \% \text{VNINDEX}_{20D}$$
   $$\mathbf{\text{RS Score} = 0.6 \times \text{RS}_{20D} + 0.4 \times \text{RS}_{5D}}$$
   * Trọng số $60\%$ cho 20 ngày: Đảm bảo cổ phiếu duy trì được **Trend tăng trung hạn bền vững**.
   * Trọng số $40\%$ cho 5 ngày: Phản ánh độ nhạy bén và **tín hiệu bứt phá ngắn hạn (SOS / Breakout)**.

2. **Bộ lọc Thanh khoản Dòng vốn Lớn (ADTV Filter - Chống trượt giá):**
   * Giá trị giao dịch bình quân 20 phiên: $\text{ADTV}_{20} = SMA_{20}(\text{Volume}) \times \text{Price} \ge 10 \text{ tỷ VNĐ/phiên}$ (bảo đảm an toàn giải ngân và cắt lỗ cho nhà đầu tư lớn, loại bỏ bẫy cổ phiếu penny/trà đá).
   * Khối lượng tương đối phiên gần nhất: $\text{RVol} = \frac{\text{Volume}}{SMA_{20}(\text{Volume})} \ge 1.0$ (chỉ chọn cổ phiếu có dòng tiền tham gia thực chất).

3. **Xác nhận Dòng tiền Lớn (Smart Money Flow):**
   * Giá trị mua ròng Khối ngoại (Net Foreign) dương trong 10-15 phiên hoặc đột biến trong phiên gần nhất.

---

## 2. Quy trình Thực thi Chuẩn (SOP - 3 Bước)

### Bước 1: Quét Toàn bộ Thị trường qua MCP
Gọi công cụ `scan_market_leaders(top_n=15, min_avg_val_bil=10.0)` từ `vnstock` MCP:
* Tự động quét Dynamic Universe (top 85 cổ phiếu thanh khoản cao và tốt nhất thị trường theo thời gian thực từ SSI iBoard), hoặc quét danh mục tuỳ chọn qua tham số `symbols`.
* Nhận bảng xếp hạng Top 10-15 mã có $\text{RS Score} > 0$ kèm thông tin nhóm ngành (`sector`) và thanh khoản (`avg_val_20d_bil`).

### Bước 2: Soi sâu Top 3-5 Cổ phiếu Dẫn đầu
Đối với 3-5 mã đứng đầu bảng xếp hạng:
1. Gọi `get_market_depth_and_foreign(symbol)` để kiểm tra dòng tiền mua ròng của Khối ngoại và mức độ kê lệnh mua/bán.
2. Gọi `get_historical_candles(symbol, count=20)` để kiểm tra cấu trúc nến VPA (đang vượt đỉnh, đang tích lũy trên cản, hay xuất hiện nến SOS / Test cung).

### Bước 3: Xuất Báo cáo & Lập Kế hoạch Hành động
Phân loại các cổ phiếu Leader thành 2 nhóm:
* **Nhóm 1: Leader Đang Bứt phá (Momentum Breakout):** Đang trong pha tăng mạnh, dòng tiền lớn dồn dập $\rightarrow$ Kế hoạch mua gia tăng hoặc canh nhịp chỉnh nhẹ (LPS / Pullback).
* **Nhóm 2: Leader Đang Tích lũy Nền trên (Base on Base / Absorption):** Giữ nền chặt chẽ khi thị trường điều chỉnh $\rightarrow$ Kế hoạch gom thăm dò trước khi bùng nổ.

---

## 3. Mẫu Báo cáo Đầu ra Chuẩn (Report Template)

```markdown
# Báo cáo Top Cổ phiếu Dẫn dắt Thị trường (Market Leaders)

## 1. Bối cảnh Thị trường Chung (VNINDEX)
- **Điểm số VNINDEX:** ... | **Hiệu suất 5 phiên:** ...% | **Hiệu suất 20 phiên:** ...%
- **Đánh giá trạng thái:** Thị trường đang trong pha [Tăng / Đi ngang tích lũy / Điều chỉnh].

## 2. Bảng Xếp hạng Top Cổ phiếu Mạnh nhất (Leading Board)
| Top | Mã | Ngành | Thị giá | 5D (%) | 20D (%) | RS Score | RVol | ADTV (Tỷ) | Khối ngoại (15D) | Trạng thái Wyckoff / VPA |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 | ... | ... | ... | ... | ... | ... | ... | ... tỷ | Mua ròng ... tỷ | Vượt đỉnh / SOS / Nền trên... |
| 2 | ... | ... | ... | ... | ... | ... | ... | ... tỷ | ... | ... |

## 3. Tiêu điểm Phân tích Top 3 Cổ phiếu Triển vọng nhất
### 1. Mã [LEADER_1]:
- **Điểm mạnh:** ...
- **Dấu chân Smart Money:** ...
- **Kế hoạch hành động:** Vùng mua: ... | Stop Loss: ... | Target: ...

### 2. Mã [LEADER_2]:
...

## 4. Khuyến nghị Phân bổ Danh mục
- **Chiến lược hành động:** Tập trung danh mục vào top 2-3 ngành dẫn dắt.
- **Tỷ trọng tiền/cổ phiếu khuyến nghị:** ...
```
