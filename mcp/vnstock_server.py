#!/usr/bin/env python3
"""
VNStock MCP Server
Fast, free, and token-efficient market data provider for Vietnamese stocks.
Data sources: Open endpoints from DNSE and 24hMoney (No API Key or auth required).
"""

import os
import sys
import time
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
# NOTE: `mcp.server.mcpserver.MCPServer` never existed in any released version of
# the `mcp` SDK; the correct import is `mcp.server.fastmcp.FastMCP` (same API:
# @server.tool(), .run(), etc.). Fixed so the server can actually be imported.
from mcp.server.fastmcp import FastMCP as MCPServer

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# Allow an explicit override for non-standard checkout locations instead of a
# hardcoded developer-machine absolute path.
_extra_path = os.environ.get("VNSTOCK_EXTRA_PATH")
if _extra_path and _extra_path not in sys.path:
    sys.path.insert(0, _extra_path)

from wfe.scanner import WFEScanner
from wfe.radar import MCDXFlowRadar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vnstock")

server = MCPServer("vnstock")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# ---------------------------------------------------------
# DYNAMIC UNIVERSE & SECTOR INTELLIGENCE
# ---------------------------------------------------------

DEFAULT_CORE_UNIVERSE = [
    # VN30 & Large Caps
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
    # Top Midcaps & Liquid Stocks
    "DGC", "FRT", "CMG", "DGW", "PNJ",
    "VND", "VIX", "HCM", "VCI", "SHS", "MBS", "FTS", "BSI", "ORS", "CTS", "AGR",
    "HSG", "NKG", "VGS",
    "PDR", "DIG", "DXG", "NLG", "KDH", "KBC", "IDC", "NVL", "CII", "TCH", "CEO", "VPI", "SZC",
    "BSR", "PVS", "PVD", "PVT", "DCM", "DPM", "BFC",
    "GMD", "HAH", "VSC", "VOS",
    "VHC", "ANV", "IDI", "DBC", "BAF", "PAN", "HAG",
    "REE", "PC1", "GEG", "HDG",
    "VCG", "HHV", "FCN", "LCG", "CTD",
    "DCL", "EIB", "MSB", "OCB", "NAB"
]

KNOWN_SECTOR_MAP = {
    # Công nghệ & Viễn thông
    "FPT": "Công nghệ", "CMG": "Công nghệ", "ELC": "Công nghệ", "FOX": "Viễn thông",
    # Bán lẻ
    "MWG": "Bán lẻ", "FRT": "Bán lẻ", "DGW": "Bán lẻ", "PET": "Bán lẻ", "PNJ": "Bán lẻ & Vàng bạc",
    # Hóa chất & Phân bón
    "DGC": "Hóa chất", "DCM": "Phân bón & Hóa chất", "DPM": "Phân bón & Hóa chất", "BFC": "Phân bón & Hóa chất", "CSV": "Hóa chất",
    # Chứng khoán
    "SSI": "Chứng khoán", "VND": "Chứng khoán", "VIX": "Chứng khoán", "HCM": "Chứng khoán",
    "VCI": "Chứng khoán", "SHS": "Chứng khoán", "MBS": "Chứng khoán", "FTS": "Chứng khoán",
    "BSI": "Chứng khoán", "ORS": "Chứng khoán", "CTS": "Chứng khoán", "AGR": "Chứng khoán", "DSE": "Chứng khoán",
    # Thép & Kim loại
    "HPG": "Thép", "HSG": "Thép", "NKG": "Thép", "VGS": "Thép", "TLH": "Thép",
    # Ngân hàng
    "TCB": "Ngân hàng", "MBB": "Ngân hàng", "ACB": "Ngân hàng", "CTG": "Ngân hàng",
    "BID": "Ngân hàng", "VCB": "Ngân hàng", "VPB": "Ngân hàng", "STB": "Ngân hàng",
    "HDB": "Ngân hàng", "LPB": "Ngân hàng", "SHB": "Ngân hàng", "TPB": "Ngân hàng",
    "MSB": "Ngân hàng", "VIB": "Ngân hàng", "EIB": "Ngân hàng", "OCB": "Ngân hàng",
    "SSB": "Ngân hàng", "NAB": "Ngân hàng", "BAB": "Ngân hàng", "NVB": "Ngân hàng",
    # Bất động sản dân dụng
    "VIC": "Bất động sản", "VHM": "Bất động sản", "VRE": "Bất động sản", "NVL": "Bất động sản",
    "PDR": "Bất động sản", "DIG": "Bất động sản", "DXG": "Bất động sản", "NLG": "Bất động sản",
    "KDH": "Bất động sản", "CEO": "Bất động sản", "TCH": "Bất động sản", "CII": "Bất động sản & Hạ tầng",
    "VPI": "Bất động sản", "HDG": "Bất động sản & Năng lượng", "KOS": "Bất động sản",
    # Bất động sản KCN
    "KBC": "Bất động sản KCN", "IDC": "Bất động sản KCN", "SZC": "Bất động sản KCN",
    "BCM": "Bất động sản KCN", "VGC": "Bất động sản KCN", "GVR": "Cao su & KCN", "PHR": "Cao su & KCN",
    # Dầu khí
    "BSR": "Dầu khí", "PVS": "Dầu khí", "PVD": "Dầu khí", "PVT": "Vận tải dầu khí",
    "GAS": "Dầu khí", "PLX": "Xăng dầu", "OIL": "Xăng dầu",
    # Điện & Năng lượng
    "POW": "Năng lượng & Điện", "REE": "Cơ điện & Năng lượng", "PC1": "Xây lắp điện & Năng lượng",
    "GEG": "Năng lượng & Điện", "NT2": "Năng lượng & Điện",
    # Cảng biển & Logistics
    "GMD": "Cảng biển & Logistics", "HAH": "Cảng biển & Logistics", "VSC": "Cảng biển & Logistics",
    "VOS": "Vận tải biển",
    # Thủy sản
    "VHC": "Thủy sản", "ANV": "Thủy sản", "IDI": "Thủy sản", "FMC": "Thủy sản",
    # Nông nghiệp & Thực phẩm
    "VNM": "Thực phẩm & Sữa", "MSN": "Tiêu dùng & Bán lẻ", "SAB": "Bia & Nước giải khát",
    "DBC": "Chăn nuôi & Nông nghiệp", "BAF": "Chăn nuôi & Nông nghiệp", "PAN": "Nông nghiệp & Thực phẩm",
    "HAG": "Nông nghiệp", "HNG": "Nông nghiệp", "SBT": "Đường & Nông nghiệp", "QNS": "Đường & Tiêu dùng",
    # Xây dựng & Đầu tư công
    "VCG": "Xây dựng & Đầu tư công", "HHV": "Hạ tầng giao thông", "FCN": "Xây dựng hạ tầng",
    "LCG": "Xây dựng hạ tầng", "CTD": "Xây dựng", "HBC": "Xây dựng",
    # Hàng không
    "VJC": "Hàng không", "HVN": "Hàng không",
    # Dược phẩm
    "DCL": "Dược phẩm", "DHG": "Dược phẩm", "IMP": "Dược phẩm"
}

