---
name: mcdx-flow-radar
description: >-
  SKILL_9 — MCDX Flow Radar: Quét và xếp hạng danh sách cổ phiếu theo dấu vết dòng tiền tạo lập
  (tiêu chuẩn WFE V3.0), với 2 chế độ lọc: ĐÃ CÓ (ESTABLISHED) và BẮT ĐẦU THAM GIA (EMERGING: Flow Turn / Gom bí mật).
  Triggers: "mcdx flow radar", "dòng tiền tạo lập", "quét mcdx", "dòng tiền lớn", "tiền to vào",
  "established flow", "emerging flow", "gom bí mật", "flow turn", "banker intensity", "bii", "skill 9".
---

# Kỹ Năng Quét Dòng Tiền Tạo Lập (MCDX Flow Radar — SKILL_9)
### Tiêu chuẩn WFE V3.0 — Wyckoff × Flow Expectancy

---

## 1. Định Nghĩa & Phạm Vi

- **Tên kỹ năng:** `MCDX Flow Radar` (id: `SKILL_9`), tiêu chuẩn **WFE V3.0**.
- **Bản chất:** Radar **lọc ứng viên** theo cường độ dòng tiền — **KHÔNG PHẢI tín hiệu mua/bán**.
- **Ranh giới kiến trúc:** Kỹ năng chỉ tiêu thụ đầu ra số học của **Flow Engine (L1)**. Không tự tính lại MCDX, không gọi Structure Engine hoặc Volume Engine (tuân thủ triệt để Hiến pháp kiến trúc: dòng tiền chỉ gặp cấu trúc ở tầng Policy).
- **Mục tiêu:** Trả về danh sách xếp hạng theo chỉ số cường độ dòng tiền tạo lập (**Banker Intensity Index - BII**, 0–100), với 2 chế độ lọc:
  - `ESTABLISHED` — **Đã có** dòng tiền tạo lập hiện diện và duy trì bền vững;
  - `EMERGING` — **Bắt đầu** có dòng tiền tạo lập tham gia (vào công khai HOẶC gom bí mật);
  - `BOTH` — Hợp nhất và gắn tag phân loại từng dòng.
- **Non-goals:** Tuyệt đối không xuất target/stop, không gán nhãn pha Wyckoff, không hứa hẹn sóng hay bảo đảm lợi nhuận.

---

## 2. Dữ Liệu Đầu Vào (Nến Đóng từ Flow Engine)

Mỗi cổ phiếu sau mỗi phiên giao dịch:
- `flow_trend`, `flow_accum`, `flow_dist` (thang điểm 0–100 + phân vị percentile cuộn 250 phiên);
- `RVol`, `SMA5_RVol`, thành phần co cụm bán `dv_contr`, phân kỳ `obv_div`;
- Độ dốc `slope5(flow_trend)` và `slope10(flow_accum)`;
- Thanh khoản `ADTV20`, cờ phiên trần/sàn `limit_day`, cờ `data_ok`, `trend_collapse_warning`, mã băm `params_hash`.

---

## 3. Logic Lọc Định Lượng Theo Chế Độ

### 3.1 `ESTABLISHED` — "Đã có dòng tiền tạo lập" (Phải thỏa mãn đồng thời E1–E4)

| Rule | Điều kiện định lượng | Ý nghĩa bản chất |
| :--- | :--- | :--- |
| **E1** | `flow_trend ≥ 50` *(mặc định tier `strong`; option tier `control` hạ xuống `≥ 25`)* | Dòng tiền tổ chức hiện diện rõ nét |
| **E2** | `flow_trend ≥ 25` ở `≥ 3/5` phiên gần nhất | **Tính duy trì**, loại trừ triệt để bẫy volume spike 1 phiên |
| **E3** | `SMA5_RVol ≥ 1.10` | Thanh khoản 5 phiên xác nhận tiền thật gia tăng |
| **E4** | `flow_dist ≤ p60` VÀ `trend_collapse_warning = False` | Bảo đảm không mua vào các phiên phân phối ngầm |

