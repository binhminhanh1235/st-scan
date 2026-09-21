# ==============================================================================
# VNStock MCP & Wyckoff / VPA Skills Installer for Antigravity & Claude Desktop
# Supports: Windows (PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File .\install.ps1
# ==============================================================================

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   CÀI ĐẶT VNSTOCK MCP SERVER & SKILLS (WINDOWS)      " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Kiểm tra Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Host "[!] Không tìm thấy Python trên máy. Vui lòng cài Python 3.10+ từ python.org" -ForegroundColor Red
    Exit 1
}

$pythonPath = $pythonCmd.Source
Write-Host "[✓] Tìm thấy Python: $pythonPath" -ForegroundColor Green

# 2. Cài đặt dependencies
Write-Host "`n[1/4] Đang cài đặt thư viện phụ thuộc (mcp, requests)..." -ForegroundColor Cyan
& $pythonPath -m pip install -q -r "$scriptDir\requirements.txt"
Write-Host "[✓] Cài đặt thư viện Python thành công." -ForegroundColor Green

# 3. Sao chép Local MCP Server
$targetMcpDir = "$HOME\.gemini\config\mcp"
if (-not (Test-Path $targetMcpDir)) {
    New-Item -ItemType Directory -Path $targetMcpDir -Force | Out-Null
}
Copy-Item "$scriptDir\mcp\vnstock_server.py" "$targetMcpDir\vnstock_server.py" -Force
Write-Host "[✓] Đã sao chép vnstock_server.py vào: $targetMcpDir" -ForegroundColor Green

# 4. Sao chép Skills
$targetSkillsDir = "$HOME\.gemini\config\skills"
if (-not (Test-Path $targetSkillsDir)) {
    New-Item -ItemType Directory -Path $targetSkillsDir -Force | Out-Null
}
Copy-Item -Recurse "$scriptDir\skills\*" "$targetSkillsDir\" -Force
Write-Host "[✓] Đã cài đặt 4 Skills (tcbs-wyckoff-vpa, market-leader-scanner, high-rr-setup-scanner, wyckoff-phase-cd-screener) vào: $targetSkillsDir" -ForegroundColor Green

# 5. Cấu hình mcp_config.json cho Antigravity
Write-Host "`n[3/4] Cấu hình mcp_config.json cho Antigravity..." -ForegroundColor Cyan
$antigravityConfig = "$HOME\.gemini\config\mcp_config.json"
$serverScript = "$targetMcpDir\vnstock_server.py".Replace('\', '\\')
$pythonEscaped = $pythonPath.Replace('\', '\\')

$updateScript = @"
import json, os

config_path = os.path.expanduser(r'$antigravityConfig')
os.makedirs(os.path.dirname(config_path), exist_ok=True)

data = {}
if os.path.exists(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}

if 'mcpServers' not in data or not isinstance(data['mcpServers'], dict):
    data['mcpServers'] = {}

data['mcpServers']['vnstock'] = {
    'command': r'$pythonEscaped',
    'args': [r'$serverScript']
}

with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print('    Đã cập nhật:', config_path)
"@

& $pythonPath -c $updateScript
Write-Host "[✓] Cấu hình Antigravity thành công." -ForegroundColor Green

# 6. Kiểm tra Claude Desktop trên Windows
$claudeDir = "$env:APPDATA\Claude"
if (Test-Path $claudeDir) {
    Write-Host "`n[4/4] Phát hiện Claude Desktop, đang cấu hình..." -ForegroundColor Cyan
    $claudeConfig = "$claudeDir\claude_desktop_config.json"
    $updateClaudeScript = @"
import json, os

config_path = os.path.expanduser(r'$claudeConfig')
data = {}
if os.path.exists(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}

if 'mcpServers' not in data or not isinstance(data['mcpServers'], dict):
    data['mcpServers'] = {}

data['mcpServers']['vnstock'] = {
    'command': r'$pythonEscaped',
    'args': [r'$serverScript']
}

with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print('    Đã cập nhật Claude config:', config_path)
"@
    & $pythonPath -c $updateClaudeScript
    Write-Host "[✓] Đã cấu hình thêm cho Claude Desktop." -ForegroundColor Green
}

Write-Host "`n======================================================" -ForegroundColor Green
Write-Host "             CÀI ĐẶT HOÀN TẤT THÀNH CÔNG!             " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host "Mở Antigravity và sử dụng ngay:"
Write-Host "  1. /tcbs-wyckoff-vpa HPG" -ForegroundColor Yellow
Write-Host "  2. /market-leader-scanner" -ForegroundColor Yellow
Write-Host "  3. /high-rr-setup-scanner" -ForegroundColor Yellow
Write-Host ""
