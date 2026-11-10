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
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
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


def compute_wilder_rsi14(c: list) -> float:
    """Computes Wilder's 14-period RSI from closing prices."""
    n = len(c)
    if n < 15:
        return 50.0
    gains = []
    losses = []
    for i in range(1, n):
        diff = c[i] - c[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    avg_gain = sum(gains[:14]) / 14.0
    avg_loss = sum(losses[:14]) / 14.0
    for i in range(14, len(gains)):
        avg_gain = (avg_gain * 13.0 + gains[i]) / 14.0
        avg_loss = (avg_loss * 13.0 + losses[i]) / 14.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)


def compute_volume_trend_5d(v: list, c: list, h: list, l: list, sma20_vol: float) -> tuple:
    """
    Analyzes 5-session volume slope & price-volume behavior:
    Returns (volume_trend_tag, normalized_score_0_to_1).
    """
    if len(v) < 6 or sma20_vol <= 0:
        return "[NEUTRAL_VOL]", 0.60
    v5 = v[-5:]
    c5 = c[-5:]
    h5 = h[-5:]
    l5 = l[-5:]
    # Linear regression slope over 5 sessions normalized by sma20_vol
    x_mean = 2.0
    y_mean = sum(v5) / 5.0
    cov = sum((idx - x_mean) * (val - y_mean) for idx, val in enumerate(v5))
    var = sum((idx - x_mean) ** 2 for idx in range(5))
    slope_norm = (cov / var) / sma20_vol if var > 0 else 0.0

    avg_rvol_3d = sum(v[-3:]) / (3.0 * sma20_vol)
    last_spread = h5[-1] - l5[-1]
    last_cp = ((c5[-1] - l5[-1]) / last_spread * 100.0) if last_spread > 0 else 50.0
    price_chg_5d = (c5[-1] - c5[0]) / c5[0] * 100.0 if c5[0] > 0 else 0.0

    # Dry-up accumulation: volume contracting while price holds support / tight range
    if slope_norm <= -0.05 and avg_rvol_3d <= 0.85 and price_chg_5d >= -2.5 and last_cp >= 40.0:
        return "[DRY_UP_ACCUMULATION]", 1.0
    # Bullish volume expansion: rising volume with strong closes
    if slope_norm >= 0.08 and price_chg_5d > 0.5 and last_cp >= 60.0:
        return "[BULLISH_VOL_EXPANSION]", 0.90
    # Hidden distribution: volume swelling on weak closes or stalling near highs
    if slope_norm >= 0.08 and last_cp <= 42.0 and avg_rvol_3d >= 1.15:
        return "[HIDDEN_DISTRIBUTION]", 0.15
    return "[NEUTRAL_VOL]", 0.65


def evaluate_vnindex_regime(d_idx: dict = None) -> dict:
    """
    Evaluates the 3-Tier Market Regime Filter (VN-Index vs SMA50, Slope5D, Distribution Days)
    to prevent macro wipeouts (like Oct 28) while allowing high-conviction Phase C Springs.
    """
    if d_idx is None:
        d_idx = _fetch_dnse_raw("VNINDEX", "1D", 100)
    if not d_idx or not d_idx.get("c"):
        return {
            "tier": "BULL",
            "status_label": "NORMAL (Fallback)",
            "current_index": 0.0,
            "sma20": 0.0,
            "sma50": 0.0,
            "dist_to_sma50_%": 0.0,
            "slope_5d_sma50_%": 0.0,
            "perf_5d_%": 0.0,
            "perf_20d_%": 0.0,
            "distribution_days_10d": 0,
            "max_portfolio_nav_pct": 100.0,
            "size_multiplier": 1.0,
            "allow_breakout": True,
            "regime_guidance": "Đủ điều kiện giải ngân tiêu chuẩn.",
            "when_not_to_buy_market": [],
            "when_must_sell_market": []
        }

    idx_c = d_idx.get("c", [])
    idx_h = d_idx.get("h", idx_c)
    idx_l = d_idx.get("l", idx_c)
    idx_v = d_idx.get("v", [1.0] * len(idx_c))
    n = len(idx_c)
    cur_idx = round(idx_c[-1], 2)

    sma20 = round(sum(idx_c[-20:]) / min(n, 20), 2)
    sma50 = round(sum(idx_c[-50:]) / min(n, 50), 2)
    if n >= 55:
        sma50_prev5 = sum(idx_c[-55:-5]) / 50.0
    elif n >= 10:
        sma50_prev5 = sum(idx_c[:-5]) / max(1, len(idx_c[:-5]))
    else:
        sma50_prev5 = sma50

    slope_5d = round((sma50 - sma50_prev5) / sma50_prev5 * 100.0, 2) if sma50_prev5 > 0 else 0.0
    dist_sma50_pct = round((cur_idx - sma50) / sma50 * 100.0, 2) if sma50 > 0 else 0.0
    perf_5d = round((idx_c[-1] - idx_c[-5]) / idx_c[-5] * 100.0, 2) if n >= 5 and idx_c[-5] > 0 else 0.0
    perf_20d = round((idx_c[-1] - idx_c[-20]) / idx_c[-20] * 100.0, 2) if n >= 20 and idx_c[-20] > 0 else 0.0

    # Count distribution days in last 10 sessions (drop <= -0.35% on higher volume than prior day)
    dist_days = 0
    start_k = max(1, n - 10)
    for k in range(start_k, n):
        chg = (idx_c[k] - idx_c[k - 1]) / idx_c[k - 1] * 100.0 if idx_c[k - 1] > 0 else 0.0
        if chg <= -0.35 and k < len(idx_v) and idx_v[k] >= idx_v[k - 1] * 0.98:
            dist_days += 1

    last_sp = (idx_h[-1] - idx_l[-1]) if idx_h and idx_l else 0.0
    last_cp = ((cur_idx - idx_l[-1]) / last_sp * 100.0) if last_sp > 0 else 50.0

    if cur_idx >= sma50 and slope_5d >= -0.5 and dist_days <= 3:
        tier = "BULL"
        status_label = "BULL (VN-Index >= SMA50 — Xu hướng Ủng hộ)"
        max_nav = 100.0
        size_mult = 1.0
        allow_breakout = True
        guidance = (
            "VN-Index nằm trên SMA50 với cấu trúc ổn định: Cho phép giải ngân tối đa 100% NAV "
            "(tối đa 20-25% NAV/mã), mở cả kèo Nền hỗ trợ (Type A / Pha C) và Vượt đỉnh/LPS (Type B / Pha D)."
        )
        no_buy_market = [
            "KHÔNG mua đuổi (FOMO) cổ phiếu đã tăng > 1.5*ATR14 khỏi nền hoặc có RSI >= 68.",
            "KHÔNG giải ngân quá 25% NAV vào 1 cổ phiếu đơn lẻ hoặc quá 35% NAV vào cùng 1 ngành."
        ]
        must_sell_market = [
            "Chốt lời 50% khi chạm Target 1, nâng Trailing Stop lên max(Giá vốn, min(Low 3 phiên)).",
            "Bán 100% nếu giá đóng cửa thủng Operative SL (trừ khi thỏa đủ 5 điều kiện Spring Wash-out Guard)."
        ]
    elif cur_idx >= sma50 * 0.96 and not (cur_idx < sma50 and slope_5d < -1.0 and dist_days >= 4):
        tier = "CAUTION"
        status_label = "CAUTION (VN-Index dưới/quanh SMA50 hoặc phân phối ngắn hạn)"
        max_nav = 40.0
        size_mult = 0.5
        allow_breakout = False
        guidance = (
            "VN-Index đang dưới nhẹ SMA50 hoặc xuất hiện áp lực phân phối: CẮT TRẦN TỔNG DANH MỤC <= 40% NAV "
            "(tối đa 10-12.5% NAV/mã, giữ >= 60% tiền mặt). KHÓA HOÀN TOÀN LỆNH MUA BREAKOUT (Type B); "
            "chỉ giải ngân thăm dò tại Hỗ trợ cứng / Pha C Spring cho cổ phiếu có RS_Score >= +3% và dòng tiền MCDX Red > 5."
        )
        no_buy_market = [
            "CẤM TUYỆT ĐỐI mua Breakout vượt đỉnh (Type B) khi VN-Index dưới SMA50 (rủi ro Bull-trap/Upthrust T+2.5 rất cao).",
            "CẤM mua cổ phiếu yếu hơn thị trường (RS_Score < +3%) hoặc chưa có dòng tiền tạo lập (MCDX Red <= 5).",
            "CẤM nâng tổng tỷ trọng cổ phiếu vượt quá 40% NAV trước khi VN-Index đóng cửa vượt lại SMA50."
        ]
        must_sell_market = [
            "Hạ ngay 50% tỷ trọng các mã đang nắm giữ nếu có RS_Score < 0 hoặc xuất hiện nến Upthrust.",
            "Cắt lỗ kỷ luật 100% ngay khi thủng SL (KHÔNG gồng lỗ chờ hồi trong pha CAUTION)."
        ]
    else:
        tier = "BEAR"
        status_label = "BEAR (VN-Index gãy sâu SMA50 — Khóa giải ngân lô lớn)"
        max_nav = 10.0 if last_cp >= 65.0 else 0.0
        size_mult = 0.25 if last_cp >= 65.0 else 0.0
        allow_breakout = False
        guidance = (
            "CẢNH BÁO ĐỎ (BEAR REGIME — VN-Index gãy sâu SMA50): KHÓA TOÀN BỘ GIẢI NGÂN LÔ LỚN để bảo toàn vốn "
            "(tránh lặp lại đợt quét SL đồng loạt 28/10). Nắm giữ 90-100% tiền mặt; chỉ cho phép tối đa 10% NAV "
            "thăm dò T0 nếu có nến rút chân hoảng loạn kèm siêu cổ phiếu hội tụ đủ WFE Pha C + MCDX + Ngoại gom."
        )
        no_buy_market = [
            "CẤM GIẢI NGÂN LÔ LỚN ở mọi nhóm ngành khi VN-Index chưa lấy lại SMA50 hoặc chưa tạo đáy WFE Pha C.",
            "CẤM bắt dao rơi các mã đang cắm dốc dưới SMA50."
        ]
        must_sell_market = [
            "BẮT BUỘC đưa tỷ trọng tiền mặt lên 90-100% NAV.",
            "Bán dứt khoát mọi vị thế vi phạm SL hoặc gãy nền hỗ trợ 15 phiên."
        ]

    return {
        "tier": tier,
        "status_label": status_label,
        "current_index": cur_idx,
        "sma20": sma20,
        "sma50": sma50,
        "dist_to_sma50_%": dist_sma50_pct,
        "slope_5d_sma50_%": slope_5d,
        "perf_5d_%": perf_5d,
        "perf_20d_%": perf_20d,
        "distribution_days_10d": dist_days,
        "max_portfolio_nav_pct": max_nav,
        "size_multiplier": size_mult,
        "allow_breakout": allow_breakout,
        "regime_guidance": guidance,
        "when_not_to_buy_market": no_buy_market,
        "when_must_sell_market": must_sell_market
    }


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
def get_market_depth_and_foreign_batch(symbols: list) -> dict:
    """
    Batch lấy thông tin giá khớp, sổ lệnh 3 mức (Order Depth) và tổng mua/bán ròng 15 phiên
    của Khối ngoại cho nhiều mã cổ phiếu cùng lúc (chạy đa luồng siêu tốc).
    """
    if isinstance(symbols, str):
        symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        symbols = [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]

    results = {}
    with ThreadPoolExecutor(max_workers=min(10, max(1, len(symbols)))) as executor:
        fut_map = {executor.submit(get_market_depth_and_foreign, sym): sym for sym in symbols}
        for fut in as_completed(fut_map):
            sym = fut_map[fut]
            try:
                results[sym] = fut.result()
            except Exception as e:
                results[sym] = {"symbol": sym, "error": str(e), "foreign_net_total_15d_bil": 0.0}
    return {"count": len(results), "data": results}