def infer_sector(company_name: str) -> str:
    """Suy luận nhóm ngành từ tên đăng ký kinh doanh chính thức của doanh nghiệp."""
    if not company_name:
        return "Sản xuất & Thương mại"
    n = company_name.lower()
    if "ngân hàng" in n: return "Ngân hàng"
    if "chứng khoán" in n: return "Chứng khoán"
    if any(k in n for k in ["bất động sản", "địa ốc", "phát triển nhà", "đầu tư nhà"]): return "Bất động sản"
    if "khu công nghiệp" in n: return "Bất động sản KCN"
    if "thép" in n or "kim khí" in n: return "Thép & Kim loại"
    if any(k in n for k in ["dầu khí", "xăng dầu", "lọc hóa dầu", "khoan dầu"]): return "Dầu khí"
    if any(k in n for k in ["cảng", "vận tải", "logistics", "hàng hải", "giao nhận"]): return "Cảng biển & Logistics"
    if any(k in n for k in ["dược", "y tế", "thuốc"]): return "Dược phẩm & Y tế"
    if any(k in n for k in ["thủy sản", "hải sản", "tôm", "cá tra"]): return "Thủy sản"
    if any(k in n for k in ["điện lực", "thủy điện", "nhiệt điện", "năng lượng", "phát điện"]): return "Năng lượng & Điện"
    if any(k in n for k in ["hóa chất", "phân bón", "đạm", "thuốc sát trùng"]): return "Hóa chất & Phân bón"
    if any(k in n for k in ["xây dựng", "hạ tầng", "xây lắp", "cienco"]): return "Xây dựng & Đầu tư công"
    if any(k in n for k in ["bán lẻ", "thế giới số", "thế giới di động"]): return "Bán lẻ"
    if any(k in n for k in ["công nghệ", "viễn thông", "phần mềm", "tin học"]): return "Công nghệ & Viễn thông"
    if any(k in n for k in ["bảo hiểm"]): return "Bảo hiểm"
    if any(k in n for k in ["cao su"]): return "Cao su"
    if any(k in n for k in ["xi măng"]): return "Vật liệu xây dựng"
    if any(k in n for k in ["thực phẩm", "nông nghiệp", "chăn nuôi", "sữa", "đường", "mía", "bánh kẹo"]): return "Thực phẩm & Nông nghiệp"
    if any(k in n for k in ["hàng không", "bay", "du lịch"]): return "Hàng không & Du lịch"
    return "Sản xuất & Thương mại"

_DYNAMIC_UNIVERSE_CACHE = {
    "symbols": None,
    "company_names": {},
    "ts": 0
}
_UNIVERSE_TTL = 900  # Cache 15 phút

def get_dynamic_universe(min_today_val_bil: float = 3.0, max_stocks: int = 85) -> list:
    """
    Tự động quét danh sách các cổ phiếu thanh khoản cao và tốt nhất thị trường (HOSE + HNX)
    qua API SSI iBoard theo thời gian thực.
    Nếu ngoài giờ giao dịch hoặc có lỗi mạng, tự động dự phòng về DEFAULT_CORE_UNIVERSE.
    """
    now = time.time()
    if _DYNAMIC_UNIVERSE_CACHE["symbols"] and (now - _DYNAMIC_UNIVERSE_CACHE["ts"] < _UNIVERSE_TTL):
        return _DYNAMIC_UNIVERSE_CACHE["symbols"]

    try:
        r_hose = requests.get("https://iboard-query.ssi.com.vn/stock/exchange/hose", headers=HEADERS, timeout=4)
        r_hnx = requests.get("https://iboard-query.ssi.com.vn/stock/exchange/hnx", headers=HEADERS, timeout=4)
        data = r_hose.json().get("data", []) + r_hnx.json().get("data", [])

        valid = []
        names = {}
        for item in data:
            sym = item.get("stockSymbol", "").upper()
            if len(sym) != 3 or item.get("stockType") != "s":
                continue
            val = (item.get("nmTotalTradedValue") or 0) / 1e9
            price = (item.get("matchedPrice") or item.get("refPrice") or 0)
            name = item.get("companyNameVi", "")
            names[sym] = name

            # Loại bỏ penny rác (< 7,000 VNĐ) nếu có giá
            if 0 < price < 7000:
                continue
            valid.append({"symbol": sym, "val": val})

        valid.sort(key=lambda x: x["val"], reverse=True)
        filtered = [s["symbol"] for s in valid if s["val"] >= min_today_val_bil]

        # Nếu đang trong phiên và lấy được >= 30 mã đạt chuẩn thanh khoản hôm nay:
        if len(filtered) >= 30:
            selected = filtered[:max_stocks]
        else:
            # Ngoài giờ giao dịch hoặc đầu ngày: Lấy toàn bộ DEFAULT_CORE_UNIVERSE
            selected = list(DEFAULT_CORE_UNIVERSE)

        _DYNAMIC_UNIVERSE_CACHE["symbols"] = selected
        _DYNAMIC_UNIVERSE_CACHE["company_names"].update(names)
        _DYNAMIC_UNIVERSE_CACHE["ts"] = now
        logger.info(f"Loaded dynamic market universe with {len(selected)} stocks.")
        return selected
    except Exception as e:
        logger.warning(f"Error loading dynamic universe from SSI: {e}. Fallback to DEFAULT_CORE_UNIVERSE.")
        return list(DEFAULT_CORE_UNIVERSE)

def get_stock_sector(symbol: str, company_name: str = None) -> str:
    """Xác định ngành của cổ phiếu dựa trên KNOWN_SECTOR_MAP hoặc phân tích tên công ty."""
    sym = symbol.upper()
    if sym in KNOWN_SECTOR_MAP:
        return KNOWN_SECTOR_MAP[sym]
    name = company_name or _DYNAMIC_UNIVERSE_CACHE["company_names"].get(sym, "")
    return infer_sector(name)

# Giữ tương thích ngược
UNIVERSE = DEFAULT_CORE_UNIVERSE
SECTOR_MAP = KNOWN_SECTOR_MAP

# In-memory Cache với TTL = 180 giây (3 phút)
_CACHE = {}
_CACHE_TTL = 180


def _fetch_dnse_raw(symbol: str, resolution: str = "1D", days: int = 90):
    """Lấy dữ liệu OHLCV thô từ DNSE kèm in-memory cache và retry."""
    symbol = symbol.upper()
    now = int(time.time())
    cache_key = (symbol, resolution.upper(), days)
    cached = _CACHE.get(cache_key)
    if cached and (now - cached["ts"] < _CACHE_TTL):
        return cached["data"]

    from_time = now - days * 86400
    path = "index" if symbol in ["VNINDEX", "VN30", "HNXINDEX"] else "stock"
    url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{path}?from={from_time}&to={now}&symbol={symbol}&resolution={resolution}"

    for attempt in range(2):
        try:
            r = requests.get(url, headers=HEADERS, timeout=4)
            if r.status_code == 200:
                data = r.json()
                _CACHE[cache_key] = {"data": data, "ts": now}
                return data
            logger.warning(f"DNSE {symbol} status {r.status_code} (attempt {attempt + 1})")
        except requests.RequestException as e:
            logger.warning(f"DNSE {symbol} error: {e} (attempt {attempt + 1})")
            time.sleep(0.2)
    return None


def _fetch_batch_candles(symbols: list, days: int = 90, resolution: str = "1D", max_workers: int = 10) -> dict:
    """Tải đồng thời OHLCV của danh sách cổ phiếu qua ThreadPoolExecutor."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_sym = {
            executor.submit(_fetch_dnse_raw, sym, resolution, days): sym
            for sym in symbols
        }
        for future in as_completed(future_to_sym):
            sym = future_to_sym[future]
            try:
                data = future.result()
                if data:
                    results[sym] = data
            except Exception as e:
                logger.error(f"Error fetching batch for {sym}: {e}")
    return results


def _fetch_dnse_ohlcv(symbol: str, resolution: str = "1D", count: int = 60):
    if resolution.upper() in ["1W", "W"]:
        days = int(count * 7 * 1.4)
    elif resolution.upper() in ["1M", "M"]:
        days = int(count * 30 * 1.4)
    else:
        days = int(count * 1.8)

    d = _fetch_dnse_raw(symbol, resolution, days)
    if not d:
        raise Exception(f"Lỗi khi lấy dữ liệu nến từ DNSE cho mã {symbol}")

    times = d.get("t", [])
    opens = d.get("o", [])
    highs = d.get("h", [])
    lows = d.get("l", [])
    closes = d.get("c", [])
    vols = d.get("v", [])

    bars = []
    n = len(times)
    for i in range(n):
        dt = datetime.datetime.fromtimestamp(times[i]).strftime("%Y-%m-%d")
        bars.append({
            "date": dt,
            "open": opens[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "volume": vols[i]
        })
    return bars[-count:]


def compute_clean_sma20_vol(v: list, c: list, o: list, h: list, l: list, end_idx: int) -> float:
    """Computes SMA20 volume excluding limit-ceiling/floor bars."""
    start_idx = max(0, end_idx - 19)
    normal_vols = []
    for j in range(start_idx, end_idx + 1):
        if c[j] > 0 and o and j < len(o):
            is_ceil = (c[j] == h[j] and abs(c[j] - o[j]) / c[j] < 0.001)
            is_floor = (c[j] == l[j] and abs(c[j] - o[j]) / c[j] < 0.001)
            if not (is_ceil or is_floor):
                normal_vols.append(v[j])
    if normal_vols:
        return sum(normal_vols) / len(normal_vols)
    window = v[start_idx:end_idx + 1]
    return sum(window) / len(window) if window else 1.0


def compute_wilder_atr14(c: list, h: list, l: list) -> float:
    """Computes Wilder's ATR 14 from lists of floats."""
    n = len(c)
    if n < 15:
        return (h[-1] - l[-1]) if n > 0 else 1.0
    tr_list = []
    for i in range(1, n):
        tr = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        tr_list.append(tr)
    curr_atr = sum(tr_list[:14]) / 14.0
    for i in range(14, len(tr_list)):
        curr_atr = (curr_atr * 13.0 + tr_list[i]) / 14.0
    return curr_atr