> [!GUARD]
> **Limit-day Guard:** Nếu $\ge 2/3$ mức tăng của `flow_trend` đến từ duy nhất một phiên trần/sàn (`limit_day = True`), cổ phiếu sẽ **bị loại ngay lập tức khỏi danh sách ESTABLISHED**.

### 3.2 `EMERGING` — "Bắt đầu tham gia" (Thỏa mãn G1 HOẶC G2)

#### 🔹 G1 — Vào công khai (Flow turn):
- `flow_trend` cắt lên ngưỡng $15$ tại phiên mới nhất, sau khi $\le 15$ tại $\ge 8/10$ phiên trước đó;
- Yêu cầu xác nhận $2$ phiên liên tiếp trên ngưỡng (tránh hiện tượng cross-intraday ảo);
- `slope5(flow_trend) > 0` và `SMA5_RVol ≥ 1.0`.

#### 🔹 G2 — Gom bí mật (Leading, giá chưa chạy):
- `flow_trend < 25` *(chưa lộ diện trên chart)* **VÀ** `flow_accum ≥ p70` *(hoặc $\ge 30$ theo thang điểm thô)* và `slope10(flow_accum) > 0`;
- Co cụm volume bán: `dv_contr = SMA5(down_vol) / SMA20(down_vol) ≤ 0.75` *(áp lực bán cạn kiệt $\ge 25\%$ so với bình quân)*;
- `obv_div ≥ 0.15` *(OBV bứt phá trước giá)* **VÀ** Giá nén chặt: Biên độ dao động 20 phiên $\le 8\%$ (`(max_H20 - min_L20) / min_L20 <= 0.08`);
- **Loại trừ phân phối:** Nếu `flow_dist ≥ p50` (dấu hiệu kéo xả trong phân phối) $\rightarrow$ **Cấm tag emerging**.

### 3.3 Xếp Hạng: Banker Intensity Index (BII, 0–100)

- **Danh mục ESTABLISHED:**
  $$BII_{est} = 0.50 \times flow\_trend + 0.20 \times persist\_score + 0.20 \times pct(SMA5\_RVol) + 0.10 \times flow\_accum - 0.20 \times flow\_dist$$
- **Danh mục EMERGING:**
  $$BII_{emg} = 0.40 \times flow\_accum + 0.25 \times pct(slope10) + 0.20 \times pct(dv\_contr) + 0.15 \times obv\_div - 0.15 \times flow\_dist$$
  *(Cộng thêm $+5$ điểm freshness nếu G1 mới bứt phá trong $\le 5$ phiên)*.

---

## 4. Bảng Tham Số Options

```json
{
  "mode": "both | established | emerging",      // mặc định "both"
  "strength_tier": "strong | control | all",     // mặc định "strong" (E1=50)
  "threshold_mode": "absolute | percentile",     // mặc định "absolute"
  "persistence_window": 5,
  "min_adtv_billion": 15,
  "universe": "HOSE | ALL | watchlist[]",
  "top_n": 20,
  "as_of": "last_close"
}
```

---

## 5. Quy Tắc Bắt Buộc Dành Cho AI Agent (LLM Rules)

> [!CRITICAL]
> 1. **Xưng Danh Đúng Chế Độ:**
>    - Khi nói về nhóm ESTABLISHED: Dùng chuẩn *"Dòng tiền tạo lập đang **hiện diện và duy trì**"*.
>    - Khi nói về nhóm EMERGING: Dùng chuẩn *"Dòng tiền **bắt đầu tham gia, chưa xác nhận xu hướng**"*.
> 2. **Cấm Từ Ngữ Cảm Tính / Thổi Phồng:** Tuyệt đối cấm dùng *"bảo kê, chắc thắng, siêu cổ, tuyệt đối, sắp sóng"*. Bắt buộc dùng ngôn ngữ định lượng xác suất.
> 3. **Cờ Cảnh Báo Phân Phối:** Luôn hiển thị cột `flow_dist`. Bất kỳ mã nào có `flow_dist ≥ 70`, dù thỏa mãn điều kiện E/G, **bắt buộc phải gắn tag `[CẢNH BÁO PHÂN PHỐI]`**.
> 4. **Luật Thị Trường Yếu (< 5 mã):** Nếu danh sách lọc trả về ít hơn 5 mã, AI phải báo thẳng: *"Thị trường hiện tại không thỏa mãn tiêu chí dòng tiền tạo lập"*, liệt kê các tùy chọn có thể nới (như chuyển `strength_tier` sang `control`), **tuyệt đối không tự ý nới lỏng ngưỡng khi chưa có yêu cầu**.
> 5. **Kill-Switch Guard:** Nếu `flow_mode = off`, từ chối chạy radar và giải thích hệ thống đang thoái hóa an toàn về Structure + VPA.
> 6. **Bắt Buộc Trích Dẫn Trace:** Khi giải thích từng mã, bắt buộc trích dẫn số liệu thật từ chuỗi `trace` của mã đó.
> 7. **Disclaimer Bắt Buộc:** Mọi báo cáo phải kết thúc bằng tuyên bố miễn trừ trách nhiệm chuẩn hóa.

