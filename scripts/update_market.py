import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import yfinance as yf

OUTPUT_PATH = Path("data/market_data.json")

INDEX_TICKERS = {
    "sp500_spot": "^GSPC",
    "sp500_futures": "ES=F",
    "nasdaq_spot": "^IXIC",
    "nasdaq_futures": "NQ=F",
    "qqq": "QQQ",
}

STOCK_TICKERS = [
    "NVDA", "MSFT", "AAPL", "AMZN", "META", "SPCX", "INTC", "ANT", "ORCL",
    "GOOGL", "TSLA", "AVGO", "PLTR", "TSM", "GEV", "NFLX", "MU", "BAC",
]


def get_us_market_session(now_utc: datetime | None = None) -> str:
    now_et = (now_utc or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return "closed"
    mins = now_et.hour * 60 + now_et.minute
    if 4 * 60 <= mins < 9 * 60 + 30:
        return "premarket"
    if 9 * 60 + 30 <= mins < 16 * 60:
        return "regular"
    if 16 * 60 <= mins < 20 * 60:
        return "afterhours"
    return "closed"


def calc_rsi(close_series, period: int = 14):
    if close_series is None or len(close_series) < period + 1:
        return None
    delta = close_series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    last_loss = loss.iloc[-1]
    if last_loss is None or last_loss == 0:
        return 50.0
    rs = gain.iloc[-1] / last_loss
    return round(float(100 - (100 / (1 + rs))), 2)


def get_premarket_price(ticker: yf.Ticker, prev_close: float | None):
    pre_price = None

    try:
        pre_hist = ticker.history(period="1d", interval="1m", prepost=True)
        if pre_hist is not None and not pre_hist.empty and "Close" in pre_hist:
            now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
            et_idx = pre_hist.index.tz_convert("America/New_York") if pre_hist.index.tzinfo else pre_hist.index.tz_localize("UTC").tz_convert("America/New_York")
            pre_rows = pre_hist[
                (et_idx.date() == now_et.date())
                & ((et_idx.hour * 60 + et_idx.minute) >= 4 * 60)
                & ((et_idx.hour * 60 + et_idx.minute) < 9 * 60 + 30)
            ]["Close"].dropna()
            if not pre_rows.empty:
                pre_price = round(float(pre_rows.iloc[-1]), 2)
    except Exception:
        pre_price = None

    if pre_price is None:
        try:
            info = ticker.fast_info or {}
            cand = info.get("preMarketPrice") or info.get("pre_market_price")
            if cand and float(cand) > 0:
                pre_price = round(float(cand), 2)
        except Exception:
            pass

    if pre_price is None:
        try:
            info = ticker.info or {}
            cand = info.get("preMarketPrice")
            if cand and float(cand) > 0:
                pre_price = round(float(cand), 2)
        except Exception:
            pass

    pre_change_pct = None
    if pre_price is not None and prev_close and prev_close > 0:
        pre_change_pct = round(((pre_price - prev_close) / prev_close) * 100, 2)

    return pre_price, pre_change_pct


def fetch_quote(symbol: str, session: str = "regular", include_premarket: bool = False) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo", interval="1d")
        if hist is None or hist.empty or "Close" not in hist:
            return {"symbol": symbol, "session": session, "price": None, "change_pct": None}

        close = hist["Close"].dropna()
        if close.empty:
            return {"symbol": symbol, "session": session, "price": None, "change_pct": None}

        latest_price = round(float(close.iloc[-1]), 2)
        prev_price = float(close.iloc[-2]) if len(close) >= 2 else latest_price
        change_pct = round(((latest_price - prev_price) / prev_price) * 100, 2) if prev_price else 0.0

        ma20 = round(float(close.rolling(20).mean().iloc[-1]), 2) if len(close) >= 20 else None
        ma60 = round(float(close.rolling(60).mean().iloc[-1]), 2) if len(close) >= 60 else None
        ma120 = round(float(close.rolling(120).mean().iloc[-1]), 2) if len(close) >= 120 else None
        rsi14 = calc_rsi(close, 14)

        result = {
            "symbol": symbol,
            "session": session,
            "price": latest_price,
            "change_pct": change_pct,
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120,
            "rsi14": rsi14,
        }

        if include_premarket and session == "premarket":
            pre_price, pre_change_pct = get_premarket_price(ticker, latest_price)
            if pre_price is not None:
                result["premarket_price"] = pre_price
                result["price"] = pre_price
            if pre_change_pct is not None:
                result["premarket_change_pct"] = pre_change_pct
                result["change_pct"] = pre_change_pct

        return result
    except Exception as exc:
        return {"symbol": symbol, "session": session, "price": None, "change_pct": None, "error": str(exc)}


def main():
    now_utc = datetime.now(timezone.utc)
    session = get_us_market_session(now_utc)

    indices = {key: fetch_quote(sym, session=session, include_premarket=False) for key, sym in INDEX_TICKERS.items()}
    stocks = [fetch_quote(sym, session=session, include_premarket=True) for sym in STOCK_TICKERS]

    payload = {
        "updated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "session": session,
        "indices": indices,
        "stocks": stocks,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {OUTPUT_PATH} successfully (session={session}).")


if __name__ == "__main__":
    main()