@server.tool()
def get_relative_strength_batch(symbols: list, count: int = 60) -> dict:
    """
    Batch tính Sức mạnh giá tương đối (RS 5D, 10D, 20D, 60D và RS_Score) so với VNINDEX
    cho danh sách nhiều mã cổ phiếu trong 1 lần gọi duy nhất.
    """
    if isinstance(symbols, str):
        symbols = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        symbols = [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]

    days = int(max(count, 60) * 1.8)
    d_idx = _fetch_dnse_raw("VNINDEX", "1D", days)
    if not d_idx or not d_idx.get("c"):
        return {"error": "Không đủ dữ liệu VNINDEX"}
    idx_c = d_idx.get("c", [])

    def _perf(arr, d):
        if len(arr) < d or arr[-d] <= 0:
            return 0.0
        return round((arr[-1] - arr[-d]) / arr[-d] * 100.0, 2)

    idx_5 = _perf(idx_c, 5)
    idx_10 = _perf(idx_c, 10)
    idx_20 = _perf(idx_c, 20)
    idx_60 = _perf(idx_c, 60)

    batch_raw = _fetch_batch_candles(symbols, days=days, resolution="1D")
    out = {}
    for sym in symbols:
        d = batch_raw.get(sym)
        if not d or not d.get("c"):
            out[sym] = {"symbol": sym, "error": "No data"}
            continue
        c = d["c"]
        s5, s10, s20, s60 = _perf(c, 5), _perf(c, 10), _perf(c, 20), _perf(c, 60)
        rs5 = round(s5 - idx_5, 2)
        rs10 = round(s10 - idx_10, 2)
        rs20 = round(s20 - idx_20, 2)
        rs60 = round(s60 - idx_60, 2)
        rs_score = round(0.6 * rs20 + 0.4 * rs5, 2)
        out[sym] = {
            "symbol": sym,
            "current_price": c[-1],
            "rs_score": rs_score,
            "excess_rs_5d_%": rs5,
            "excess_rs_10d_%": rs10,
            "excess_rs_20d_%": rs20,
            "excess_rs_60d_%": rs60,
            "rs_evaluation": "OUTPERFORMING" if rs_score > 0 else "UNDERPERFORMING"
        }
    return {
        "benchmark": {"name": "VNINDEX", "current_index": idx_c[-1], "perf_5d_%": idx_5, "perf_20d_%": idx_20},
        "count": len(out),
        "data": out
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
    top_leaders = leaders[:top_n]

    if top_leaders and len(top_leaders) <= 15:
        try:
            f_batch = get_market_depth_and_foreign_batch([item["symbol"] for item in top_leaders]).get("data", {})
            for item in top_leaders:
                f_info = f_batch.get(item["symbol"], {})
                item["foreign_net_15d_bil"] = f_info.get("foreign_net_total_15d_bil", 0.0)
        except Exception:
            pass

    regime = evaluate_vnindex_regime(d_idx)

    return {
        "market_regime": regime,
        "benchmark": {
            "name": "VNINDEX",
            "current_index": idx_c[-1],
            "perf_5d_%": idx_perf_5d,
            "perf_20d_%": idx_perf_20d
        },
        "scanned_count": len(target_universe),
        "qualified_count": len(leaders),
        "universe_type": "Dynamic Market (SSI Live)" if not symbols else "Custom List",
        "top_leaders": top_leaders
    }


def _build_trade_governance_plan(
    sym: str,
    setup_type: str,
    p_cur: float,
    pivot_or_support: float,
    stop_loss: float,
    target_1: float,
    target_2: float,
    atr14: float,
    rsi14: float,
    rvol: float,
    last_cp: float,
    change_1d_pct: float,
    rs_score: float,
    support_tag: str,
    vol_trend_tag: str,
    regime: dict,
    mcdx_red: float = None,
    flow_dist: float = None,
    wfe_size_pct: float = None
) -> dict:
    """
    Computes explicit actionable governance for a candidate:
    1. Entry timing & Optimal Limit Buy Zone (anti-FOMO T+2.5)
    2. Capital Allocation (% NAV + Tranche T1/T2 split + Market Regime cap)
    3. When NOT to Buy (explicit veto & wait rules)
    4. When MUST Sell (explicit stop loss, Spring Guard, 3-stage trailing stop, climax exit, time-stop)
    """
    is_breakout = "VƯỢT ĐỈNH" in setup_type or "BREAKOUT" in setup_type or "PHASE_D" in setup_type
    dist_from_base_atr = round((p_cur - pivot_or_support) / atr14, 2) if atr14 > 0 else 0.0

    if is_breakout:
        buy_low = round(max(stop_loss + 0.5 * atr14, pivot_or_support * 0.995), 2)
        buy_high = round(pivot_or_support + 0.6 * atr14, 2)
    else:
        buy_low = round(pivot_or_support, 2)
        buy_high = round(min(p_cur, pivot_or_support + 0.7 * atr14), 2)
        if buy_high < buy_low:
            buy_high = round(pivot_or_support * 1.02, 2)

    veto_reasons = []
    wait_reasons = []

    if regime.get("tier") == "BEAR":
        veto_reasons.append(
            f"VN-Index đang trong pha BEAR ({regime.get('current_index')} < SMA50 {regime.get('sma50')}): "
            "KHÔNG giải ngân lô lớn (chỉ tối đa 5-10% NAV thăm dò nếu hội tụ đủ tín hiệu)."
        )
    elif regime.get("tier") == "CAUTION" and is_breakout and not regime.get("allow_breakout", False):
        veto_reasons.append(
            "VN-Index dưới SMA50 (pha CAUTION): CẤM MUA BREAKOUT VƯỢT ĐỈNH (Type B) do xác suất Bull-trap T+2.5 rất cao."
        )

    if rsi14 >= 70.0:
        wait_reasons.append(f"RSI14 = {rsi14} >= 70 (Quá mua): CẤM mua đuổi giá xanh, bắt buộc chờ nhịp chỉnh về vùng {buy_low}-{buy_high}.")
    elif rsi14 >= 68.0 and is_breakout:
        wait_reasons.append(f"RSI14 = {rsi14} tiệm cận vùng quá mua (>=68): Không mua đuổi giá cao, chỉ kê mua Limit tại {buy_low}-{buy_high}.")

    if dist_from_base_atr > 1.5:
        wait_reasons.append(
            f"Giá hiện tại ({p_cur}) đã kéo giãn {dist_from_base_atr}x ATR14 khỏi mốc tham chiếu ({pivot_or_support}): "
            f"CẤM đua lệnh T+0, chờ retest vùng {buy_low}-{buy_high}."
        )
    if rvol > 3.0 and change_1d_pct > 4.0:
        wait_reasons.append(
            f"Nến nổ Vol đột biến (RVol={rvol} > 3.0, +{change_1d_pct}%): Rủi ro rũ hàng T+2.5 cao, chờ nến xác nhận/retest 1/2 thân nến."
        )
    if vol_trend_tag == "[HIDDEN_DISTRIBUTION]":
        veto_reasons.append("Cảnh báo [HIDDEN_DISTRIBUTION]: Khối lượng 5 phiên phồng to nhưng đóng nến yếu -> KHÔNG MUA.")
    if flow_dist is not None and flow_dist >= 70.0:
        veto_reasons.append(f"Cảnh báo phân phối MCDX (flow_dist={flow_dist:.1f} >= 70) -> KHÔNG MUA MỚI.")

    if veto_reasons:
        entry_timing = "[DO_NOT_BUY_VETO]"
    elif wait_reasons:
        entry_timing = "[WAIT_PULLBACK_LIMIT]"
    else:
        entry_timing = "[BUY_IN_OPTIMAL_ZONE]"

    base_nav_pct = wfe_size_pct if (wfe_size_pct is not None and wfe_size_pct > 0) else 20.0
    if support_tag == "[WEAK_SUPPORT]":
        base_nav_pct *= 0.75
    if rs_score < 0:
        base_nav_pct *= 0.80
    if mcdx_red is not None and mcdx_red <= 5.0:
        base_nav_pct *= 0.50
    if wait_reasons:
        base_nav_pct *= 0.75

    regime_mult = regime.get("size_multiplier", 1.0)
    rec_nav_pct = round(min(25.0, base_nav_pct * regime_mult), 1)
    if entry_timing == "[DO_NOT_BUY_VETO]":
        rec_nav_pct = 0.0

    t1_alloc_pct = round(rec_nav_pct * 0.5, 1)
    t2_alloc_pct = round(rec_nav_pct - t1_alloc_pct, 1)

    capital_allocation = {
        "recommended_nav_pct": rec_nav_pct,
        "max_single_stock_cap_pct": 25.0,
        "market_regime_portfolio_cap_pct": regime.get("max_portfolio_nav_pct", 100.0),
        "tranche_1_probe_pct": t1_alloc_pct,
        "tranche_1_zone": f"{buy_low} - {buy_high}",
        "tranche_2_add_pct": t2_alloc_pct,
        "tranche_2_trigger": (
            f"Chỉ giải ngân thêm {t2_alloc_pct}% NAV khi hàng T1 đã về tài khoản (T+2.5) VÀ giá đóng cửa > {round(pivot_or_support * 1.015, 2)} kèm RVol >= 1.2"
        ) if rec_nav_pct > 0 else "Không giải ngân (Approved Size = 0% NAV)"
    }

    when_not_to_buy = list(veto_reasons) + list(wait_reasons)
    when_not_to_buy.extend([
        f"KHÔNG MUA nếu giá mở cửa/trong phiên thủng mốc Hỗ trợ/Pivot ({pivot_or_support}) hoặc thủng SL ({stop_loss}) kèm RVol > 1.2.",
        f"KHÔNG MUA ĐUỔI nếu giá vượt quá {round(buy_high * 1.015, 2)} (lệch vùng mua tối ưu làm hỏng tỷ lệ R:R < 1.5).",
        "KHÔNG GIẢI NGÂN LÔ LỚN nếu VN-Index đóng cửa gãy SMA50 kèm khối lượng bán tăng vọt."
    ])

    when_must_sell = [
        f"1. CẮT LỖ KỶ LUẬT 100% (Hard Stop): Bán dứt khoát nếu giá đóng cửa <= {stop_loss} (Rủi ro -{round((p_cur - stop_loss)/p_cur*100, 2)}%). "
        f"Ngoại lệ duy nhất: Kích hoạt [SPRING_TEST] nếu nhúng thủng {stop_loss} trong phiên nhưng rút chân đóng cửa CP >= 70%, RVol >= 1.0 -> quan sát T+1 (nếu T+1 đóng cửa < Low_T thì bán 100% tại Open T+2).",
        f"2. CHỐT LỜI 50% & KHÓA LÃI (Stage 2 Trailing Stop): Khi giá chạm Target 1 ({target_1}) hoặc lãi >= +5%, chốt 50% vị thế và nâng ngay Operative SL lên max(Giá vốn, min(Low 3 phiên gần nhất)).",
        f"3. CHỐT LỜI CHỦ ĐỘNG TRÊN ĐỈNH (Stage 3 / Climax Exit): Bán 100% phần còn lại khi chạm Target 2 ({target_2}) HOẶC xuất hiện nến Upthrust/Buying Climax (RSI14 >= 72, đóng cửa nửa dưới CP <= 40% với RVol >= 1.4).",
        "4. BÁN CƠ CẤU THEO THỜI GIAN (Time-Stop T+8): Nếu sau 8 phiên nắm giữ mà giá vẫn đi ngang trong biên +-1.5% quanh giá mua và dòng tiền suy yếu (RVol < 0.8, RS < 0) -> Chủ động bán thu hồi vốn."
    ]

    return {
        "entry_timing": entry_timing,
        "optimal_buy_zone": [buy_low, buy_high],
        "dist_from_base_atr": dist_from_base_atr,
        "capital_allocation": capital_allocation,
        "when_not_to_buy": when_not_to_buy,
        "when_must_sell": when_must_sell
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
    tuân thủ nghiêm ngặt quản trị rủi ro tuyệt đối (Absolute Return) và thiết kế cho dòng vốn lớn (Institutional Capital).
    """
    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()

    # Tải dữ liệu song song đa luồng cho toàn bộ Universe (120 ngày - margin an toàn dịp lễ Tết - BUG-6)
    stock_data = _fetch_batch_candles(target_universe, days=120, resolution="1D")

    # Lấy dữ liệu VNINDEX để tính RS Score inline & Market Regime Gate
    d_idx = _fetch_dnse_raw("VNINDEX", "1D", 45)
    regime = evaluate_vnindex_regime(d_idx)
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

        # 4. Dynamic Stop Loss bằng ATR_14 & RSI_14 (Wilder Smoothing chuẩn xác - BUG-12):
        atr14 = compute_wilder_atr14(c, h, l)
        rsi14 = compute_wilder_rsi14(c)

        # 5. Nhận diện VPA Đa phiên (Context-Aware VPA - BUG-1, BUG-3, BUG-4) & Volume Trend 5D:
        last_spread = round(h[-1] - l[-1], 2)
        last_cp = round((c[-1] - l[-1]) / last_spread * 100.0, 1) if last_spread > 0 else 50.0
        last_rvol = round(v[-1] / sma20_vol, 2) if sma20_vol > 0 else 1.0
        change_1d_pct = round((c[-1] - c[-2]) / c[-2] * 100.0, 2) if len(c) >= 2 and c[-2] > 0 else 0.0

        vpa_status = classify_vpa(c, o, h, l, v, len(c) - 1, sma20_vol)
        vol_trend_tag, vol_trend_norm = compute_volume_trend_5d(v, c, h, l, sma20_vol)

        # BUG-1: Loại bỏ ngay mã có tín hiệu VPA tiêu cực
        if vpa_status in BEARISH_VPA:
            continue

        prior_40_close_high = max(c[-41:-1])
        prior_40_high = max(h[-41:-1])
        base_low_40 = min(l[-41:-1])  # BUG-2: Loại trừ nến hiện tại để tránh phồng base_depth

        # 6. Phân loại Kịch bản (Archetype Classification):
        base_depth_cand = round(prior_40_close_high - base_low_40, 2)
        if p_cur >= prior_40_close_high * 0.985 and base_depth_cand >= 1.5 * atr14:
            # Kịch bản B: VƯỢT ĐỈNH NỀN GIÁ / VCP PIVOT
            # BUG-3: Kiểm tra Upthrust / False Breakout tại vùng Breakout
            if last_cp <= 30.0 and last_rvol >= 1.2:
                continue

            setup_type = "VƯỢT ĐỈNH (Breakout / VCP)"
            pivot = prior_40_close_high
            base_depth = base_depth_cand

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
        if vpa_status in ["Bùng nổ dòng tiền (SOS tiền lớn vào)", "Bùng nổ rút chân (Bullish Hammer SOS)", "Chớm dừng rơi (Stopping Volume / Hấp thụ)"]:
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
            min(
                1.0,
                0.30 * rr_1_norm
                + 0.25 * vpa_score_norm
                + 0.20 * rs_score_norm
                + 0.10 * support_density_norm
                + 0.10 * vol_trend_norm
                + 0.05 * adtv_norm
                + rs_bonus
            ),
            3
        )

        gov = _build_trade_governance_plan(
            sym=sym,
            setup_type=setup_type,
            p_cur=p_cur,
            pivot_or_support=pivot_or_support,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            atr14=atr14,
            rsi14=rsi14,
            rvol=last_rvol,
            last_cp=last_cp,
            change_1d_pct=change_1d_pct,
            rs_score=rs_score,
            support_tag=support_tag,
            vol_trend_tag=vol_trend_tag,
            regime=regime
        )

        trend_label = "Uptrend (>SMA50)" if p_cur >= sma50 else "Tích lũy sát SMA50"
        setups.append({
            "symbol": sym,
            "sector": get_stock_sector(sym),
            "setup_type": setup_type,
            "current_price": p_cur,
            "rsi_14": rsi14,
            "trend": trend_label,
            "slope_5d_sma50_%": slope_5d,
            "rs_score": rs_score,
            "support_or_pivot": pivot_or_support,
            "support_density": support_density,
            "support_tag": support_tag,
            "volume_trend_5d": vol_trend_tag,
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
            "avg_vol_20d": int(sma20_vol),
            "entry_timing": gov["entry_timing"],
            "optimal_buy_zone": gov["optimal_buy_zone"],
            "capital_allocation": gov["capital_allocation"],
            "when_not_to_buy": gov["when_not_to_buy"],
            "when_must_sell": gov["when_must_sell"]
        })

    # Xếp hạng ưu tiên theo Composite Score, sau đó đến rr_1_conservative
    setups.sort(key=lambda x: (x["composite_score"], x["rr_1_conservative"]), reverse=True)

    return {
        "market_regime": regime,
        "scanned_count": len(target_universe),
        "qualified_count": len(setups),
        "universe_type": "Dynamic Market (SSI Live)" if not symbols else "Custom List",
        "methodology": {
            "market_regime_gate": f"{regime['tier']} (Max Portfolio Budget: {regime['max_portfolio_nav_pct']}% NAV)",
            "liquidity_filter": f"ADTV >= {min_avg_val_bil} tỷ VNĐ/phiên (Chống trượt giá cho vốn lớn)",
            "trend_filter": "Price >= SMA50 * 0.965 & SMA50 Slope 5D >= -1.0%",
            "rs_filter": "RS_Score = 0.6*RS_20D + 0.4*RS_5D >= -5.0% vs VNINDEX",
            "dual_archetypes": "Type A (Range Rebound mua sát hỗ trợ) & Type B (Breakout/VCP theo Measured Move)",
            "support_density": "Mật độ test đáy 40 phiên: Weak Support (<2 touch -> buffer 1.2*ATR14) vs Strong Support (>=3 touch -> buffer 1.0*ATR14)",
            "dynamic_stop_loss": "Support/Pivot - 1.0 * ATR14 (hoặc 1.2 * ATR14 nếu Weak Support)",
            "context_aware_vpa": "Phân tích đa phiên (Grinding No Demand, Upthrust, No Supply, Stopping Vol, SOS) + Volume Trend 5D",
            "composite_ranking": "Composite = 0.30*RR1 + 0.25*VPA + 0.20*RS + 0.10*SupportDensity + 0.10*VolTrend5D + 0.05*ADTV"
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
    regime = evaluate_vnindex_regime()
    return {
        "market_regime": regime,
        "scanned_count": len(target_universe),
        "qualified_count": len(setups),
        "universe_type": "Dynamic Market (SSI Live)" if not symbols else "Custom List",
        "methodology": {
            "market_regime_gate": f"{regime['tier']} (Max Portfolio Budget: {regime['max_portfolio_nav_pct']}% NAV)",
            "trading_range": "Hộp Tích lũy 90 phiên [-90:-20] (TR_Low, TR_Mid, TR_High) kiểm tra Stationarity 3 khung",
            "setup_phase_c": "Test of Spring / Shakeout (Mua đáy test cạn cung, SL dưới Spring)",
            "setup_phase_d": "BU / LPS (Mua pullback cạn cung ở nửa trên TR sau Minor SOS lọc %CP >= 66%)",
            "liquidity_filter": f"ADTV >= {min_avg_val_bil} tỷ VNĐ/phiên",
            "risk_management": "Dynamic ATR14 Stop Loss + Buffer chống whipsaw 0.8*ATR + Tranche Scaling 2 giai đoạn"
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
    Quét cơ hội giải ngân theo Đặc tả kỹ thuật & vận hành WFE V3.5 (Wyckoff x Flow Expectancy System).
    Ba Engine độc lập (Flow, Structure, Volume) hội tụ tại tầng Policy ra quyết định theo Expectancy (EV)
    và xác suất p_success, tích hợp cổng Market Regime VN-Index.
    """
    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()
    stock_data = _fetch_batch_candles(target_universe, days=220, resolution="1D")
    regime = evaluate_vnindex_regime()

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

    res = scanner.scan_universe(
        candles_by_symbol=candles_map,
        top_n=top_n,
        min_p_success=min_p_success,
        min_avg_val_bil=min_avg_val_bil
    )
    res["market_regime"] = regime
    return res


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
    stock_data = _fetch_batch_candles(target_universe, days=220, resolution="1D")

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
    res = out.to_dict()
    res.pop("disclaimer", None)
    return res


@server.tool()
def scan_unified_opportunities(
    preset: str = "all",
    min_rr: float = 1.8,
    max_risk_pct: float = 6.5,
    min_avg_val_bil: float = 15.0,
    top_n: int = 10,
    symbols: list = None,
    include_foreign_flow: bool = True
) -> dict:
    """
    UNIFIED MASTER SCANNER (Gộp 4 bộ lọc vào 1 lần gọi duy nhất, dùng chung cache OHLCV):
    - preset: 'all' (hội tụ đa tín hiệu), 'high_rr', 'wfe', 'leaders', hoặc 'mcdx'
    - Tích hợp 3-Tier Market Regime Gate (VN-Index vs SMA50), Sector Breadth (Top ngành dẫn dắt),
      RS Leader Score, MCDX Banker Flow (BII & Red 0-20), WFE V3.5 (Pha C Spring / Pha D LPS),
      và High R:R V2.2 (Type A Support / Type B Breakout).
    - Chấm điểm Convergence Score (0-100) ưu tiên mã hội tụ >= 2 tín hiệu.
    - Trả về đầy đủ kế hoạch thực thi cho từng mã và toàn danh mục:
      1. Khi nào KHÔNG ĐƯỢC MUA (when_not_to_buy + entry_timing + optimal_buy_zone chống bẫy T+2.5)
      2. Khi nào PHẢI BÁN (when_must_sell: Hard SL, Spring Guard 5 điều kiện, Trailing Stop 3 giai đoạn, Climax Exit, Time-Stop)
      3. Phân bổ vốn bao nhiêu (capital_allocation: % NAV khuyến nghị, chia Tranche T1/T2, trần danh mục theo Market Regime).
    """
    preset_mode = (preset or "all").strip().lower()
    target_universe = [s.upper() for s in symbols] if symbols else get_dynamic_universe()

    # 1. Tải dữ liệu VNINDEX & đánh giá Market Regime Gate (3-Tier)
    d_idx = _fetch_dnse_raw("VNINDEX", "1D", 100)
    regime = evaluate_vnindex_regime(d_idx)
    idx_perf_5d = regime.get("perf_5d_%", 0.0)
    idx_perf_20d = regime.get("perf_20d_%", 0.0)

    # 2. Tải dữ liệu 1 lần duy nhất cho toàn bộ Universe (220 ngày)
    stock_data = _fetch_batch_candles(target_universe, days=220, resolution="1D")

    # Chuẩn bị candles_map cho WFE & MCDX Flow Radar
    candles_map = {}
    rs_by_sym = {}
    sector_stats = {}

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
        if len(c) < 55 or len(v) < 55:
            continue

        sma20_vol = compute_clean_sma20_vol(v, c, o, h, l, len(c) - 1)
        adtv_bil = round(sma20_vol * c[-1] / 1e6, 2)
        if adtv_bil >= min_avg_val_bil:
            p5 = (c[-1] - c[-5]) / c[-5] * 100.0 if c[-5] > 0 else 0.0
            p20 = (c[-1] - c[-20]) / c[-20] * 100.0 if c[-20] > 0 else 0.0
            rs_5d = round(p5 - idx_perf_5d, 2)
            rs_20d = round(p20 - idx_perf_20d, 2)
            rs_sc = round(0.6 * rs_20d + 0.4 * rs_5d, 2)
            sec = get_stock_sector(sym)
            rs_by_sym[sym] = {
                "rs_score": rs_sc,
                "rs_5d_%": rs_5d,
                "rs_20d_%": rs_20d,
                "adtv_bil": adtv_bil,
                "sector": sec
            }
            st = sector_stats.setdefault(sec, {"total": 0, "outperforming": 0, "rs_sum": 0.0, "leaders": []})
            st["total"] += 1
            st["rs_sum"] += rs_sc
            if rs_sc > 0:
                st["outperforming"] += 1
                st["leaders"].append((rs_sc, sym))

        if len(c) >= 70:
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

    # 3. Tính Sector Breadth (Top ngành dẫn dắt)
    sector_leaderboard = []
    leading_sectors = set()
    for sec, st in sector_stats.items():
        if st["total"] == 0:
            continue
        breadth_pct = round(st["outperforming"] / st["total"] * 100.0, 1)
        avg_rs = round(st["rs_sum"] / st["total"], 2)
        st["leaders"].sort(reverse=True)
        sector_leaderboard.append({
            "sector": sec,
            "stock_count": st["total"],
            "outperforming_pct": breadth_pct,
            "avg_rs_score": avg_rs,
            "top_symbols": [sym for _, sym in st["leaders"][:3]]
        })
    sector_leaderboard.sort(key=lambda x: (x["outperforming_pct"], x["avg_rs_score"]), reverse=True)
    for item in sector_leaderboard[:3]:
        if item["avg_rs_score"] > -1.0:
            leading_sectors.add(item["sector"])

    # 4. Chạy MCDX Flow Radar in-memory (dùng tier='control' để lấy đủ cả Established & Emerging)
    mcdx_by_sym = {}
    if candles_map:
        radar = MCDXFlowRadar()
        mcdx_out = radar.scan_radar(
            candles_by_symbol=candles_map,
            mode="both",
            strength_tier="control",
            min_adtv_billion=min_avg_val_bil,
            top_n=len(candles_map)
        )
        for cand in mcdx_out.candidates:
            mcdx_by_sym[cand.symbol] = cand
        # Ngoài ra tính nhanh flow_trend / flow_accum / flow_dist cho các mã không lọt radar
        flow_eng = radar.flow_engine
    else:
        from wfe.engines.flow_engine import FlowEngine
        flow_eng = FlowEngine()

    # 5. Chạy WFE V3.5 Scanner in-memory (nếu preset là 'all' hoặc 'wfe')
    wfe_by_sym = {}
    wfe_dropouts = []
    if preset_mode in ("all", "wfe") and candles_map:
        wfe_scanner = WFEScanner()
        wfe_res = wfe_scanner.scan_universe(
            candles_by_symbol=candles_map,
            top_n=max(top_n * 2, 25),
            min_p_success=0.42,
            min_avg_val_bil=min_avg_val_bil
        )
        wfe_dropouts = wfe_res.get("drop_out_manifest", [])
        for wc in wfe_res.get("top_candidates", []):
            wfe_by_sym[wc["symbol"]] = wc

    # 6. Chấm điểm từng cổ phiếu trong Universe & hợp nhất tín hiệu
    BEARISH_VPA = {
        "Cảnh báo: Thiếu cầu trên đà rơi (No Demand)",
        "Cảnh báo: Chuỗi giảm cạn vol 3 phiên (Grinding No Demand)",
        "Chịu áp lực bán ngắn hạn",
        "Trôi cạn vol (Thiếu cầu ngắn hạn)",
        "Upthrust / Selling Climax"
    }

    unified_candidates = []
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
        sma20_vol = compute_clean_sma20_vol(v, c, o, h, l, len(c) - 1)
        avg_val_20d_bil = round(sma20_vol * p_cur / 1e6, 2)
        if avg_val_20d_bil < min_avg_val_bil or sma20_vol < 180000:
            continue

        sma50 = sum(c[-50:]) / 50.0
        sma50_prev5 = sum(c[-55:-5]) / 50.0
        slope_5d = round((sma50 - sma50_prev5) / sma50_prev5 * 100.0, 2)

        perf_5d = round((c[-1] - c[-5]) / c[-5] * 100.0, 2) if c[-5] > 0 else 0.0
        perf_20d = round((c[-1] - c[-20]) / c[-20] * 100.0, 2) if c[-20] > 0 else 0.0
        rs_5d = round(perf_5d - idx_perf_5d, 2)
        rs_20d = round(perf_20d - idx_perf_20d, 2)
        rs_score = round(rs_20d * 0.6 + rs_5d * 0.4, 2)
        change_1d = round((c[-1] - c[-2]) / c[-2] * 100.0, 2) if len(c) >= 2 and c[-2] > 0 else 0.0

        atr14 = compute_wilder_atr14(c, h, l)
        rsi14 = compute_wilder_rsi14(c)
        last_spread = round(h[-1] - l[-1], 2)
        last_cp = round((c[-1] - l[-1]) / last_spread * 100.0, 1) if last_spread > 0 else 50.0
        last_rvol = round(v[-1] / sma20_vol, 2) if sma20_vol > 0 else 1.0
        vpa_status = classify_vpa(c, o, h, l, v, len(c) - 1, sma20_vol)
        vol_trend_tag, vol_trend_norm = compute_volume_trend_5d(v, c, h, l, sma20_vol)
        sector = get_stock_sector(sym)

        # Lấy thông tin MCDX Flow
        mcdx_cand = mcdx_by_sym.get(sym)
        if mcdx_cand:
            flow_trend = round(mcdx_cand.flow_trend, 1)
            flow_accum = round(mcdx_cand.flow_accum, 1)
            flow_dist = round(mcdx_cand.flow_dist, 1)
            bii = round(mcdx_cand.bii, 1)
            mcdx_cat = mcdx_cand.category
        elif sym in candles_map and sym in wfe_by_sym:
            fb = wfe_by_sym[sym].get("flow") or {}
            flow_trend = round((fb.get("trend") or {}).get("value") or 0.0, 1)
            flow_accum = round((fb.get("accum") or {}).get("value") or 0.0, 1)
            flow_dist = round((fb.get("dist") or {}).get("value") or 0.0, 1)
            bii = round(0.5 * flow_trend + 0.3 * flow_accum - 0.2 * flow_dist, 1)
            mcdx_cat = "ESTABLISHED" if flow_trend >= 50 else ("EMERGING" if flow_trend >= 25 or flow_accum >= 45 else "NO_FLOW")
        else:
            flow_trend = 0.0
            flow_accum = 0.0
            flow_dist = 0.0
            bii = 0.0
            mcdx_cat = "NO_FLOW"

        # Quy đổi thang đo MCDX 24HMoney (0-20) = flow_trend / 5.0
        mcdx_red_20 = round(flow_trend / 5.0, 2)
        if flow_dist >= 70.0:
            flow_tag = "[CẢNH BÁO PHÂN PHỐI]"
        elif mcdx_red_20 > 5.0 or mcdx_cat in ("ESTABLISHED", "EMERGING_G1", "EMERGING_G2", "EMERGING"):
            flow_tag = "[FLOW_CONFIRMED]"
        else:
            flow_tag = "[NO_FLOW]"

        # Kiểm tra High R:R Setup (Type A / Type B)
        prior_40_close_high = max(c[-41:-1])
        prior_40_high = max(h[-41:-1])
        base_low_40 = min(l[-41:-1])
        prior_support_15d = min(l[-16:-1])

        high_rr_valid = False
        setup_type = None
        stop_loss = None
        target_1 = None
        target_2 = None
        pivot_or_support = prior_support_15d
        support_density = sum(1 for low_val in l[-41:-1] if abs(low_val - prior_support_15d) / prior_support_15d <= 0.015)
        support_tag = "[STRONG_SUPPORT]" if support_density >= 2 else "[WEAK_SUPPORT]"
        rr_1 = 0.0
        rr_2 = 0.0
        risk_pct = 0.0

        if slope_5d >= -1.0 and p_cur >= sma50 * 0.965 and rs_score >= -5.0 and vpa_status not in BEARISH_VPA:
            base_depth = round(prior_40_close_high - base_low_40, 2)
            if p_cur >= prior_40_close_high * 0.985 and base_depth >= 1.5 * atr14:
                if not (last_cp <= 30.0 and last_rvol >= 1.2):
                    setup_type = "VƯỢT ĐỈNH (Breakout / VCP)"
                    pivot_or_support = prior_40_close_high
                    support_tag = "[BREAKOUT_PIVOT]"
                    sl = round(prior_40_close_high - 1.0 * atr14, 2)
                    if p_cur - sl < 0.8 * atr14:
                        sl = round(p_cur - 1.0 * atr14, 2)
                    t1 = round(p_cur + base_depth * 0.8, 2)
                    t2 = round(p_cur + base_depth * 1.3, 2)
                    rk = round((p_cur - sl) / p_cur * 100.0, 2)
                    rw1 = round((t1 - p_cur) / p_cur * 100.0, 2)
                    if 0 < rk <= max_risk_pct and rw1 >= 3.5:
                        r1 = round((t1 - p_cur) / (p_cur - sl), 2)
                        r2 = round((t2 - p_cur) / (p_cur - sl), 2)
                        if r1 >= min_rr:
                            high_rr_valid = True
                            stop_loss, target_1, target_2, rr_1, rr_2, risk_pct = sl, t1, t2, r1, r2, rk
            if not high_rr_valid:
                dist_to_sup = round((p_cur - prior_support_15d) / prior_support_15d * 100.0, 2)
                if p_cur >= prior_support_15d and dist_to_sup <= 5.0:
                    setup_type = "NỀN HỖ TRỢ (Range Rebound / LPS)"
                    buf = 1.2 * atr14 if support_density < 2 else 1.0 * atr14
                    sl = round(prior_support_15d - buf, 2)
                    t1 = prior_40_close_high
                    t2 = prior_40_high
                    rk = round((p_cur - sl) / p_cur * 100.0, 2)
                    rw1 = round((t1 - p_cur) / p_cur * 100.0, 2)
                    if 0 < rk <= max_risk_pct and rw1 >= 3.5:
                        r1 = round((t1 - p_cur) / (p_cur - sl), 2)
                        r2 = round((t2 - p_cur) / (p_cur - sl), 2)
                        if r1 >= min_rr:
                            high_rr_valid = True
                            stop_loss, target_1, target_2, rr_1, rr_2, risk_pct = sl, t1, t2, r1, r2, rk

        # Kiểm tra WFE V3.5 Setup
        wfe_cand = wfe_by_sym.get(sym)
        wfe_actionable = bool(wfe_cand and wfe_cand.get("classification") == "ACTIONABLE")
        wfe_setup_name = wfe_cand.get("setup_type") if wfe_cand else None
        wfe_p_success = wfe_cand.get("p_success") if wfe_cand else None
        wfe_ev = wfe_cand.get("ev") if wfe_cand else None
        wfe_size = wfe_cand.get("approved_size_pct", 0.0) if wfe_cand else 0.0

        # Nếu chưa có setup High R:R nhưng có WFE Setup hoặc người dùng quét 'leaders' / 'mcdx', vẫn tính SL/Target chuẩn
        if not high_rr_valid:
            if wfe_cand and wfe_cand.get("operative_sl") and wfe_cand.get("target_1"):
                setup_type = f"WFE {wfe_setup_name or 'Phase C/D'}"
                stop_loss = round(wfe_cand["operative_sl"], 2)
                target_1 = round(wfe_cand["target_1"], 2)
                target_2 = round(wfe_cand["target_2"], 2) if wfe_cand.get("target_2") else round(target_1 * 1.06, 2)
                risk_pct = round((p_cur - stop_loss) / p_cur * 100.0, 2) if p_cur > stop_loss else 4.0
                rr_1 = round((target_1 - p_cur) / (p_cur - stop_loss), 2) if p_cur > stop_loss else 0.0
                rr_2 = round((target_2 - p_cur) / (p_cur - stop_loss), 2) if (p_cur > stop_loss and target_2) else 0.0
            else:
                # Fallback SL/Target cho Leaders / MCDX candidates
                setup_type = "MOMENTUM LEADER" if p_cur >= prior_40_close_high * 0.97 else "PULLBACK / ACCUMULATION"
                stop_loss = round(max(prior_support_15d - 1.0 * atr14, p_cur - 1.8 * atr14), 2)
                target_1 = round(max(prior_40_close_high, p_cur + 2.0 * atr14), 2)
                target_2 = round(max(prior_40_high, p_cur + 3.2 * atr14), 2)
                risk_pct = round((p_cur - stop_loss) / p_cur * 100.0, 2) if p_cur > stop_loss else 4.5
                rr_1 = round((target_1 - p_cur) / max(0.01, p_cur - stop_loss), 2)
                rr_2 = round((target_2 - p_cur) / max(0.01, p_cur - stop_loss), 2)

        # Xác định các tín hiệu hội tụ (Converged Signals)
        signals = []
        if high_rr_valid:
            signals.append("HIGH_RR_SETUP")
        if wfe_actionable:
            signals.append(f"WFE_{wfe_setup_name}")
        elif wfe_cand and (wfe_p_success or 0) >= 0.48:
            signals.append("WFE_WATCHLIST")
        if mcdx_cat != "NO_FLOW" or mcdx_red_20 > 5.0:
            signals.append(f"MCDX_{mcdx_cat}")
        if rs_score >= 3.0 and last_rvol >= 1.0:
            signals.append("RS_MARKET_LEADER")
        if sector in leading_sectors:
            signals.append("TOP_SECTOR")
        if vol_trend_tag in ("[DRY_UP_ACCUMULATION]", "[BULLISH_VOL_EXPANSION]"):
            signals.append(vol_trend_tag.strip("[]"))

        # Lọc theo preset_mode
        if preset_mode == "high_rr" and not high_rr_valid:
            continue
        elif preset_mode == "wfe" and not wfe_cand:
            continue
        elif preset_mode == "leaders" and rs_score <= 0:
            continue
        elif preset_mode == "mcdx" and mcdx_cat == "NO_FLOW" and mcdx_red_20 <= 5.0:
            continue
        elif preset_mode == "all":
            # Trong chế độ 'all', yêu cầu ít nhất có High R:R, hoặc WFE, hoặc hội tụ RS Leader + MCDX Flow (trừ khi user truyền danh sách symbols cụ thể)
            if not symbols and not (high_rr_valid or wfe_actionable or (rs_score >= 3.0 and mcdx_red_20 > 5.0)):
                continue

        # Chấm điểm Convergence Score (thang 0-100)
        rr_pts = min(30.0, max(0.0, (rr_1 - 1.2) / 2.8 * 30.0)) if high_rr_valid else min(15.0, max(0.0, (rr_1 - 1.0) * 6.0))
        wfe_pts = min(25.0, (wfe_p_success or 0.40) * 35.0) if wfe_actionable else (10.0 if wfe_cand else 0.0)
        flow_pts = min(20.0, max(0.0, bii * 0.22)) if flow_tag == "[FLOW_CONFIRMED]" else 0.0
        if flow_dist >= 65.0:
            flow_pts -= 12.0
        rs_pts = min(15.0, max(0.0, (rs_score + 5.0) / 20.0 * 15.0))
        if sector in leading_sectors:
            rs_pts += 4.0
        vpa_pts = 10.0 * vol_trend_norm
        if vpa_status in BEARISH_VPA:
            vpa_pts -= 15.0

        convergence_score = round(min(100.0, max(0.0, rr_pts + wfe_pts + flow_pts + rs_pts + vpa_pts)), 1)

        gov = _build_trade_governance_plan(
            sym=sym,
            setup_type=f"{setup_type} ({wfe_setup_name})" if wfe_setup_name else setup_type,
            p_cur=p_cur,
            pivot_or_support=pivot_or_support,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            atr14=atr14,
            rsi14=rsi14,
            rvol=last_rvol,
            last_cp=last_cp,
            change_1d_pct=change_1d,
            rs_score=rs_score,
            support_tag=support_tag,
            vol_trend_tag=vol_trend_tag,
            regime=regime,
            mcdx_red=mcdx_red_20,
            flow_dist=flow_dist,
            wfe_size_pct=wfe_size if wfe_actionable else None
        )

        unified_candidates.append({
            "symbol": sym,
            "sector": sector,
            "is_leading_sector": sector in leading_sectors,
            "convergence_score": convergence_score,
            "convergence_count": len(signals),
            "converged_signals": signals,
            "setup_type": setup_type,
            "wfe_setup": wfe_setup_name,
            "wfe_classification": wfe_cand.get("classification") if wfe_cand else None,
            "wfe_p_success": wfe_p_success,
            "wfe_ev_r": wfe_ev,
            "current_price": p_cur,
            "change_1d_%": change_1d,
            "rsi_14": rsi14,
            "rs_score": rs_score,
            "rvol": last_rvol,
            "close_pos_%": last_cp,
            "vpa_status": vpa_status,
            "volume_trend_5d": vol_trend_tag,
            "mcdx_category": mcdx_cat,
            "mcdx_bii": bii,
            "mcdx_red_20": mcdx_red_20,
            "flow_trend_100": flow_trend,
            "flow_accum_100": flow_accum,
            "flow_dist_100": flow_dist,
            "flow_tag": flow_tag,
            "support_or_pivot": pivot_or_support,
            "support_density": support_density,
            "support_tag": support_tag,
            "atr_14": round(atr14, 2),
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "risk_pct": risk_pct,
            "rr_1": rr_1,
            "rr_2": rr_2,
            "adtv_20d_bil": avg_val_20d_bil,
            "entry_timing": gov["entry_timing"],
            "optimal_buy_zone": gov["optimal_buy_zone"],
            "capital_allocation": gov["capital_allocation"],
            "when_not_to_buy": gov["when_not_to_buy"],
            "when_must_sell": gov["when_must_sell"]
        })

    # Sắp xếp ưu tiên các mã không bị VETO, điểm Convergence cao và R:R tốt
    unified_candidates.sort(
        key=lambda x: (
            0 if x["entry_timing"] == "[DO_NOT_BUY_VETO]" else 1,
            x["convergence_score"],
            x["rr_1"]
        ),
        reverse=True
    )

    top_results = unified_candidates[:top_n]

    # 7. Nhúng dữ liệu Khối ngoại 15 phiên (Batch) cho Top Candidates và cộng điểm thưởng nếu ngoại gom ròng
    if include_foreign_flow and top_results and len(top_results) <= 15:
        try:
            f_map = get_market_depth_and_foreign_batch([item["symbol"] for item in top_results]).get("data", {})
            for item in top_results:
                f_info = f_map.get(item["symbol"], {})
                net_15d = f_info.get("foreign_net_total_15d_bil", 0.0)
                item["foreign_net_15d_bil"] = net_15d
                if net_15d >= 15.0:
                    item["converged_signals"].append("FOREIGN_NET_BUY")
                    item["convergence_count"] = len(item["converged_signals"])
                    item["convergence_score"] = round(min(100.0, item["convergence_score"] + 4.0), 1)
                elif net_15d <= -30.0:
                    item["when_not_to_buy"].insert(
                        0,
                        f"Khối ngoại đang xả ròng mạnh ({net_15d} tỷ/15 phiên): Thận trọng không mua đuổi giá cao."
                    )
        except Exception:
            pass

    # 8. Áp trần tổng ngân sách danh mục (Portfolio Budget Cap) theo Market Regime
    max_port_budget = regime.get("max_portfolio_nav_pct", 100.0)
    running_alloc = 0.0
    for item in top_results:
        alloc = item["capital_allocation"]["recommended_nav_pct"]
        if alloc <= 0:
            continue
        if running_alloc + alloc > max_port_budget:
            allowed = max(0.0, round(max_port_budget - running_alloc, 1))
            item["capital_allocation"]["recommended_nav_pct"] = allowed
            item["capital_allocation"]["tranche_1_probe_pct"] = round(allowed * 0.5, 1)
            item["capital_allocation"]["tranche_2_add_pct"] = round(allowed - round(allowed * 0.5, 1), 1)
            if allowed == 0.0:
                item["entry_timing"] = "[RESERVE_PORTFOLIO_CAP_FULL]"
        running_alloc = round(running_alloc + item["capital_allocation"]["recommended_nav_pct"], 1)

    return {
        "preset": preset_mode,
        "market_regime": regime,
        "sector_breadth_top5": sector_leaderboard[:5],
        "portfolio_allocation_summary": {
            "regime_tier": regime["tier"],
            "max_portfolio_equity_nav_pct": max_port_budget,
            "recommended_deployed_equity_nav_pct": running_alloc,
            "recommended_cash_reserve_nav_pct": round(max(0.0, 100.0 - running_alloc), 1),
            "when_not_to_buy_global": regime["when_not_to_buy_market"],
            "when_must_sell_global": regime["when_must_sell_market"]
        },
        "scanned_count": len(target_universe),
        "qualified_count": len(unified_candidates),
        "top_opportunities": top_results,
        "wfe_drop_out_manifest": wfe_dropouts
    }


@server.tool()
def evaluate_positions_and_exits(
    action: str = "evaluate",
    positions: list = None
) -> dict:
    """
    QUẢN TRỊ ĐIỂM BÁN TỐI ƯU & THEO DÕI DANH MỤC ĐA PHIÊN (`portfolio_tracker.json`):
    - action:
      + 'evaluate': Chấm điểm trạng thái, tính Operative Trailing Stop, kiểm tra 4 quy tắc PHẢI BÁN / GIỮ cho danh mục đang mở.
      + 'upsert': Lưu hoặc cập nhật danh sách vị thế vào `wfe/ops/portfolio_tracker.json`, sau đó đánh giá ngay.
      + 'remove': Xóa các mã trong `positions` (truyền list các dict `{"symbol": "CTG"}` hoặc list mã) khỏi tracker.
      + 'clear': Xóa toàn bộ danh mục theo dõi.
    - Mỗi vị thế trong `positions` có dạng:
      `{"symbol": "CTG", "entry_price": 35.2, "stop_loss": 33.8, "target_1": 38.0, "target_2": 40.5, "size_nav_pct": 15.0, "entry_date": "2026-11-09"}`
    """
    import json as _json

    tracker_path = os.path.join(PROJECT_ROOT, "wfe", "ops", "portfolio_tracker.json")
    os.makedirs(os.path.dirname(tracker_path), exist_ok=True)

    saved_positions = {}
    if os.path.exists(tracker_path):
        try:
            with open(tracker_path, "r", encoding="utf-8") as f:
                raw_saved = _json.load(f)
                if isinstance(raw_saved, dict) and "positions" in raw_saved:
                    for p in raw_saved["positions"]:
                        if p.get("symbol"):
                            saved_positions[p["symbol"].upper()] = p
        except Exception:
            saved_positions = {}

    act = (action or "evaluate").strip().lower()
    if act == "clear":
        saved_positions = {}
        with open(tracker_path, "w", encoding="utf-8") as f:
            _json.dump({"positions": []}, f, indent=2, ensure_ascii=False)
        return {"status": "CLEARED", "positions_evaluated": []}

    if act == "remove" and positions:
        for item in positions:
            sym = (item.get("symbol") if isinstance(item, dict) else str(item)).strip().upper()
            saved_positions.pop(sym, None)
        with open(tracker_path, "w", encoding="utf-8") as f:
            _json.dump({"positions": list(saved_positions.values())}, f, indent=2, ensure_ascii=False)

    if positions and act in ("upsert", "evaluate"):
        for item in positions:
            if isinstance(item, dict) and item.get("symbol"):
                sym = item["symbol"].strip().upper()
                merged = dict(saved_positions.get(sym, {}))
                merged.update(item)
                merged["symbol"] = sym
                saved_positions[sym] = merged
        if act == "upsert":
            with open(tracker_path, "w", encoding="utf-8") as f:
                _json.dump({"positions": list(saved_positions.values())}, f, indent=2, ensure_ascii=False)

    active_list = list(saved_positions.values())
    if not active_list:
        return {
            "status": "EMPTY",
            "message": "Chưa có vị thế nào trong portfolio_tracker.json. Truyền tham số `positions=[...]` với `action='upsert'` để lưu và theo dõi.",
            "positions_evaluated": []
        }

    syms = [p["symbol"] for p in active_list]
    stock_data = _fetch_batch_candles(syms, days=90, resolution="1D")
    regime = evaluate_vnindex_regime()
    idx_perf_5d = regime.get("perf_5d_%", 0.0)
    idx_perf_20d = regime.get("perf_20d_%", 0.0)

    evaluated = []
    wins = 0
    closed_or_triggered = 0
    spring_saves = 0
    r_multiples = []

    for pos in active_list:
        sym = pos["symbol"]
        d = stock_data.get(sym)
        if not d or not d.get("c") or len(d["c"]) < 20:
            evaluated.append({"symbol": sym, "error": "Không đủ dữ liệu OHLCV"})
            continue

        c = d["c"]
        o = d.get("o", c)
        h = d.get("h", c)
        l = d.get("l", c)
        v = d.get("v", [1.0] * len(c))
        t = d.get("t", [])

        p_cur = c[-1]
        sma20_vol = compute_clean_sma20_vol(v, c, o, h, l, len(c) - 1)
        atr14 = compute_wilder_atr14(c, h, l)
        rsi14 = compute_wilder_rsi14(c)
        last_spread = round(h[-1] - l[-1], 2)
        last_cp = round((c[-1] - l[-1]) / last_spread * 100.0, 1) if last_spread > 0 else 50.0
        last_rvol = round(v[-1] / sma20_vol, 2) if sma20_vol > 0 else 1.0
        vpa_tag = classify_vpa(c, o, h, l, v, len(c) - 1, sma20_vol)

        perf_5d = (c[-1] - c[-5]) / c[-5] * 100.0 if c[-5] > 0 else 0.0
        perf_20d = (c[-1] - c[-20]) / c[-20] * 100.0 if c[-20] > 0 else 0.0
        rs_score = round(0.6 * (perf_20d - idx_perf_20d) + 0.4 * (perf_5d - idx_perf_5d), 2)

        entry_price = float(pos.get("entry_price") or p_cur)
        initial_sl = float(pos.get("stop_loss") or round(entry_price - 1.2 * atr14, 2))
        t1 = float(pos.get("target_1") or round(entry_price + 2.0 * (entry_price - initial_sl), 2))
        t2 = float(pos.get("target_2") or round(entry_price + 3.2 * (entry_price - initial_sl), 2))
        size_nav_pct = float(pos.get("size_nav_pct") or 15.0)
        entry_date = pos.get("entry_date")

        # Xác định số phiên nắm giữ kể từ entry_date (mặc định 5 phiên gần nhất nếu không ghi entry_date)
        bars_held = 5
        if entry_date and t:
            date_strs = [datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts in t]
            for idx_dt, dt_s in enumerate(date_strs):
                if dt_s >= entry_date:
                    bars_held = max(1, len(c) - 1 - idx_dt)
                    break

        lookback = min(max(1, bars_held), len(c) - 1)
        high_since_entry = max(h[-lookback:])
        low_since_entry = min(l[-lookback:])

        init_risk = max(0.01, entry_price - initial_sl)
        pnl_pct = round((p_cur - entry_price) / entry_price * 100.0, 2)
        realized_r = round((p_cur - entry_price) / init_risk, 2)

        # Kiểm tra 5 điều kiện Spring Wash-out Guard
        spreads_20 = sorted([ (h[j] - l[j]) / c[j] * 100.0 for j in range(max(0, len(c)-20), len(c)) if c[j] > 0 ])
        median_sp_20 = spreads_20[len(spreads_20)//2] if spreads_20 else 1.5
        cur_sp_pct = (last_spread / p_cur * 100.0) if p_cur > 0 else 0.0
        not_3d_drop = not (len(c) >= 4 and c[-1] < c[-2] < c[-3] < c[-4])

        is_spring_test = (
            l[-1] < initial_sl
            and p_cur > initial_sl
            and last_cp >= 70.0
            and cur_sp_pct >= median_sp_20
            and last_rvol >= 1.0
            and not_3d_drop
        )

        # Tính Operative Trailing Stop (3 giai đoạn)
        min_low_3d = round(min(l[-4:-1]) if len(l) >= 4 else l[-1], 2)
        if high_since_entry >= t1 or pnl_pct >= 5.0:
            operative_sl = round(max(entry_price, min_low_3d, initial_sl), 2)
            trailing_stage = "STAGE_2_LOCK_PROFIT (Operative SL = max(Entry, min(Low_3D)))"
        else:
            operative_sl = initial_sl
            trailing_stage = "STAGE_1_INITIAL_ATR_SL"

        # Phân loại trạng thái & Khuyến nghị hành động BÁN / GIỮ
        is_climax_or_upthrust = (
            (rsi14 >= 72.0 and last_cp <= 40.0 and last_rvol >= 1.3)
            or vpa_tag == "Upthrust / Selling Climax"
        )

        if p_cur <= operative_sl:
            status_tag = "[VI PHẠM SL — BẮT BUỘC BÁN 100%]"
            sell_action = f"BÁN CẮT LỖ/CHẶN LÃI 100% NGAY LẬP TỨC do giá đóng cửa ({p_cur}) <= Operative SL ({operative_sl})."
            recommended_remaining_nav_pct = 0.0
            closed_or_triggered += 1
            if realized_r > 0:
                wins += 1
            r_multiples.append(realized_r if operative_sl > initial_sl else -1.0)
        elif is_spring_test:
            status_tag = "[RÚT CHÂN SPRING — GIỮ QUAN SÁT T+1]"
            sell_action = (
                f"Kích hoạt Spring Wash-out Guard (đủ 5 điều kiện): KHÔNG bán hoảng loạn. "
                f"Nếu phiên T+1 đóng cửa > {p_cur} -> giữ tiếp; nếu T+1 thủng đáy Spring ({l[-1]}) -> BÁN 100% tại Open T+2."
            )
            recommended_remaining_nav_pct = size_nav_pct
            spring_saves += 1
            r_multiples.append(realized_r)
        elif high_since_entry >= t2:
            status_tag = "[ĐẠT TARGET 2 — CHỐT LỜI 100%]"
            sell_action = f"ĐÃ CHẠM TARGET 2 ({t2}): BÁN CHỐT LỜI 100% vị thế để hiện thực hóa toàn bộ lợi nhuận."
            recommended_remaining_nav_pct = 0.0
            closed_or_triggered += 1
            wins += 1
            r_multiples.append(round((t2 - entry_price) / init_risk, 2))
        elif is_climax_or_upthrust and pnl_pct > 2.0:
            status_tag = "[CẢNH BÁO ĐỈNH CLIMAX/UPTHRUST — CHỐT LỜI CHỦ ĐỘNG]"
            sell_action = (
                f"Xuất hiện tín hiệu xả/kiệt sức vùng cao ({vpa_tag}, RSI={rsi14}, CP={last_cp}%, RVol={last_rvol}): "
                f"BÁN CHỐT LỜI CHỦ ĐỘNG 50-100% ngay trên đỉnh, nâng cứng SL phần còn lại lên {min_low_3d}."
            )
            recommended_remaining_nav_pct = round(size_nav_pct * 0.3, 1)
            wins += 1
            closed_or_triggered += 1
            r_multiples.append(realized_r)
        elif high_since_entry >= t1:
            status_tag = "[ĐẠT TARGET 1 — CHỐT 50% & NÂNG TRAILING SL]"
            sell_action = (
                f"Đã đạt Target 1 ({t1}): CHỐT LỜI 50% vị thế (giữ {round(size_nav_pct*0.5, 1)}% NAV), "
                f"nâng Operative SL lên {operative_sl} (không bao giờ để lệnh thắng thành lỗ)."
            )
            recommended_remaining_nav_pct = round(size_nav_pct * 0.5, 1)
            wins += 1
            closed_or_triggered += 1
            r_multiples.append(realized_r)
        elif bars_held >= 8 and abs(pnl_pct) <= 1.5 and (rs_score < 0 or last_rvol < 0.8):
            status_tag = "[TIME-STOP T+8 — BÁN CƠ CẤU VỐN]"
            sell_action = (
                f"Đã nắm giữ {bars_held} phiên nhưng giá đi ngang ({pnl_pct}%) và sức mạnh giá yếu (RS={rs_score}%): "
                f"BÁN 100% theo quy tắc Time-Stop để giải phóng {size_nav_pct}% NAV sang cổ phiếu dẫn dắt."
            )
            recommended_remaining_nav_pct = 0.0
            r_multiples.append(realized_r)
        else:
            status_tag = "[ĐANG GIỮ — AN TOÀN]"
            sell_action = (
                f"Tiếp tục nắm giữ ({size_nav_pct}% NAV). Đặt lệnh Stop Loss tự động tại {operative_sl}, "
                f"kê bán chốt lời 50% tại Target 1 ({t1})."
            )
            recommended_remaining_nav_pct = size_nav_pct
            r_multiples.append(realized_r)

        evaluated.append({
            "symbol": sym,
            "entry_date": entry_date or f"T-{bars_held}",
            "bars_held": bars_held,
            "entry_price": entry_price,
            "current_price": p_cur,
            "initial_sl": initial_sl,
            "operative_sl": operative_sl,
            "trailing_stage": trailing_stage,
            "target_1": t1,
            "target_2": t2,
            "pnl_pct": pnl_pct,
            "realized_r": realized_r,
            "rsi_14": rsi14,
            "rs_score": rs_score,
            "rvol": last_rvol,
            "close_pos_%": last_cp,
            "vpa_tag": vpa_tag,
            "status_tag": status_tag,
            "must_sell_or_hold_action": sell_action,
            "current_size_nav_pct": size_nav_pct,
            "recommended_remaining_nav_pct": recommended_remaining_nav_pct
        })

    win_rate = round(wins / max(1, closed_or_triggered) * 100.0, 1) if closed_or_triggered > 0 else 0.0
    avg_r = round(sum(r_multiples) / max(1, len(r_multiples)), 2)

    return {
        "market_regime": regime,
        "portfolio_metrics": {
            "total_positions": len(evaluated),
            "win_rate_%": win_rate,
            "avg_r_multiple": avg_r,
            "spring_saves_count": spring_saves
        },
        "positions_evaluated": evaluated
    }


if __name__ == "__main__":
    server.run(transport="stdio")

