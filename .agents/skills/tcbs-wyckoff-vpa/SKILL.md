---
name: tcbs-wyckoff-vpa
description: >-
  Phân tích cổ phiếu chuyên sâu kết hợp phương pháp Wyckoff và VPA (Volume Price Analysis)
  sử dụng dữ liệu từ vnstock Local MCP Server (DNSE, 24hMoney) hoặc TCBS. Tự động tính toán Spread,
  Volume trung bình, nhận diện nến tín hiệu VPA (No Supply, No Demand, Stopping Volume, Shakeout, Upthrust),
  xác định Pha Wyckoff (Accumulation, Distribution, Spring, SOS, LPS) và theo vết dòng tiền Smart Money (Khối ngoại, RS Rank).
  Triggers: "phân tích wyckoff", "phân tích vpa", "wyckoff vpa", "tcbs wyckoff", "soi nến vol", "smart money tcbs", "vpa cổ phiếu", "phân tích cổ phiếu".
---

# Kỹ năng Phân tích Cổ phiếu theo Wyckoff & VPA

Kỹ năng này chuẩn hóa quy trình phân tích hành động giá (Price Action) kết hợp khối lượng (Volume) theo phương pháp **Richard Wyckoff** và **VPA (Volume Price Analysis - Anna Coulling / Tom Williams VSA)**, kết nối trực tiếp với **vnstock Local MCP Server** (siêu tốc, miễn phí 100%, tiết kiệm token).

---

## 1. Công cụ Dữ liệu từ Local MCP (`vnstock`)

Local MCP Server đã tính toán sẵn các chỉ số định lượng ở tầng backend, giúp AI tiết kiệm tối đa token ngữ cảnh:

1. **`get_historical_candles(symbol, resolution='1D', count=60)`:**
   - Cung cấp chuỗi nến OHLCV từ nguồn DNSE (hoàn toàn miễn phí, không cần token/API key).
   - Tính sẵn: `spread` (High - Low), `spread_pct` (Biên độ tương đối theo % giá đóng cửa), `close_pos_%` (Vị trí đóng nến trong range), `sma20_vol`, `rvol` (Volume / SMA20), và nhãn sơ bộ `vpa_tag` (chuẩn hóa theo spread tương đối).
2. **`get_market_depth_and_foreign(symbol)`:**
   - Cung cấp giá khớp realtime, sổ lệnh 3 mức giá dư mua/dư bán.
   - Thống kê 15 phiên gần nhất của Khối ngoại: Giá trị mua, bán và **giá trị mua/bán ròng (Tỷ đồng)**.
3. **`get_relative_strength(symbol, count=60)`:**
   - Đo lường sức mạnh giá tương đối (RS) so với **VNINDEX** trong 10, 20, 60 phiên (xác định cổ phiếu Outperforming hay Underperforming).

---

## 2. Quy trình Thực thi Chuẩn (SOP - 4 Bước)

### Bước 1: Thu thập Dữ liệu qua Local MCP
Khi nhận mã cổ phiếu (ví dụ: `HPG`, `SSI`, `VND`...):
1. Gọi `get_historical_candles(symbol, count=60)` để lấy diễn biến 60 phiên gần nhất.
2. Gọi `get_market_depth_and_foreign(symbol)` để lấy hành vi khối ngoại và dư mua/bán.
3. Gọi `get_relative_strength(symbol)` để đối chiếu sức mạnh tương quan với VN-Index.

---

### Bước 2: Phân tích Định lượng Nến & Khối lượng (VPA Scanning)

Rà soát 10 - 15 phiên gần nhất để tìm các mẫu nến VPA kinh điển:

| Mẫu nến VPA | Đặc điểm nhận dạng | Ý nghĩa theo VPA / Smart Money |
| :--- | :--- | :--- |
| **No Supply Bar** | Nến giảm/thân hẹp, Spread nhỏ, $\text{RVol} < 0.65$, xuất hiện sau nhịp chỉnh hoặc tại hỗ trợ. | Cạn kiệt nguồn cung bán tháo. Smart Money kiểm định cung thành công. |
| **Test of Supply** | Nến nhúng sâu quét đáy rồi rút chân ($\text{Close Pos} \ge 60\%$), Volume thấp đến trung bình. | Kiểm định lượng cung trôi nổi. Nếu vol thấp $\rightarrow$ Sẵn sàng tăng. |
| **Stopping Volume / Selling Climax** | Nến giảm biên độ lớn hoặc rút chân mạnh ở cuối nhịp giảm, $\text{RVol} \ge 1.8$. | Smart Money nhảy vào hấp thụ hàng hoảng loạn. Đáy tiềm năng. |
| **Absorption Bar** | Nến tăng mạnh tiệm cận cản, Spread rộng, $\text{Close Pos} \ge 70\%$, $\text{RVol} \ge 1.3$. | Phe mua hấp thụ hết lực bán chốt lời tại cản để chuẩn bị vượt đỉnh. |
| **Upthrust / Bẫy Bull-trap** | Nến cố đẩy qua cản nhưng bị ép xuống, râu trên dài, $\text{Close Pos} \le 35\%$, Volume cao. | Phe mua đu đỉnh bị mắc kẹt, Smart Money xả hàng. |
| **No Demand Bar** | Nến tăng nhẹ, thân hẹp, Volume rất thấp trong nhịp hồi. | Dòng tiền lớn không tham gia đẩy giá. Hồi phục kỹ thuật yếu ớt. |
| **Effort vs Result Discrepancy** | Volume tăng đột biến ($\text{RVol} \ge 1.8$) nhưng thân nến hẹp hoặc đóng giữa. | Nỗ lực lớn nhưng kết quả nhỏ $\rightarrow$ Bị chặn cung hoặc chặn cầu âm thầm. |

