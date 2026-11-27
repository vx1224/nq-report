"""data/symbols/*_full_tickers.json -> data/universe.json

미국 3개 거래소 종목 중 시가총액 상위 보통주만 추려 사이트 테마(11개)로 분류한다.
사이트(index.html)는 이 파일의 메타데이터와 market_data.json 의 `universe` 시세를 합쳐 쓴다.

    python scripts/build_universe.py [시총 하한(USD), 기본 5e10]
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYMBOL_DIR = ROOT / "data" / "symbols"
OUT_PATH = ROOT / "data" / "universe.json"
MIN_MARKET_CAP = float(sys.argv[1]) if len(sys.argv) > 1 else 5e10

# index.html 의 themeCatalog 키와 같아야 한다.
AI_SEMI = "AI 반도체"
BIGTECH = "빅테크 클라우드"
DEVICE = "온디바이스"
POWER = "전력·인프라"
SW = "자율주행·SW"
FIN = "금융·핀테크"
HEALTH = "헬스케어·바이오"
CONSUMER = "소비·유통·미디어"
ENERGY = "에너지·소재"
INDUSTRIAL = "산업재·방산·운송"
REIT_UTIL = "리츠·유틸리티"

# 거래소 파일의 업종(sector)만으로는 사이트 테마와 맞지 않는 종목
OVERRIDES = {
    # 빅테크 클라우드 & AI 플랫폼
    "MSFT": BIGTECH, "GOOGL": BIGTECH, "GOOG": BIGTECH, "AMZN": BIGTECH, "META": BIGTECH,
    "ORCL": BIGTECH, "SAP": BIGTECH, "IBM": BIGTECH, "NET": BIGTECH, "SNOW": BIGTECH, "ANT": BIGTECH,
    # 온디바이스
    "AAPL": DEVICE, "QCOM": DEVICE, "SONY": DEVICE, "GRMN": DEVICE, "MSI": DEVICE,
    # 전력·인프라 (전력 설비·냉각·네트워크·서버)
    "GEV": POWER, "VRT": POWER, "ETN": POWER, "GE": POWER, "EMR": POWER, "PWR": POWER, "CEG": POWER,
    "TT": POWER, "JCI": POWER, "CMI": POWER, "APH": POWER, "TEL": POWER, "GLW": POWER,
    "DELL": POWER, "HPE": POWER, "CSCO": POWER, "ANET": POWER,
    # 자율주행·로보틱스 & 엔터프라이즈 SW
    "TSLA": SW, "PLTR": SW, "CRM": SW, "UBER": SW, "ACN": SW, "APP": SW, "ADP": SW, "INFY": SW,
    "PANW": SW, "FTNT": SW,
    # AI 반도체 (장비·메모리·스토리지 포함)
    "ASML": AI_SEMI, "LRCX": AI_SEMI, "KLAC": AI_SEMI, "STX": AI_SEMI, "WDC": AI_SEMI, "SNDK": AI_SEMI,
    # 금융·핀테크
    "V": FIN, "MA": FIN, "BN": FIN, "BAM": FIN, "BRK.B": FIN,
    # 헬스케어 (생명과학 장비)
    "TMO": HEALTH, "DHR": HEALTH, "A": HEALTH,
    # 소비 (담배는 파일에서 Health Care 로 분류됨)
    "PM": CONSUMER, "BTI": CONSUMER, "MO": CONSUMER,
    # 산업재·방산·운송
    "MMM": INDUSTRIAL, "SPCX": INDUSTRIAL, "FDX": INDUSTRIAL, "DAL": INDUSTRIAL, "URI": INDUSTRIAL,
    # 에너지·소재 (파이프라인·화학·철강·건자재)
    "WMB": ENERGY, "EPD": ENERGY, "KMI": ENERGY, "TRP": ENERGY, "TRGP": ENERGY, "LNG": ENERGY,
    "OKE": ENERGY, "ENB": ENERGY, "ECL": ENERGY, "NUE": ENERGY, "MT": ENERGY, "CRH": ENERGY,
}

SECTOR_THEME = {
    "Technology": SW,
    "Finance": FIN,
    "Health Care": HEALTH,
    "Consumer Discretionary": CONSUMER,
    "Consumer Staples": CONSUMER,
    "Telecommunications": CONSUMER,
    "Industrials": INDUSTRIAL,
    "Energy": ENERGY,
    "Basic Materials": ENERGY,
    "Utilities": REIT_UTIL,
    "Real Estate": REIT_UTIL,
}

# 일반 보통주가 아닌 증권(워런트·권리·유닛·우선주·구조화 증권 등)
NON_COMMON = re.compile(
    r"\b(warrants?|rights?|units?|notes?|preferred|zones|depositary share representing)\b", re.I
)
# 심볼에 기호가 있어도 실제 보통주인 예외 (파일 표기 -> 화면 표기, 야후 표기)
SYMBOL_ALIASES = {"BRK/B": ("BRK.B", "BRK-B")}

NAME_TRIM = re.compile(
    r"\s+(Common Stock|Common Shares|Ordinary Shares?|American Depositary (Shares|Receipts)|"
    r"Sponos?ored ADR|Unsponsored|ADR|ADS|Limited Voting Shares|Subordinate Voting Shares|"
    r"(New York|NY) Registry Shares)\b.*$",
    re.I,
)
# 파일의 이름이 지저분해서 직접 지정
NAME_FIX = {"NGG": "National Grid PLC", "MT": "ArcelorMittal"}


def clean_name(name: str) -> str:
    name = re.sub(r"\s*\(.*$", "", name or "").strip()
    name = NAME_TRIM.sub("", name).strip(" ,")
    name = re.sub(r"\s{2,}", " ", name)
    name = re.sub(r"\b(\w+)( \1)\b", r"\1", name)  # "PLC PLC" -> "PLC"
    return name


def market_cap(row) -> float:
    try:
        return float(row.get("marketCap") or 0)
    except (TypeError, ValueError):
        return 0.0


def theme_of(symbol: str, sector: str, industry: str):
    if symbol in OVERRIDES:
        return OVERRIDES[symbol]
    if industry == "Semiconductors":
        return AI_SEMI
    return SECTOR_THEME.get(sector)


def main():
    rows = []
    for ex in ("nasdaq", "nyse", "amex"):
        for row in json.loads((SYMBOL_DIR / f"{ex}_full_tickers.json").read_text(encoding="utf-8")):
            row["ex"] = ex
            rows.append(row)

    picked, dropped = {}, []
    for row in sorted(rows, key=market_cap, reverse=True):
        raw = row["symbol"]
        if market_cap(row) < MIN_MARKET_CAP:
            break
        yf_symbol = None
        if raw in SYMBOL_ALIASES:
            symbol, yf_symbol = SYMBOL_ALIASES[raw]
        elif re.search(r"[\^/]", raw):
            continue
        else:
            symbol = raw
        if NON_COMMON.search(row.get("name", "")):
            continue
        if symbol in picked:
            continue
        theme = theme_of(symbol, row.get("sector") or "", row.get("industry") or "")
        if not theme:
            dropped.append((symbol, row.get("sector"), row.get("industry")))
            continue
        item = {
            "s": symbol,
            "n": NAME_FIX.get(symbol) or clean_name(row.get("name", "")) or symbol,
            "sec": row.get("sector") or "",
            "ind": (row.get("industry") or "").strip(),
            "mc": round(market_cap(row)),
            "ex": row["ex"],
            "th": theme,
        }
        if yf_symbol:
            item["yf"] = yf_symbol
        picked[symbol] = item

    stocks = list(picked.values())
    lines = ",\n".join("    " + json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in stocks)
    header = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "source": "https://github.com/rreichel3/US-Stock-Symbols (data/symbols)",
        "min_market_cap_usd": MIN_MARKET_CAP,
        "count": len(stocks),
    }
    head = json.dumps(header, ensure_ascii=False, indent=2)[:-2]
    OUT_PATH.write_text(head + ',\n  "stocks": [\n' + lines + "\n  ]\n}\n", encoding="utf-8")

    by_theme = {}
    for s in stocks:
        by_theme.setdefault(s["th"], []).append(s["s"])
    print(f"saved {OUT_PATH.relative_to(ROOT)}: {len(stocks)} stocks")
    for theme, syms in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
        print(f"  {theme} [{len(syms)}]: {' '.join(syms)}")
    if dropped:
        print("분류 못 해서 제외:", dropped)


if __name__ == "__main__":
    main()