def classify_vpa(
    c: list,
    o: list,
    h: list,
    l: list,
    v: list,
    i: int,
    sma20_vol: float
) -> str:
    """Context-aware VPA classification for candle at index i."""
    if i < 0 or i >= len(c):
        return "Bình thường"

    high = h[i]
    low = l[i]
    close = c[i]
    vol = v[i]

    spread = round(high - low, 2)
    cp = round(((close - low) / spread * 100), 1) if spread > 0 else 50.0
    rvol = round(vol / sma20_vol, 2) if sma20_vol > 0 else 1.0

    # Multi-session context
    prev_dump = False
    prev_climax = False
    if i >= 2:
        prev_spread = round(h[i-1] - l[i-1], 2)
        prev_cp = round((c[i-1] - l[i-1]) / prev_spread * 100, 1) if prev_spread > 0 else 50.0
        prev_rvol = round(v[i-1] / sma20_vol, 2) if sma20_vol > 0 else 1.0
        prev_dump = (c[i-1] < c[i-2] and prev_cp <= 30.0 and prev_rvol >= 1.1)
        prev_climax = (c[i-1] > c[i-2] and prev_cp >= 75.0 and prev_rvol >= 1.5)

    # 1. Grinding decline detection (BUG-4: 3 phiên giảm liên tục cạn vol)
    if i >= 3 and (c[i] < c[i-1] < c[i-2] < c[i-3]):
        avg_rvol_3d = sum(v[i-2:i+1]) / (3 * sma20_vol) if sma20_vol > 0 else rvol
        if avg_rvol_3d < 0.80:
            return "Cảnh báo: Chuỗi giảm cạn vol 3 phiên (Grinding No Demand)"

    # 2. Upthrust / False Breakout at recent 20-bar high (BUG-3)
    if cp <= 30.0 and rvol >= 1.2 and (high - close) > (close - low) * 1.5:
        if i >= 5 and high >= max(h[max(0, i-20):i]):
            return "Upthrust / Selling Climax"

    # 3. Low volume conditions (rvol < 0.70)
    if rvol < 0.70:
        if prev_dump and (i >= 1 and close <= c[i-1]):
            return "Cảnh báo: Thiếu cầu trên đà rơi (No Demand)"
        elif prev_climax:
            return "Tạm dừng sau tăng nóng (Inside bar)"
        elif cp >= 35.0 and not prev_dump:
            # Nguyên tắc Wyckoff: No Supply bắt buộc là nến Giảm hoặc Đi ngang (close <= c[i-1]).
            # Nến tăng (close > c[i-1]) cạn vol là Low-vol Up-bar / Thiếu cầu ngắn hạn, không được dán nhãn No Supply.
            if i >= 1 and close > c[i-1]:
                return "Thiếu cầu / Hấp thụ cạn vol (Low-vol Test)"
            return "No Supply chuẩn (Cạn vol giữ nền)"
        elif cp < 35.0:
            return "Trôi cạn vol (Thiếu cầu ngắn hạn)"

    # 4. Test of Supply (Rút chân cạn cung / Hammer)
    if cp >= 60.0 and (high - close) < (close - low) and rvol <= 1.2:
        return "Test of Supply (Rút chân cạn cung)"

    # 5. Stopping Volume / Absorption (chỉ áp dụng khi giá đang giảm hoặc đi ngang có lực đỡ)
    if (prev_dump and cp >= 50.0) or (rvol > 1.8 and cp >= 65.0 and (i >= 1 and close <= c[i-1])):
        return "Chớm dừng rơi (Stopping Volume / Hấp thụ)"

    # 6. SOS / Bùng nổ dòng tiền
    if rvol >= 1.3 and cp >= 65.0 and (i >= 1 and close > c[i-1]):
        open_val = o[i] if i < len(o) else close
        lower_shadow = min(open_val, close) - low
        if spread > 0 and (lower_shadow / spread) >= 0.35:
            return "Bùng nổ rút chân (Bullish Hammer SOS)"
        return "Bùng nổ dòng tiền (SOS tiền lớn vào)"

    # 7. Bearish Pressure
    if cp <= 25.0 or (cp <= 30.0 and rvol >= 1.2):
        return "Chịu áp lực bán ngắn hạn"

    # 8. High volume divergence (Effort vs Result)
    if rvol > 1.8 and 30.0 < cp < 65.0:
        return "Effort vs Result Discrepancy"

    return "Bình thường"


@server.tool()
def get_historical_candles(symbol: str, resolution: str = "1D", count: int = 60) -> list:
    """
    Lấy dữ liệu nến OHLCV kèm các chỉ số tính toán sẵn cho phương pháp Wyckoff/VPA:
    - Spread (High - Low) & Spread % (Biên độ tương đối)
    - Close Position (Vị trí đóng nến theo % biên độ)
    - SMA20 Volume & RVol (Khối lượng tương đối)
    - Tín hiệu nến VPA sơ bộ (No Supply, Test, Stopping Vol, Upthrust...)
    """
    bars = _fetch_dnse_ohlcv(symbol, resolution, count + 20)

    c_list = [b["close"] for b in bars]
    o_list = [b["open"] for b in bars]
    h_list = [b["high"] for b in bars]
    l_list = [b["low"] for b in bars]
    v_list = [b["volume"] for b in bars]

    enriched = []
    for i in range(len(bars)):
        bar = bars[i]
        sma20_vol = compute_clean_sma20_vol(v_list, c_list, o_list, h_list, l_list, i)

        high = bar["high"]
        low = bar["low"]
        close = bar["close"]
        vol = bar["volume"]
        spread = round(high - low, 2)
        spread_pct = round(spread / close * 100, 2) if close > 0 else 0.0
        close_pos = round(((close - low) / spread * 100), 1) if spread > 0 else 50.0
        rvol = round(vol / sma20_vol, 2) if sma20_vol > 0 else 1.0

        vpa_tag = classify_vpa(c_list, o_list, h_list, l_list, v_list, i, sma20_vol)

        enriched.append({
            "date": bar["date"],
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": vol,
            "sma20_vol": int(sma20_vol),
            "spread": spread,
            "spread_pct": spread_pct,
            "close_pos_%": close_pos,
            "rvol": rvol,
            "vpa_tag": vpa_tag
        })

    return enriched[-count:]