---

### Bước 3: Định vị Cấu trúc & Pha Wyckoff (Wyckoff Schematics)

1. **Xác định Vùng dao động (Trading Range - TR):**
   - Biên dưới (Support): Xác định từ vùng đáy Selling Climax (SC), Secondary Test (ST), hoặc Spring.
   - Biên trên (Resistance): Xác định từ đỉnh Automatic Rally (AR) hoặc Buying Climax (BC).
2. **Nhận diện Chu kỳ & Pha:**
   - **Tích lũy (Accumulation):**
     - *Pha A:* Chặn đứng đà giảm (SC, AR, ST).
     - *Pha B:* Tạo nguyên nhân, kiểm định cung cầu trong TR.
     - *Pha C:* Rũ bỏ quyết định — **Spring** hoặc **Shakeout**.
     - *Pha D:* Bứt phá bên trong TR — **Sign of Strength (SOS)** kèm volume lớn, sau đó test lại tạo **Last Point of Support (LPS)**.
     - *Pha E:* Bước vào sóng tăng mạnh (Markup).
   - **Phân phối (Distribution):**
     - *Pha A:* Chặn đà tăng (BC, AR, ST).
     - *Pha B:* Phân phối ngầm.
     - *Pha C:* Xuất hiện **UTAD (Upthrust After Distribution)** vượt đỉnh dụ mua rồi gãy.
     - *Pha D:* Xuất hiện **Sign of Weakness (SOW)** thủng hỗ trợ với volume bán tăng.
     - *Pha E:* Bước vào sóng giảm mạnh (Markdown).
3. **Đánh giá Sức mạnh Tương đối (RS Rank):**
   - Nếu thị trường chỉnh mà cổ phiếu đi ngang giữ nền, RS 20 phiên $> 0\% \rightarrow$ Ứng viên dẫn dắt (Leader).

---

### Bước 4: Tích hợp Smart Money & Lập Kế hoạch Giao dịch (Action Plan)

1. **Đọc vị Dòng tiền lớn:**
   - Khối ngoại liên tục mua ròng ở vùng giá nền $\rightarrow$ Củng cố kịch bản gom hàng (Accumulation).
   - Khối ngoại xả ròng dồn dập ở vùng cản đỉnh $\rightarrow$ Cảnh báo phân phối.
2. **Thiết lập Kế hoạch Mua/Bán (Trade Setup):**
   - **Điểm vào lệnh (Entry):**
     - *Điểm mua 1:* Mua khi nến Test thành công sau Spring (Volume cạn kiệt, rút chân).
     - *Điểm mua 2 (Chuẩn mực Wyckoff):* Mua tại **LPS** khi giá điều chỉnh vol thấp sau cây nến SOS bứt phá.
     - *Điểm mua 3 (Gia tăng):* Mua khi giá breakout vượt qua biên trên của TR (JAC - Jump Across the Creek).
   - **Điểm cắt lỗ (Stop Loss):** Đặt dưới đáy gần nhất của nến Spring hoặc dưới vùng hỗ trợ cứng ($3\% - 5\%$).
   - **Mục tiêu chốt lời (Target):** Đo lường mục tiêu giá dựa trên độ rộng của Trading Range (Luật Cause & Effect) hoặc các đỉnh cản phía trên.
   - **Tỷ lệ Risk : Reward (R:R):** Tối thiểu đạt $1 : 2.5$ trở lên.

---

## 3. Mẫu Báo cáo Đầu ra Chuẩn (Report Format)

```markdown
# Phân tích Kỹ thuật Wyckoff & VPA: [MÃ CỔ PHIẾU] (Sàn: [HOSE/HNX])

## 1. Thông số Kỹ thuật Cốt lõi
- **Thị giá hiện tại:** ... | **Sức mạnh tương đối (RS vs VNINDEX):** ...
- **Khối lượng phiên gần nhất:** ... (RVol: ... lần SMA20)
- **Động thái Khối ngoại (15 phiên gần nhất):** Tổng mua ròng / bán ròng ... tỷ đồng
- **Tình trạng sổ lệnh:** ...

## 2. Quét Tín hiệu Nến & Khối lượng (VPA Scanning 10 phiên gần nhất)
| Ngày | Giá đóng | Biên độ (Spread) | Khối lượng (RVol) | Vị trí đóng (%CP) | Mẫu nến VPA & Hành động giá |
| :--- | :--- | :--- | :--- | :--- | :--- |
| ... | ... | ... | ... | ... | No Supply / Stopping Vol / SOS... |

*Nhận xét VPA:* Đánh giá quy luật Nỗ lực vs Kết quả (Effort vs Result) và tương quan Cung - Cầu ngắn hạn.

## 3. Định vị Cấu trúc Wyckoff
- **Trạng thái cấu trúc:** [Trading Range Tích lũy / Phân phối / Xu hướng tăng / Xu hướng giảm]
- **Biên độ TR:** Hỗ trợ cứng: ... | Kháng cự biên trên: ...
- **Pha hiện tại:** [Phase A / B / C / D / E] - [Chi tiết sự kiện: Spring, Test, SOS, LPS...]
- **Dấu ấn Smart Money:** Nhận định sự tham gia của dòng tiền lớn qua thanh khoản và khối ngoại.

## 4. Kế hoạch Giao dịch (Trading Plan Khuyến nghị)
- **Khuyến nghị:** [THEO DÕI / MUA THĂM DÒ / MUA GIA TĂNG / ĐỨNG NGOÀI]
- **Vùng mua (Entry):** ...
- **Điểm cắt lỗ (Stop Loss):** ... (Thủng ngưỡng ...)
- **Mục tiêu giá (Target 1 & 2):** ...
- **Tỷ lệ R : R:** 1 : ...
```
