import json
from datetime import datetime, timezone
from pathlib import Path
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
    "NVDA", "MSFT", "AAPL", "AMZN", "META",
    "GOOGL", "TSLA", "AVGO", "PLTR", "TSM",
]


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


def fetch_quote(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo", interval="1d")
        if hist is None or hist.empty or "Close" not in hist:
            return {"symbol": symbol, "price": None, "change_pct": None}

        close = hist["Close"].dropna()
        if close.empty:
            return {"symbol": symbol, "price": None, "change_pct": None}

        latest_price = round(float(close.iloc[-1]), 2)
        prev_price = float(close.iloc[-2]) if len(close) >= 2 else latest_price
        change_pct = round(((latest_price - prev_price) / prev_price) * 100, 2) if prev_price else 0.0

        ma20 = round(float(close.rolling(20).mean().iloc[-1]), 2) if len(close) >= 20 else None
        ma60 = round(float(close.rolling(60).mean().iloc[-1]), 2) if len(close) >= 60 else None
        ma120 = round(float(close.rolling(120).mean().iloc[-1]), 2) if len(close) >= 120 else None
        rsi14 = calc_rsi(close, 14)

        return {
            "symbol": symbol,
            "price": latest_price,
            "change_pct": change_pct,
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120,
            "rsi14": rsi14,
        }
    except Exception as exc:
        return {"symbol": symbol, "price": None, "change_pct": None, "error": str(exc)}


def main():
    indices = {key: fetch_quote(sym) for key, sym in INDEX_TICKERS.items()}
    stocks = [fetch_quote(sym) for sym in STOCK_TICKERS]

    payload = {
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "indices": indices,
        "stocks": stocks,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {OUTPUT_PATH} successfully.")


if __name__ == "__main__":
    main()