---

## 6. Quy Trình Thực Thi Chuẩn (SOP)

### Bước 1: Quét Lọc Qua MCP Tool
Gọi công cụ `scan_mcdx_radar` từ `vnstock` MCP:
```python
scan_mcdx_radar(
    mode="both",           # hoặc "established" / "emerging"
    strength_tier="strong",
    min_adtv_billion=15.0,
    top_n=20
)
```

### Bước 2: Phân Tích Danh Sách Ứng Viên
- Đọc mảng `candidates`, trích xuất các mã Top theo chỉ số `bii`.
- Kiểm tra các cờ rủi ro (`is_dist_warning`, `trace`).

### Bước 3: Đưa Ra Gợi Ý Hành Động Cố Định
Bắt buộc in dòng khuyến nghị bước tiếp theo:
> 💡 **Bước kế tiếp:** Chạy WFE setup scan (Structure + VPA + Policy) trên Top N để kiểm định điểm mua rủi ro thấp và lập kế hoạch Tranche giải ngân.

---

## 7. Mẫu Báo Cáo Chuẩn Đầu Ra (Report Template)

```markdown
# Báo Cáo Radar Dòng Tiền Tạo Lập (MCDX Flow Radar — SKILL_9)

*(Lưu ý Hệ thống: MCDX là proxy heuristic từ giá và khối lượng công khai, không phải sổ lệnh thật của tạo lập. Danh sách trả về là radar ứng viên theo dõi dòng tiền, không phải khuyến nghị mua/bán).*

## 1. Bảng Xếp Hạng Cường Độ Dòng Tiền (Banker Intensity Index - BII)

| Mã | Giá | ADTV (Tỷ) | Flow Trend (Trạng thái) | Duy Trì (5 phiên) | Flow Accum | Flow Dist (Cờ rủi ro) | RVol 5D | Phân Loại | BII |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| FPT | 135.2 | 85.4 | 100.0 (Tiền to bùng nổ) | 5/5 | 45.2 | 12.0 | 1.35 | ESTABLISHED | 86.5 |
| MWG | 66.5 | 62.1 | 18.5 (Bắt đầu gom) | 2/5 | 52.0 | 8.5 | 1.15 | EMERGING (Flow Turn) | 68.2 |

## 2. Chi Tiết Từng Ứng Viên & Dấu Vết Định Lượng (Trace)

### 🎯 [MÃ] — Phân loại: [ESTABLISHED / EMERGING]
- **Dữ liệu Trace thực:** `[Trích xuất toàn bộ dòng trace từ hệ thống]`
- **Đánh giá dòng tiền:** Dòng tiền tạo lập đang [hiện diện và duy trì / bắt đầu tham gia, chưa xác nhận xu hướng].
- **Cảnh báo rủi ro:** [Nếu flow_dist >= 70 gắn CẢNH BÁO PHÂN PHỐI, ngược lại ghi nhận áp lực bán an toàn].

---

💡 **Gợi ý bước kế tiếp:** Chạy WFE setup scan (`scan_wfe_v3` hoặc `scan_wyckoff_phase_c_d`) trên top mã này để kiểm định cấu trúc hộp tích lũy và xác định điểm mua Tranche T0/T1.
```