@server.tool()
def get_market_depth_and_foreign(symbol: str) -> dict:
    """
    Lấy thông tin giá khớp thời gian thực, 3 mức giá dư mua/dư bán (Order Depth)
    và lịch sử 10-15 phiên giao dịch mua/bán ròng của Khối ngoại (kèm giá trị ròng tính theo Tỷ đồng).
    """
    url = f"https://api-finance-t19.24hmoney.vn/v1/ios/stock/detail?symbol={symbol.upper()}"
    r = requests.get(url, headers=HEADERS, timeout=6)
    if r.status_code != 200:
        raise Exception(f"Không thể truy xuất dữ liệu từ 24hMoney: HTTP {r.status_code}")

    data = r.json().get("data", {})
    sd = data.get("share_detail", {})
    fh = data.get("foreign_trading_history", [])

    foreign_summary = []
    total_net_val = 0.0
    for f in fh[:15]:
        dt = datetime.datetime.fromtimestamp(f.get("trading_date", 0)).strftime("%Y-%m-%d")
        buy_val = round(f.get("buy_foreign_val", 0), 2)
        sell_val = round(f.get("sell_foreign_val", 0), 2)
        net_val = round(buy_val - sell_val, 2)
        total_net_val += net_val
        foreign_summary.append({
            "date": dt,
            "match_price": f.get("match_price"),
            "buy_val_bil": buy_val,
            "sell_val_bil": sell_val,
            "net_val_bil": net_val,
            "status": "MUA RÒNG" if net_val > 0 else "BÁN RÒNG"
        })

    depth = {
        "bid_1": {"price": sd.get("bid_price01"), "volume": sd.get("bid_qtty01")},
        "bid_2": {"price": sd.get("bid_price02"), "volume": sd.get("bid_qtty02")},
        "bid_3": {"price": sd.get("bid_price03"), "volume": sd.get("bid_qtty03")},
        "ask_1": {"price": sd.get("offer_price01"), "volume": sd.get("offer_qtty01")},
        "ask_2": {"price": sd.get("offer_price02"), "volume": sd.get("offer_qtty02")},
        "ask_3": {"price": sd.get("offer_price03"), "volume": sd.get("offer_qtty03")}
    }

    return {
        "symbol": symbol.upper(),
        "company_name": sd.get("company_name"),
        "exchange": sd.get("floor_code"),
        "current_price": sd.get("price"),
        "accumulated_volume": sd.get("accumylated_vol"),
        "accumulated_value_bil": round((sd.get("accumulated_val") or 0) / 1e9, 2),
        "foreign_net_total_15d_bil": round(total_net_val, 2),
        "order_depth": depth,
        "foreign_history": foreign_summary
    }


@server.tool()
def get_relative_strength(symbol: str, count: int = 60) -> dict:
    """
    So sánh hiệu suất giá giữa cổ phiếu và chỉ số VNINDEX trong các khung 10, 20, 60 phiên
    để xác định sức mạnh giá tương đối (RS - Relative Strength theo phương pháp Wyckoff).
    """
    stock_bars = _fetch_dnse_ohlcv(symbol, "1D", count)
    vnindex_bars = _fetch_dnse_ohlcv("VNINDEX", "1D", count)

    if not stock_bars or not vnindex_bars:
        return {"error": "Không đủ dữ liệu để tính RS"}

    def calc_perf(bars, days):
        if len(bars) < days:
            return 0.0
        start = bars[-days]["close"]
        end = bars[-1]["close"]
        return round((end - start) / start * 100, 2)

    perf_10d_stock = calc_perf(stock_bars, 10)
    perf_10d_idx = calc_perf(vnindex_bars, 10)

    perf_20d_stock = calc_perf(stock_bars, 20)
    perf_20d_idx = calc_perf(vnindex_bars, 20)

    perf_60d_stock = calc_perf(stock_bars, 60)
    perf_60d_idx = calc_perf(vnindex_bars, 60)

    rs_10d = round(perf_10d_stock - perf_10d_idx, 2)
    rs_20d = round(perf_20d_stock - perf_20d_idx, 2)
    rs_60d = round(perf_60d_stock - perf_60d_idx, 2)

    return {
        "symbol": symbol.upper(),
        "benchmark": "VNINDEX",
        "current_stock_price": stock_bars[-1]["close"],
        "current_vnindex": vnindex_bars[-1]["close"],
        "performance_comparison": {
            "10_days": {"stock_%": perf_10d_stock, "vnindex_%": perf_10d_idx, "excess_rs_%": rs_10d},
            "20_days": {"stock_%": perf_20d_stock, "vnindex_%": perf_20d_idx, "excess_rs_%": rs_20d},
            "60_days": {"stock_%": perf_60d_stock, "vnindex_%": perf_60d_idx, "excess_rs_%": rs_60d}
        },
        "rs_evaluation": "MẠNH HƠN THỊ TRƯỜNG (Outperforming)" if rs_20d > 0 else "YẾU HƠN THỊ TRƯỜNG (Underperforming)"
    }


@server.tool()
def scan_market_leaders(top_n: int = 15, min_avg_val_bil: float = 10.0, symbols: list = None) -> dict:
    """
    Quét toàn bộ thị trường tìm ra các cổ phiếu dẫn dắt (Market Leaders) mạnh nhất theo điểm Relative Strength (RS Score),
    tương quan khối lượng (RVol), và sức mạnh giá so với VNINDEX.
    Mặc định: Tự động quét Dynamic Universe (các cổ phiếu thanh khoản cao và tốt nhất thị trường).
    Tuỳ chọn: Có thể truyền danh sách 'symbols' tuỳ biến để quét danh mục riêng.
    Bộ lọc thanh khoản: Giá trị giao dịch trung bình 20 phiên (ADTV20) >= min_avg_val_bil (mặc định 10 tỷ VNĐ/phiên).
    """
    d_idx = _fetch_dnse_raw("VNINDEX", "1D", 45)
    if not d_idx or len(d_idx.get("c", [])) < 20:
        return {"error": "Không thể lấy đủ dữ liệu chỉ số VNINDEX"}

    idx_c = d_idx.get("c", [])
    idx_perf_5d = round((idx_c[-1] - idx_c[-5]) / idx_c[-5] * 100, 2)
    idx_perf_20d = round((idx_c[-1] - idx_c[-20]) / idx_c[-20] * 100, 2)

    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()

    # Tải dữ liệu song song đa luồng cho toàn bộ Universe
    stock_data = _fetch_batch_candles(target_universe, days=45, resolution="1D")

    leaders = []
    for sym in target_universe:
        d = stock_data.get(sym)
        if not d:
            continue
        c = d.get("c", [])
        v = d.get("v", [])
        if len(c) < 20 or len(v) < 20:
            continue

        p_cur = c[-1]
        sma20_vol = sum(v[-20:]) / 20
        # ADTV 20 phiên tính bằng Tỷ đồng VNĐ
        avg_val_20d_bil = round(sma20_vol * p_cur / 1e6, 2)
        if avg_val_20d_bil < min_avg_val_bil or sma20_vol < 150000:
            continue

        perf_5d = round((c[-1] - c[-5]) / c[-5] * 100, 2)
        perf_20d = round((c[-1] - c[-20]) / c[-20] * 100, 2)
        rs_5d = round(perf_5d - idx_perf_5d, 2)
        rs_20d = round(perf_20d - idx_perf_20d, 2)

        # Trọng số: 60% cho 20 ngày (trend trung hạn), 40% cho 5 ngày (độ nhạy ngắn hạn)
        rs_score = round(rs_20d * 0.6 + rs_5d * 0.4, 2)

        last_rvol = round(v[-1] / sma20_vol, 2) if sma20_vol > 0 else 1.0
        last_change = round((c[-1] - c[-2]) / c[-2] * 100, 2) if len(c) >= 2 else 0.0

        leaders.append({
            "symbol": sym,
            "sector": get_stock_sector(sym),
            "current_price": p_cur,
            "change_1d_%": last_change,
            "perf_5d_%": perf_5d,
            "perf_20d_%": perf_20d,
            "excess_rs_5d_%": rs_5d,
            "excess_rs_20d_%": rs_20d,
            "rs_score": rs_score,
            "rvol": last_rvol,
            "avg_val_20d_bil": avg_val_20d_bil,
            "avg_vol_20d": int(sma20_vol)
        })

    leaders.sort(key=lambda x: x["rs_score"], reverse=True)

    return {
        "benchmark": {
            "name": "VNINDEX",
            "current_index": idx_c[-1],
            "perf_5d_%": idx_perf_5d,
            "perf_20d_%": idx_perf_20d
        },
        "scanned_count": len(target_universe),
        "qualified_count": len(leaders),
        "universe_type": "Dynamic Market (SSI Live)" if not symbols else "Custom List",
        "top_leaders": leaders[:top_n]
    }


