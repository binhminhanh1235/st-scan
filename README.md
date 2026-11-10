# Bộ Công cụ Phân tích Đầu tư Chứng khoán Việt Nam (VNStock MCP & Wyckoff/VPA Skills)

Bộ công cụ tích hợp sẵn **Local MCP Server** và **2 Kỹ năng Hợp nhất Chuyên sâu (Unified Skills)** dành cho AI Assistant (Google Antigravity, Claude Desktop) giúp phân tích kỹ thuật theo phương pháp **Richard Wyckoff & VPA (Volume Price Analysis)** kết hợp **Dòng tiền Tạo lập MCDX** trên thị trường chứng khoán Việt Nam.

---

## 🌟 Tính năng Nổi bật

* **100% Miễn phí & Siêu tốc:** Kết nối trực tiếp vào các cổng dữ liệu mở của DNSE và 24hMoney, không cần đăng ký tài khoản, không cần API Key, không bị chặn Cloudflare hay giới hạn số lượt gọi.
* **Tiết kiệm Token tối đa:** Mọi phép tính toán học nặng ($SMA_{20}$, Spread, Close Position %, RVol, RS Score, Tỷ lệ R:R, MCDX BII, Phân kỳ Dòng tiền) đều được xử lý trước ở tầng Python, trả về dữ liệu tinh gọn giúp AI suy luận chính xác và nhanh chóng.
* **Hệ thống 2 Kỹ năng Hợp nhất (Unified Architecture):**
  1. **`invest-market-scanner`:** Bộ quét hội tụ đa nhân tố toàn thị trường:
     - 3-Tier VN-Index Market Regime Gate (BULL / CAUTION / BEAR).
     - WFE V3.5 Wyckoff Phase C (Spring/Test) & Phase D (LPS/BU).
     - High R:R V2.2 Range Rebound & Breakout.
     - MCDX Banker Flow Radar (Chỉ số BII, Dòng tiền Tạo lập, Cảnh báo Phân phối).
     - Mansfield Relative Strength (RS Leaders) & Sector Breadth.
     - Dòng tiền Khối ngoại 15 phiên gần nhất.
     - Xuất tường minh: Vùng mua tối ưu (chống bẫy T+2.5), Khi nào KHÔNG ĐƯỢC MUA (Veto), Khi nào PHẢI BÁN (SL, Trailing Stop, Climax, Time-stop) và Phân bổ vốn (% NAV).
  2. **`invest-stock-portfolio-advisor`:** Cố vấn phân tích chuyên sâu Wyckoff/VPA từng mã và Quản trị danh mục:
     - Soi nến VPA chi tiết, cấu trúc tích lũy TR Wyckoff, độ nén vol, dòng tiền lớn.
     - Quản trị danh mục mở (`portfolio_tracker.json`), tự động đánh giá Trailing Stop 3 giai đoạn, Spring Wash-out Guard 5 điều kiện, chốt lời từng phần và Time-Stop T+8.

---

## 📁 Cấu trúc Thư mục Đóng gói

```text
invest/
├── install.sh                  # Script cài đặt tự động 1-click cho macOS / Linux
├── install.ps1                 # Script cài đặt tự động 1-click cho Windows
├── requirements.txt            # Thư viện phụ thuộc (mcp, requests)
├── README.md                   # Hướng dẫn chi tiết
├── mcp/
│   └── vnstock_server.py       # Local MCP Server cung cấp 9+ công cụ tài chính
└── skills/
    ├── invest-market-scanner/  # Kỹ năng quét cơ hội đầu tư hội tụ toàn thị trường
    │   └── SKILL.md
    └── invest-stock-portfolio-advisor/ # Kỹ năng soi mã chuyên sâu & quản trị danh mục
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
3. Cài đặt 2 unified skills vào `~/.gemini/config/skills/` và `~/.agents/skills/`.
4. Tự động ghi cấu hình vào file `~/.gemini/config/mcp_config.json` (và cả `claude_desktop_config.json` nếu máy có cài Claude Desktop) kèm biến môi trường `VNSTOCK_EXTRA_PATH`.

---

## 🛠️ Danh sách Công cụ trong MCP Server (`vnstock`)

| Tên công cụ | Chức năng | Dữ liệu trả về |
| :--- | :--- | :--- |
| `scan_unified_opportunities` | **Quét hội tụ toàn diện** (WFE + High R:R + MCDX + RS Leaders + Foreign) | Top cơ hội kèm Regime Gate, Vùng mua tối ưu, Veto, SL/TP và Phân bổ vốn (% NAV). |
| `evaluate_positions_and_exits` | Đánh giá danh mục & trailing stop đa kỳ | Trạng thái vị thế, Operative SL, Spring Guard, Khuyến nghị chốt lời/cắt lỗ/nắm giữ. |
| `get_historical_candles` | Lấy dữ liệu nến n ngày hoặc tuần | OHLCV, Spread, Vị trí đóng nến (%CP), $SMA_{20}$, RVol, VPA Tag. |
| `get_market_depth_and_foreign` | Lấy giá realtime & sổ lệnh | Giá khớp, 3 mức dư mua/bán, 15 phiên mua/bán ròng Khối ngoại (Tỷ đồng). |
| `get_relative_strength` | So sánh sức mạnh giá với VNINDEX | Hiệu suất 10D, 20D, 60D và mức vượt trội (Excess RS %). |
| `scan_market_leaders` | Quét toàn bộ cổ phiếu dẫn dắt | Bảng xếp hạng Top 10-15 mã có RS Score cao nhất thị trường. |
| `scan_high_rr_setups` | Quét cơ hội tỷ lệ R:R cao | Bảng lọc các mã gần hỗ trợ, tính sẵn Stop Loss, Target, Risk %, Reward %, R:R. |
| `scan_wfe_v3` | Quét Wyckoff Phase C & D | Danh sách ứng viên Test of Spring (Pha C) & LPS/BU (Pha D) chuẩn WFE. |

---

## 💬 Hướng dẫn Sử dụng trong Antigravity

Sau khi cài đặt, bạn có thể gọi trực tiếp bằng ngôn ngữ tự nhiên:

### 1. Quét cơ hội toàn thị trường (Unified Scanner):
* `"Quét cổ phiếu đáng mua nhất hôm nay"`
* `"Tìm kèo tỷ lệ R:R cao kèm dòng tiền tạo lập MCDX"`
* `"Quét cổ phiếu Wyckoff Pha C và Pha D"`
* `"Top cổ phiếu RS dẫn dắt thị trường"`

### 2. Phân tích 1 mã cụ thể (Wyckoff & VPA):
* `"Phân tích HPG theo Wyckoff VPA"`
* `"Soi nến vol và dòng tiền SSI"`
* `"Đánh giá điểm mua CTG có bị bẫy T+2.5 không"`

### 3. Đánh giá & Quản trị Danh mục (Portfolio & Exit Advisor):
* `"Review danh mục đầu tư hiện tại"`
* `"Có nên bán cổ phiếu X hay tiếp tục gồng lãi?"`
* `"Đối chiếu kết quả các kèo khuyến nghị"`
