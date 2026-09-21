#!/usr/bin/env bash
# ==============================================================================
# VNStock MCP & Wyckoff / VPA Skills Installer for Antigravity & Claude Desktop
# Supports: macOS & Linux
# ==============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}   CÀI ĐẶT VNSTOCK MCP SERVER & SKILLS CHO ANTIGRAVITY${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Xác định thư mục nguồn
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 2. Kiểm tra Python 3
if command -v python3 &>/dev/null; then
    PYTHON_BIN="$(which python3)"
else
    echo -e "${YELLOW}[!] Không tìm thấy python3 trên máy. Vui lòng cài đặt Python 3.10+ trước.${NC}"
    exit 1
fi

echo -e "${GREEN}[✓] Tìm thấy Python:${NC} $PYTHON_BIN ($($PYTHON_BIN --version))"

# 3. Cài đặt các thư viện phụ thuộc
echo -e "\n${BLUE}[1/4] Đang cài đặt thư viện phụ thuộc (mcp, requests)...${NC}"
"$PYTHON_BIN" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
echo -e "${GREEN}[✓] Cài đặt thư viện Python thành công.${NC}"

# 4. Sao chép Local MCP Server
TARGET_MCP_DIR="$HOME/.gemini/config/mcp"
mkdir -p "$TARGET_MCP_DIR"
cp "$SCRIPT_DIR/mcp/vnstock_server.py" "$TARGET_MCP_DIR/vnstock_server.py"
chmod +x "$TARGET_MCP_DIR/vnstock_server.py"
echo -e "${GREEN}[✓] Đã sao chép vnstock_server.py vào:${NC} $TARGET_MCP_DIR"

# 5. Sao chép các Skills vào Antigravity
TARGET_SKILLS_DIR="$HOME/.gemini/config/skills"
mkdir -p "$TARGET_SKILLS_DIR"
cp -r "$SCRIPT_DIR/skills/tcbs-wyckoff-vpa" "$TARGET_SKILLS_DIR/"
cp -r "$SCRIPT_DIR/skills/market-leader-scanner" "$TARGET_SKILLS_DIR/"
cp -r "$SCRIPT_DIR/skills/high-rr-setup-scanner" "$TARGET_SKILLS_DIR/"
cp -r "$SCRIPT_DIR/skills/wyckoff-phase-cd-screener" "$TARGET_SKILLS_DIR/"
echo -e "${GREEN}[✓] Đã cài đặt 4 Skills vào:${NC} $TARGET_SKILLS_DIR"
echo -e "    - tcbs-wyckoff-vpa (Phân tích nến VPA & Wyckoff từng mã)"
echo -e "    - market-leader-scanner (Quét top cổ phiếu dẫn dắt RS cao)"
echo -e "    - high-rr-setup-scanner (Quét kèo R:R cao mua nền & vượt đỉnh)"
echo -e "    - wyckoff-phase-cd-screener (Quét điểm mua Test of Spring Pha C & BU/LPS Pha D)"

# 6. Tự động cấu hình Antigravity mcp_config.json
echo -e "\n${BLUE}[3/4] Cấu hình file mcp_config.json cho Antigravity...${NC}"
ANTIGRAVITY_CONFIG="$HOME/.gemini/config/mcp_config.json"

"$PYTHON_BIN" - <<EOF
import json, os

config_path = os.path.expanduser("$ANTIGRAVITY_CONFIG")
os.makedirs(os.path.dirname(config_path), exist_ok=True)

data = {}
if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
    data["mcpServers"] = {}

data["mcpServers"]["vnstock"] = {
    "command": "$PYTHON_BIN",
    "args": [os.path.expanduser("$TARGET_MCP_DIR/vnstock_server.py")]
}

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("    Đã cập nhật", config_path)
EOF

echo -e "${GREEN}[✓] Cấu hình Antigravity thành công.${NC}"

# 7. Hỗ trợ thêm cho Claude Desktop (nếu máy có cài)
CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ -d "$HOME/Library/Application Support/Claude" ]; then
    echo -e "\n${BLUE}[4/4] Phát hiện Claude Desktop, đang cấu hình...${NC}"
    "$PYTHON_BIN" - <<EOF
import json, os

config_path = os.path.expanduser("$CLAUDE_CONFIG")
data = {}
if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
    data["mcpServers"] = {}

data["mcpServers"]["vnstock"] = {
    "command": "$PYTHON_BIN",
    "args": [os.path.expanduser("$TARGET_MCP_DIR/vnstock_server.py")]
}

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("    Đã cập nhật", config_path)
EOF
    echo -e "${GREEN}[✓] Đã cấu hình thêm cho Claude Desktop.${NC}"
fi

echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}             CÀI ĐẶT HOÀN TẤT THÀNH CÔNG!             ${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "Bây giờ bạn có thể mở Antigravity và sử dụng ngay các lệnh:"
echo -e "  1. ${YELLOW}/tcbs-wyckoff-vpa HPG${NC}            -> Phân tích mã cụ thể"
echo -e "  2. ${YELLOW}/market-leader-scanner${NC}             -> Quét cổ phiếu mạnh nhất"
echo -e "  3. ${YELLOW}/high-rr-setup-scanner${NC}             -> Quét kèo tỷ lệ R:R cao nhất"
echo -e ""