@server.tool()
def scan_high_rr_setups(
    min_rr: float = 1.8,
    max_risk_pct: float = 6.5,
    min_avg_val_bil: float = 15.0,
    top_n: int = 10,
    symbols: list = None
) -> dict:
    """
    Quét toàn bộ thị trường tìm kiếm các cơ hội vào lệnh (Trade Setups) có tỷ lệ Risk:Reward (R:R) thực tế cao nhất,
    tuân thủ nghiêm ngặt quản trị rủi ro tuyệt đối (Absolute Return) và thiết kế cho dòng vốn lớn (Institutional Capital):
    Mặc định: Tự động quét Dynamic Universe (các cổ phiếu thanh khoản cao và tốt nhất thị trường).
    Tuỳ chọn: Có thể truyền danh sách 'symbols' tuỳ biến để quét danh mục riêng.
    1. Bộ lọc Thanh khoản Tuyệt đối (ADTV): Bắt buộc Giá trị giao dịch trung bình 20 phiên >= 15 tỷ VNĐ (chống trượt giá/slippage).
    2. Trend Filter & SMA50 Slope: Bắt buộc giá nằm trên hoặc giữ vững sát SMA50 và độ dốc SMA50 không cắm dốc mạnh.
    3. Bộ lọc Sức mạnh Tương đối (RS Filter): Loại bỏ mã có RS_Score < -5.0% so với VNINDEX.
    4. Phân loại 2 Kịch bản Vào lệnh (Dual Archetype):
       - Setup Type A: NỀN HỖ TRỢ (Range Rebound / LPS) - Mua gần đáy tích lũy, Support Density, Target 1 = đỉnh đóng cửa 40 phiên, SL = Hỗ trợ - (1.0~1.2)*ATR.
       - Setup Type B: VƯỢT ĐỈNH (Breakout / VCP) - Bứt phá đỉnh 40 phiên, lọc Upthrust/False Breakout, Target tính theo Measured Move độ sâu nền giá, SL = Pivot - 1.0*ATR.
    5. VPA Đa phiên (Context-Aware VPA): Xét bối cảnh đa phiên để lọc bỏ tín hiệu No Demand trên đà rơi, Grinding decline, và nến Upthrust.
    6. Xếp hạng Weighted Composite Score: Cân bằng R:R, VPA, RS Score, Support Density và ADTV.
    """
    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()

    # Tải dữ liệu song song đa luồng cho toàn bộ Universe (120 ngày - margin an toàn dịp lễ Tết - BUG-6)
    stock_data = _fetch_batch_candles(target_universe, days=120, resolution="1D")

    # Lấy dữ liệu VNINDEX để tính RS Score inline (Cross-skill integration - Mục 2.A2 & 9.C)
    d_idx = _fetch_dnse_raw("VNINDEX", "1D", 45)
    idx_perf_5d = 0.0
    idx_perf_20d = 0.0
    if d_idx and len(d_idx.get("c", [])) >= 20:
        idx_c = d_idx.get("c", [])
        idx_perf_5d = (idx_c[-1] - idx_c[-5]) / idx_c[-5] * 100.0 if idx_c[-5] > 0 else 0.0
        idx_perf_20d = (idx_c[-1] - idx_c[-20]) / idx_c[-20] * 100.0 if idx_c[-20] > 0 else 0.0

    # Danh sách VPA tiêu cực loại bỏ setup (BUG-1)
    BEARISH_VPA = [
        "Cảnh báo: Thiếu cầu trên đà rơi (No Demand)",
        "Cảnh báo: Chuỗi giảm cạn vol 3 phiên (Grinding No Demand)",
        "Chịu áp lực bán ngắn hạn",
        "Trôi cạn vol (Thiếu cầu ngắn hạn)",
        "Upthrust / Selling Climax"
    ]

    setups = []
    for sym in target_universe:
        d = stock_data.get(sym)
        if not d:
            continue
        c = d.get("c", [])
        o = d.get("o", [])
        h = d.get("h", [])
        l = d.get("l", [])
        v = d.get("v", [])
        if len(c) < 55 or len(v) < 55:
            continue

        p_cur = c[-1]

        # 1. Bộ lọc Thanh khoản Tuyệt đối (ADTV - Giá trị giao dịch trung bình 20 phiên, lọc limit day BUG-5):
        sma20_vol = compute_clean_sma20_vol(v, c, o, h, l, len(c) - 1)
        avg_val_20d_bil = round(sma20_vol * p_cur / 1e6, 2)
        if avg_val_20d_bil < min_avg_val_bil or sma20_vol < 200000:
            continue

        # 2. Trend Filter Nâng cao (Độ dốc & Vị thế SMA50):
        sma50 = sum(c[-50:]) / 50.0
        sma50_prev5 = sum(c[-55:-5]) / 50.0
        slope_5d = round((sma50 - sma50_prev5) / sma50_prev5 * 100.0, 2)
        if slope_5d < -1.0:  # SMA50 cắm dốc mạnh xuống
            continue
        if p_cur < sma50 * 0.965:  # Nằm quá sâu dưới SMA50
            continue

        # 3. Bộ lọc Sức mạnh Tương đối (RS Filter vs VNINDEX - Mục 2.A2 & 9.C):
        perf_5d = (c[-1] - c[-5]) / c[-5] * 100.0 if c[-5] > 0 else 0.0
        perf_20d = (c[-1] - c[-20]) / c[-20] * 100.0 if c[-20] > 0 else 0.0
        rs_5d = round(perf_5d - idx_perf_5d, 2)
        rs_20d = round(perf_20d - idx_perf_20d, 2)
        rs_score = round(rs_20d * 0.6 + rs_5d * 0.4, 2)
        if rs_score < -5.0:  # LOẠI BỎ mã underperforming thị trường quá nhiều
            continue

        # 4. Dynamic Stop Loss bằng ATR_14 (Wilder Smoothing chuẩn xác - BUG-12):
        atr14 = compute_wilder_atr14(c, h, l)

        # 5. Nhận diện VPA Đa phiên (Context-Aware VPA - BUG-1, BUG-3, BUG-4):
        last_spread = round(h[-1] - l[-1], 2)
        last_cp = round((c[-1] - l[-1]) / last_spread * 100.0, 1) if last_spread > 0 else 50.0
        last_rvol = round(v[-1] / sma20_vol, 2) if sma20_vol > 0 else 1.0

        vpa_status = classify_vpa(c, o, h, l, v, len(c) - 1, sma20_vol)

        # BUG-1: Loại bỏ ngay mã có tín hiệu VPA tiêu cực
        if vpa_status in BEARISH_VPA:
            continue

        prior_40_close_high = max(c[-41:-1])
        prior_40_high = max(h[-41:-1])
        base_low_40 = min(l[-41:-1])  # BUG-2: Loại trừ nến hiện tại để tránh phồng base_depth

        # 6. Phân loại Kịch bản (Archetype Classification):
        if p_cur >= prior_40_close_high * 0.985:
            # Kịch bản B: VƯỢT ĐỈNH NỀN GIÁ / VCP PIVOT
            # BUG-3: Kiểm tra Upthrust / False Breakout tại vùng Breakout
            if last_cp <= 30.0 and last_rvol >= 1.2:
                continue

            setup_type = "VƯỢT ĐỈNH (Breakout / VCP)"
            pivot = prior_40_close_high
            base_depth = round(pivot - base_low_40, 2)

            # BUG-7: Target validity cho Breakout - nền phải đủ sâu
            if base_depth < 1.5 * atr14:
                continue

            stop_loss = round(pivot - 1.0 * atr14, 2)
            if p_cur - stop_loss < 0.8 * atr14:
                stop_loss = round(p_cur - 1.0 * atr14, 2)
            risk_pct = round((p_cur - stop_loss) / p_cur * 100.0, 2)

            target_1 = round(p_cur + base_depth * 0.8, 2)
            target_2 = round(p_cur + base_depth * 1.3, 2)
            reward_1_pct = round((target_1 - p_cur) / p_cur * 100.0, 2)
            reward_2_pct = round((target_2 - p_cur) / p_cur * 100.0, 2)
            pivot_or_support = pivot
            support_density = 0
            support_tag = "[BREAKOUT_PIVOT]"
        else:
            # Kịch bản A: NỀN HỖ TRỢ / RANGE REBOUND (Wyckoff Spring / LPS)
            setup_type = "NỀN HỖ TRỢ (Range Rebound)"
            prior_support_15d = min(l[-16:-1])

            # NGUYÊN TẮC: Nếu giá đóng cửa thủng hỗ trợ 15 phiên trước -> LOẠI BỎ NGAY
            if p_cur < prior_support_15d:
                continue

            dist_to_sup_pct = round((p_cur - prior_support_15d) / prior_support_15d * 100.0, 2)
            if dist_to_sup_pct > 5.0:
                continue

            # Nâng cấp Mục 2.A1: Đánh giá Support Density trong 40 phiên trước
            support_density = sum(1 for low_val in l[-41:-1] if abs(low_val - prior_support_15d) / prior_support_15d <= 0.015)
            if support_density < 2:
                support_tag = "[WEAK_SUPPORT]"
                buffer_atr = 1.2 * atr14
            else:
                support_tag = "[STRONG_SUPPORT]"
                buffer_atr = 1.0 * atr14

            stop_loss = round(prior_support_15d - buffer_atr, 2)
            risk_pct = round((p_cur - stop_loss) / p_cur * 100.0, 2)

            target_1 = prior_40_close_high
            target_2 = prior_40_high
            reward_1_pct = round((target_1 - p_cur) / p_cur * 100.0, 2)
            reward_2_pct = round((target_2 - p_cur) / p_cur * 100.0, 2)
            pivot_or_support = prior_support_15d

        # Kiểm tra ngưỡng chịu rủi ro và biên lợi nhuận khả thi
        if risk_pct <= 0 or risk_pct > max_risk_pct or reward_1_pct < 3.5:
            continue

        risk_val = p_cur - stop_loss
        rr_1 = round((target_1 - p_cur) / risk_val, 2) if risk_val > 0 else 0.0
        rr_2 = round((target_2 - p_cur) / risk_val, 2) if risk_val > 0 else 0.0
        if rr_1 < min_rr:
            continue

        # 7. Tính điểm Xếp hạng Toàn diện (Weighted Composite Score - Mục 2.E):
        rr_1_norm = min(1.0, max(0.0, (rr_1 - 1.8) / 3.2))
        if vpa_status in ["Bùng nổ dòng tiền (SOS tiền lớn vào)", "Chớm dừng rơi (Stopping Volume / Hấp thụ)"]:
            vpa_score_norm = 1.0
        elif vpa_status == "Test of Supply (Rút chân cạn cung)":
            vpa_score_norm = 0.85
        elif vpa_status == "No Supply chuẩn (Cạn vol giữ nền)":
            vpa_score_norm = 0.80
        else:
            vpa_score_norm = 0.50

        rs_score_norm = min(1.0, max(0.0, (rs_score - (-5.0)) / 20.0))
        support_density_norm = 0.70 if setup_type.startswith("VƯỢT ĐỈNH") else min(1.0, support_density / 5.0)
        adtv_norm = min(1.0, max(0.0, (avg_val_20d_bil - 15.0) / 85.0))
        rs_bonus = 0.05 if rs_score >= 0 else 0.0

        composite_score = round(
            min(1.0, 0.35 * rr_1_norm + 0.25 * vpa_score_norm + 0.20 * rs_score_norm + 0.10 * support_density_norm + 0.10 * adtv_norm + rs_bonus),
            3
        )

        trend_label = "Uptrend (>SMA50)" if p_cur >= sma50 else "Tích lũy sát SMA50"
        setups.append({
            "symbol": sym,
            "sector": get_stock_sector(sym),
            "setup_type": setup_type,
            "current_price": p_cur,
            "trend": trend_label,
            "slope_5d_sma50_%": slope_5d,
            "rs_score": rs_score,
            "support_or_pivot": pivot_or_support,
            "support_density": support_density,
            "support_tag": support_tag,
            "atr_14": round(atr14, 2),
            "stop_loss": stop_loss,
            "target_1_conservative": target_1,
            "target_2_optimistic": target_2,
            "risk_pct": risk_pct,
            "reward_1_pct": reward_1_pct,
            "reward_2_pct": reward_2_pct,
            "rr_1_conservative": rr_1,
            "rr_2_optimistic": rr_2,
            "composite_score": composite_score,
            "rvol": last_rvol,
            "close_pos_%": last_cp,
            "vpa_status": vpa_status,
            "avg_val_20d_bil": avg_val_20d_bil,
            "avg_vol_20d": int(sma20_vol)
        })

    # Xếp hạng ưu tiên theo Composite Score, sau đó đến rr_1_conservative
    setups.sort(key=lambda x: (x["composite_score"], x["rr_1_conservative"]), reverse=True)

    return {
        "scanned_count": len(target_universe),
        "qualified_count": len(setups),
        "universe_type": "Dynamic Market (SSI Live)" if not symbols else "Custom List",
        "methodology": {
            "liquidity_filter": f"ADTV >= {min_avg_val_bil} tỷ VNĐ/phiên (Chống trượt giá cho vốn lớn)",
            "trend_filter": "Price >= SMA50 * 0.965 & SMA50 Slope 5D >= -1.0%",
            "rs_filter": "RS_Score = 0.6*RS_20D + 0.4*RS_5D >= -5.0% vs VNINDEX",
            "dual_archetypes": "Type A (Range Rebound mua sát hỗ trợ) & Type B (Breakout/VCP theo Measured Move)",
            "support_density": "Mật độ test đáy 40 phiên: Weak Support (<2 touch -> buffer 1.2*ATR14) vs Strong Support (>=3 touch -> buffer 1.0*ATR14)",
            "dynamic_stop_loss": "Support/Pivot - 1.0 * ATR14 (hoặc 1.2 * ATR14 nếu Weak Support)",
            "context_aware_vpa": "Phân tích đa phiên (Grinding No Demand, Upthrust, No Supply, Stopping Vol, SOS)",
            "composite_ranking": "Composite = 0.35*RR1 + 0.25*VPA + 0.20*RS + 0.10*SupportDensity + 0.10*ADTV"
        },
        "top_setups": setups[:top_n]
    }


