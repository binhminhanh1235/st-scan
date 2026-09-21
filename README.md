# Bộ Công cụ Phân tích Đầu tư Chứng khoán Việt Nam (VNStock MCP & Wyckoff/VPA Skills)

Bộ công cụ tích hợp sẵn **Local MCP Server** và **4 Kỹ năng chuyên sâu (Skills)** dành cho AI Assistant (Google Antigravity, Claude Desktop) giúp phân tích kỹ thuật theo phương pháp **Richard Wyckoff & VPA (Volume Price Analysis)** trên thị trường chứng khoán Việt Nam.

---

## 🌟 Tính năng Nổi bật

* **100% Miễn phí & Siêu tốc:** Kết nối trực tiếp vào các cổng dữ liệu mở của DNSE và 24hMoney, không cần đăng ký tài khoản, không cần API Key, không bị chặn Cloudflare hay giới hạn số lượt gọi.
* **Tiết kiệm Token tối đa:** Mọi phép tính toán học nặng ($SMA_{20}$, Spread, Close Position %, RVol, RS Score, Tỷ lệ R:R) đều được xử lý trước ở tầng Python, trả về dữ liệu tinh gọn giúp AI suy luận chính xác và nhanh chóng.
* **Đầy đủ 4 Kỹ năng then chốt:**
  1. **`tcbs-wyckoff-vpa`:** Phân tích chi tiết 1 mã chứng khoán (nến ngày/nến tuần, khối lượng, khối ngoại, vị thế các Pha Wyckoff).
  2. **`market-leader-scanner`:** Quét toàn thị trường tìm các cổ phiếu dẫn dắt có sức mạnh giá tương đối (RS) cao nhất.
  3. **`high-rr-setup-scanner`:** Quét tìm các cơ hội vào lệnh tối ưu R:R cho dòng vốn lớn (mua nền LPS & vượt đỉnh VCP).
  4. **`wyckoff-phase-cd-screener`:** Quét các điểm mua đón lõng rủi ro cực thấp tại Pha C (Test of Spring) và Pha D (BU/LPS).

---

## 📁 Cấu trúc Thư mục Đóng gói

```text
invest/
├── install.sh                  # Script cài đặt tự động 1-click cho macOS / Linux
├── install.ps1                 # Script cài đặt tự động 1-click cho Windows
├── requirements.txt            # Thư viện phụ thuộc (mcp, requests)
├── README.md                   # Hướng dẫn chi tiết
├── mcp/
│   └── vnstock_server.py       # Local MCP Server cung cấp 6 công cụ tài chính
└── skills/
    ├── tcbs-wyckoff-vpa/       # Kỹ năng phân tích Wyckoff & VPA
    │   └── SKILL.md
    ├── market-leader-scanner/  # Kỹ năng quét cổ phiếu dẫn dắt (RS cao)
    │   └── SKILL.md
    ├── high-rr-setup-scanner/  # Kỹ năng quét điểm mua tối ưu R:R cao
    │   └── SKILL.md
    └── wyckoff-phase-cd-screener/ # Kỹ năng quét điểm mua Wyckoff Pha C & D
        └── SKILL.md
```

---

## 🚀 Hướng dẫn Cài đặt trên Máy Mới (Chỉ 1 Thao tác)

### Cách 1: Trên macOS hoặc Linux
Mở Terminal, chuyển vào thư mục này và chạy:
```bash
chmod +x install.sh
./install.sh
```

### Cách 2: Trên Windows
Mở PowerShell với quyền User thông thường và chạy:
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

*Script cài đặt sẽ tự động:*
1. Cài đặt các thư viện Python cần thiết (`pip install -r requirements.txt`).
2. Sao chép MCP server vào thư mục cấu hình toàn cục `~/.gemini/config/mcp/`.
3. Cài đặt 4 skills vào `~/.gemini/config/skills/`.
4. Tự động ghi cấu hình vào file `~/.gemini/config/mcp_config.json` (và cả `claude_desktop_config.json` nếu máy có cài Claude Desktop).

---

## 🛠️ Danh sách Công cụ trong MCP Server (`vnstock`)

| Tên công cụ | Chức năng | Dữ liệu trả về |
| :--- | :--- | :--- |
| `get_historical_candles` | Lấy dữ liệu nến n ngày hoặc tuần | OHLCV, Spread, Vị trí đóng nến (%CP), $SMA_{20}$, RVol, VPA Tag. |
| `get_market_depth_and_foreign` | Lấy giá realtime & sổ lệnh | Giá khớp, 3 mức dư mua/bán, 15 phiên mua/bán ròng Khối ngoại (Tỷ đồng). |
| `get_relative_strength` | So sánh sức mạnh giá với VNINDEX | Hiệu suất 10D, 20D, 60D và mức vượt trội (Excess RS %). |
| `scan_market_leaders` | Quét toàn bộ cổ phiếu dẫn dắt | Bảng xếp hạng Top 10-15 mã có RS Score cao nhất thị trường. |
| `scan_high_rr_setups` | Quét cơ hội tỷ lệ R:R cao | Bảng lọc các mã gần hỗ trợ, tính sẵn Stop Loss, Target, Risk %, Reward %, R:R. |

---

## 💬 Hướng dẫn Sử dụng trong Antigravity

Sau khi cài đặt, khởi động lại Antigravity và bạn có thể gõ các câu lệnh bằng ngôn ngữ tự nhiên hoặc Slash Commands:

### 1. Phân tích 1 mã cụ thể (Wyckoff & VPA):
* `/tcbs-wyckoff-vpa HPG`
* `Phân tích HPG theo Wyckoff VPA`
* `Phân tích SSI trên khung tuần (1W)`

### 2. Quét cổ phiếu dẫn dắt thị trường (Market Leaders):
* `/market-leader-scanner`
* `Tìm cho mình những cổ phiếu mạnh nhất thị trường hôm nay`
* `Top cổ phiếu có RS cao nhất và dòng tiền khối ngoại gom`

### 3. Quét cổ phiếu có tỷ lệ Risk : Reward cao nhất:
* `/high-rr-setup-scanner`
* `Tìm cho mình những cổ phiếu đáng mua nhất thị trường (tỷ lệ R:R cao)`
* `Tìm kèo mua sát hỗ trợ rủi ro thấp`