@server.tool()
def scan_wyckoff_phase_c_d(
    min_rr: float = 1.8,
    max_risk_pct: float = 6.5,
    min_avg_val_bil: float = 15.0,
    top_n: int = 10,
    symbols: list = None
) -> dict:
    """
    Quét tự động toàn bộ thị trường tìm kiếm các cơ hội giải ngân rủi ro cực thấp theo Wyckoff (V7.0):
    1. Test of Spring / Terminal Shakeout (Pha C): Mua đón lõng tại nhịp test đáy rũ bỏ cạn cung (Higher Low / Double Bottom).
    2. BU / LPS (Pha D): Mua tại nhịp điều chỉnh pullback cạn cung ở nửa trên Trading Range sau khi có SOS xác nhận.
    Mặc định: Tự động quét Dynamic Universe (các cổ phiếu thanh khoản cao và tốt nhất thị trường).
    Tuỳ chọn: Có thể truyền danh sách 'symbols' tuỳ biến để quét danh mục riêng.
    Bộ lọc thanh khoản: ADTV >= 15 tỷ VNĐ/phiên cho dòng vốn lớn.
    """
    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()

    # Tải dữ liệu song song đa luồng cho toàn bộ Universe (220 ngày để đủ tối thiểu 130 nến trading)
    stock_data = _fetch_batch_candles(target_universe, days=220, resolution="1D")

    setups = []
    for sym in target_universe:
        d = stock_data.get(sym)
        if not d:
            continue
        c = d.get("c", [])
        h = d.get("h", [])
        l = d.get("l", [])
        v = d.get("v", [])
        if len(c) < 120 or len(v) < 120:
            continue

        p_cur = c[-1]

        # 1. Thanh khoản Dòng vốn lớn (ADTV20):
        sma20_vol = sum(v[-20:]) / 20
        avg_val_20d_bil = round(sma20_vol * p_cur / 1e6, 2)
        if avg_val_20d_bil < min_avg_val_bil or sma20_vol < 200000:
            continue

        # 2. Bộ lọc Xu hướng (Trend Filter linh hoạt):
        sma50 = sum(c[-50:]) / 50
        sma50_prev5 = sum(c[-55:-5]) / 50
        slope_5d = round((sma50 - sma50_prev5) / sma50_prev5 * 100, 2)
        if slope_5d < -1.5:  # Loại bỏ Downtrend dốc đứng
            continue

        # 3. Tính ATR14 (Bao gồm phiên hiện tại):
        tr_list = []
        for i in range(len(c) - 14, len(c)):
            tr = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
            tr_list.append(tr)
        atr14 = sum(tr_list) / 14

        # 4. Bản vá 1 (Gắn cờ Regime Counter-Trend):
        # Peak_Old = max(High[-120:-60]), Peak_New = max(High[-60:-20])
        peak_old = max(h[-120:-60])
        peak_new = max(h[-60:-20])
        is_counter_trend = (peak_new < peak_old * 0.95)
        position_sizing = "Giảm 50% quy mô (Half-size)" if is_counter_trend else "Full-size"

        # 5. Bản vá 2 (Snapshot Hộp TR & Đo lường Stationarity trên 3 rolling windows):
        tr_p_high = max(c[-90:-20])
        tr_p_low = min(c[-90:-20])
        tr_s1_high = max(c[-100:-25])
        tr_s2_high = max(c[-80:-15])

        drift_1 = abs(tr_p_high - tr_s1_high) / tr_p_high
        drift_2 = abs(tr_p_high - tr_s2_high) / tr_p_high
        is_box_unstable = (drift_1 > 0.05 or drift_2 > 0.05)
        box_status = "Unstable" if is_box_unstable else "Ổn định"

        tr_high = tr_p_high
        tr_low = tr_p_low
        tr_mid = round((tr_high + tr_low) / 2.0, 2)

        # 6. Bản vá 3 (Vùng Cung Major Supply lookback 130 phiên):
        lookback_sup = min(130, len(h) - 1)
        major_supply = max(h[-lookback_sup:-1])

        # Các thông số VPA phiên hiện tại T0:
        last_spread = round(h[-1] - l[-1], 2)
        last_cp = round((c[-1] - l[-1]) / last_spread * 100, 1) if last_spread > 0 else 50.0
        last_rvol = round(v[-1] / sma20_vol, 2)

        # Thông số phiên T-1:
        prev_spread = round(h[-2] - l[-2], 2)
        prev_cp = round((c[-2] - l[-2]) / prev_spread * 100, 1) if prev_spread > 0 else 50.0
        prev_rvol = round(v[-2] / sma20_vol, 2)
        prev_dump = (c[-2] < c[-3] and prev_cp <= 30.0 and prev_rvol >= 1.1)

        setup_found = None

        # --- KIỂM TRA SETUP 1: TEST OF SPRING / TERMINAL SHAKEOUT (PHA C) ---
        event_low = min(l[-25:-5])
        if event_low <= tr_low * 1.02 and (event_low <= p_cur <= event_low * 1.06):
            test_low = min(l[-4:])
            # Đáy test giữ được đáy Spring (Higher Low hoặc Double Bottom)
            if test_low >= event_low * 0.995:
                # VPA Cạn cung: Volume thấp, không phải xả hoảng loạn
                if last_rvol < 0.75 and not (prev_dump and c[-1] <= c[-2]):
                    sl = round(event_low - 0.8 * atr14, 2)
                    if p_cur - sl < 0.8 * atr14:
                        sl = round(p_cur - 1.0 * atr14, 2)

                    risk_pct = round((p_cur - sl) / p_cur * 100, 2)
                    tp1 = tr_mid
                    reward_1_pct = round((tp1 - p_cur) / p_cur * 100, 2)

                    # Chiết khấu Target 2 & Check Box Unstable
                    if is_box_unstable:
                        tp2 = None
                        reward_2_pct = None
                        rr2 = None
                        target_2_note = "Hộp không ổn định (Unstable)"
                    else:
                        tp2_raw = tr_high
                        if tp2_raw >= major_supply * 0.97:
                            tp2 = round(major_supply * 0.98, 2)
                            target_2_note = "Bị giới hạn bởi Supply Zone cũ"
                        else:
                            tp2 = tp2_raw
                            target_2_note = "Kháng cự đỉnh hộp TR"
                        reward_2_pct = round((tp2 - p_cur) / p_cur * 100, 2)
                        rr2 = round(reward_2_pct / risk_pct, 2) if risk_pct > 0 else None

                    if risk_pct > 0 and risk_pct <= max_risk_pct and reward_1_pct >= 3.0:
                        rr1 = round(reward_1_pct / risk_pct, 2)
                        if rr1 >= min_rr:
                            vpa_desc = "Test lại đáy Spring cạn vol giữ nền" if last_cp >= 35.0 else "Test đáy Spring vol thấp"
                            base_type = "Test of Spring (Pha C)"
                            tags = []
                            if is_counter_trend:
                                tags.append("[Counter-Trend]")
                            if is_box_unstable:
                                tags.append("[Box Unstable]")
                            setup_type_full = f"{base_type} {' '.join(tags)}".strip()

                            setup_found = {
                                "symbol": sym,
                                "sector": get_stock_sector(sym),
                                "setup_type": setup_type_full,
                                "box_status": box_status,
                                "position_sizing": position_sizing,
                                "current_price": p_cur,
                                "event_low": round(event_low, 2),
                                "tr_low": tr_low,
                                "tr_mid": tr_mid,
                                "tr_high": tr_high,
                                "slope_5d_sma50_%": slope_5d,
                                "vpa_context": vpa_desc,
                                "stop_loss": sl,
                                "risk_pct": risk_pct,
                                "target_1": tp1,
                                "target_2": tp2,
                                "target_2_note": target_2_note,
                                "reward_1_pct": reward_1_pct,
                                "reward_2_pct": reward_2_pct,
                                "rr_1": rr1,
                                "rr_2": rr2,
                                "tranche_1_entry": p_cur,
                                "tranche_1_sl": sl,
                                "tranche_2_trigger": tr_mid,
                                "tranche_2_sl": round(event_low, 2),
                                "rvol": last_rvol,
                                "close_pos_%": last_cp,
                                "adtv_20_bil": avg_val_20d_bil
                            }

        # --- KIỂM TRA SETUP 2: BU / LPS (PHA D) ---
        if not setup_found:
            # 1. Tìm sự kiện Minor SOS trong 15 phiên qua:
            # Siết điều kiện: RVol >= 1.25, c > c-1, và %CP >= 66% (đóng 1/3 trên biên độ)
            has_sos = any(
                h[i] >= tr_mid
                and (v[i] / sma20_vol) >= 1.25
                and c[i] > c[i-1]
                and (h[i] - l[i] > 0)
                and ((c[i] - l[i]) / (h[i] - l[i])) >= 0.66
                for i in range(len(c) - 15, len(c) - 1)
            )
            if has_sos and p_cur >= tr_mid * 0.98:
                sos_high = max(h[-15:])
                # Đang điều chỉnh lành mạnh từ đỉnh SOS
                if p_cur <= sos_high * 0.99:
                    # VPA Cạn cung: Volume nhịp test nhỏ (<0.75), không bị bán tháo ở T-1
                    if last_rvol < 0.75 and not (prev_dump and c[-1] <= c[-2]):
                        recent_low_5d = min(l[-6:-1])
                        sl_cand = round(max(recent_low_5d - 0.5 * atr14, tr_mid - 0.8 * atr14), 2)
                        sl = sl_cand if (p_cur - sl_cand) >= 0.8 * atr14 else round(p_cur - 1.0 * atr14, 2)
                        risk_pct = round((p_cur - sl) / p_cur * 100, 2)

                        tp1 = sos_high
                        reward_1_pct = round((tp1 - p_cur) / p_cur * 100, 2)

                        # Bản vá 2 & 3: Chiết khấu Target 2 theo Supply Zone và kiểm tra Box Unstable
                        target_2_raw = round(tr_high + (tr_high - tr_low) * 0.5, 2)
                        if is_box_unstable:
                            tp2 = None
                            reward_2_pct = None
                            rr2 = None
                            target_2_note = "Hộp không ổn định (Unstable)"
                        else:
                            if target_2_raw >= major_supply * 0.97:
                                tp2 = round(major_supply * 0.98, 2)
                                target_2_note = "Bị giới hạn bởi Supply Zone cũ"
                            else:
                                tp2 = target_2_raw
                                target_2_note = "Mục tiêu theo Measured Move"
                            reward_2_pct = round((tp2 - p_cur) / p_cur * 100, 2)
                            rr2 = round(reward_2_pct / risk_pct, 2) if risk_pct > 0 else None

                        if risk_pct > 0 and risk_pct <= max_risk_pct and reward_1_pct >= 3.0:
                            rr1 = round(reward_1_pct / risk_pct, 2)
                            if rr1 >= min_rr:
                                vpa_desc = "LPS rút chân cạn cung ở nửa trên Hộp" if last_cp >= 50.0 else "Pullback LPS cạn vol"
                                base_type = "BU / LPS (Pha D)"
                                tags = []
                                if is_counter_trend:
                                    tags.append("[Counter-Trend]")
                                if is_box_unstable:
                                    tags.append("[Box Unstable]")
                                setup_type_full = f"{base_type} {' '.join(tags)}".strip()

                                setup_found = {
                                    "symbol": sym,
                                    "sector": get_stock_sector(sym),
                                    "setup_type": setup_type_full,
                                    "box_status": box_status,
                                    "position_sizing": position_sizing,
                                    "current_price": p_cur,
                                    "tr_low": tr_low,
                                    "tr_mid": tr_mid,
                                    "tr_high": tr_high,
                                    "slope_5d_sma50_%": slope_5d,
                                    "vpa_context": vpa_desc,
                                    "stop_loss": sl,
                                    "risk_pct": risk_pct,
                                    "target_1": tp1,
                                    "target_2": tp2,
                                    "target_2_note": target_2_note,
                                    "reward_1_pct": reward_1_pct,
                                    "reward_2_pct": reward_2_pct,
                                    "rr_1": rr1,
                                    "rr_2": rr2,
                                    "tranche_1_entry": p_cur,
                                    "tranche_1_sl": sl,
                                    "tranche_2_trigger": tr_high,
                                    "tranche_2_sl": tr_mid,
                                    "rvol": last_rvol,
                                    "close_pos_%": last_cp,
                                    "adtv_20_bil": avg_val_20d_bil
                                }

        if setup_found:
            setups.append(setup_found)

    setups.sort(key=lambda x: x["rr_1"], reverse=True)
    return {
        "scanned_count": len(target_universe),
        "qualified_count": len(setups),
        "universe_type": "Dynamic Market (SSI Live)" if not symbols else "Custom List",
        "methodology": {
            "trading_range": "Hộp Tích lũy 90 phiên [-90:-20] (TR_Low, TR_Mid, TR_High) kiểm tra Stationarity 3 khung",
            "setup_phase_c": "Test of Spring / Shakeout (Mua đáy test cạn cung, SL dưới Spring)",
            "setup_phase_d": "BU / LPS (Mua pullback cạn cung ở nửa trên TR sau Minor SOS lọc %CP >= 66%)",
            "liquidity_filter": f"ADTV >= {min_avg_val_bil} tỷ VNĐ/phiên",
            "risk_management": "Dynamic ATR14 Stop Loss + Buffer chống whipsaw 0.8*ATR + Tranche Scaling 2 giai đoạn",
            "disclaimer": "Setup: anticipatory mid-range long (rule-based), chưa xác nhận Pha D cổ điển; xác nhận khi close > Kháng cự; phủ định khi chạm Stop Loss."
        },
        "top_setups": setups[:top_n]
    }


@server.tool()
def scan_wfe_v3(
    symbols: list = None,
    min_avg_val_bil: float = 15.0,
    min_p_success: float = 0.45,
    top_n: int = 10
) -> dict:
    """
    Quét cơ hội giải ngân theo Đặc tả kỹ thuật & vận hành WFE V3.0 (Wyckoff x Flow Expectancy System).
    Ba Engine độc lập (Flow, Structure, Volume) hội tụ tại tầng Policy ra quyết định theo Expectancy (EV)
    và xác suất p_success.
    Quản trị rủi ro đa tầng (Tranche Scaling T0/T1/T2, Dynamic ATR Stop Loss, Exit Ladder) và Output Schema chuẩn L5.
    """
    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()
    stock_data = _fetch_batch_candles(target_universe, days=220, resolution="1D")

    scanner = WFEScanner()
    candles_map = {}
    for sym in target_universe:
        d = stock_data.get(sym)
        if not d:
            continue
        c = d.get("c", [])
        o = d.get("o", [])
        h = d.get("h", [])
        l = d.get("l", [])
        v = d.get("v", [])
        t = d.get("t", [])
        if len(c) < 70 or len(v) < 70:
            continue

        sym_candles = []
        for i in range(len(c)):
            dt_str = datetime.datetime.fromtimestamp(t[i]).strftime("%Y-%m-%d") if i < len(t) else f"T_{i}"
            sym_candles.append({
                "date": dt_str,
                "open": o[i],
                "high": h[i],
                "low": l[i],
                "close": c[i],
                "volume": v[i]
            })
        candles_map[sym] = sym_candles

    return scanner.scan_universe(
        candles_by_symbol=candles_map,
        top_n=top_n,
        min_p_success=min_p_success,
        min_avg_val_bil=min_avg_val_bil
    )


@server.tool()
def scan_mcdx_radar(
    mode: str = "both",
    strength_tier: str = "strong",
    min_adtv_billion: float = 15.0,
    top_n: int = 20,
    symbols: list = None
) -> dict:
    """
    SKILL_9 — MCDX Flow Radar: Quét danh sách cổ phiếu theo dòng tiền tạo lập (tiêu chuẩn WFE V3.0).
    2 chế độ:
    - ESTABLISHED: Đã có dòng tiền tạo lập hiện diện và duy trì (thỏa E1-E4, loại spike limit-day).
    - EMERGING: Bắt đầu có dòng tiền tham gia (G1 vào công khai HOẶC G2 gom bí mật).
    - BOTH: Hợp nhất và gắn tag từng dòng.
    Xếp hạng theo chỉ số Banker Intensity Index (BII 0-100).
    """
    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()
    stock_data = _fetch_batch_candles(target_universe, days=120, resolution="1D")

    radar = MCDXFlowRadar()
    candles_map = {}
    for sym in target_universe:
        d = stock_data.get(sym)
        if not d:
            continue
        c = d.get("c", [])
        o = d.get("o", [])
        h = d.get("h", [])
        l = d.get("l", [])
        v = d.get("v", [])
        t = d.get("t", [])
        if len(c) < 70 or len(v) < 70:
            continue

        sym_candles = []
        for i in range(len(c)):
            dt_str = datetime.datetime.fromtimestamp(t[i]).strftime("%Y-%m-%d") if i < len(t) else f"T_{i}"
            sym_candles.append({
                "date": dt_str,
                "open": o[i],
                "high": h[i],
                "low": l[i],
                "close": c[i],
                "volume": v[i]
            })
        candles_map[sym] = sym_candles

    out = radar.scan_radar(
        candles_by_symbol=candles_map,
        mode=mode,
        strength_tier=strength_tier,
        min_adtv_billion=min_adtv_billion,
        top_n=top_n
    )
    return out.to_dict()


if __name__ == "__main__":
    server.run(transport="stdio")

