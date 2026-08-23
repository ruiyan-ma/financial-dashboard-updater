"""Fetch market data and update Notion database pages concurrently."""

import math
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import curl_cffi.requests
import yfinance as yf

from shared.utils import get_title, query_all_pages
from updater.notion import notion_client

# yfinance handles every market except US stocks and cryptocurrencies.
yf.config.network.retries = 2

NASDAQ_INFO_URL = "https://api.nasdaq.com/api/quote/{ticker}/info"
COINBASE_TICKER_URL = "https://api.exchange.coinbase.com/products/{pair}/ticker"
USD_RATES_URL = "https://open.er-api.com/v6/latest/USD"
GOLD_PRICE_URL = "https://api.gold-api.com/price/XAU"


logger = logging.getLogger(__name__)

_thread_state = threading.local()


# Suppress yfinance "symbol-not-found" noise (404 / delisted / no data).
_yfinance_noise = re.compile(r"HTTP Error 404|possibly delisted|No data found")


class _YFinanceNoiseFilter(logging.Filter):
    def filter(self, record):
        return not _yfinance_noise.search(record.getMessage())


logging.getLogger("yfinance").setLevel(logging.ERROR)
logging.getLogger("yfinance").addFilter(_YFinanceNoiseFilter())


def _get_market_session():
    """Returns one direct market-data session per worker thread."""
    if not hasattr(_thread_state, "market_session"):
        _thread_state.market_session = curl_cffi.requests.Session(
            impersonate="chrome", trust_env=False
        )
    return _thread_state.market_session


def _request_json(url, label, attempts=3, timeout=10):
    """Fetches JSON with bounded retries for transient provider failures."""
    error = None
    for attempt in range(attempts):
        try:
            response = _get_market_session().get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            error = e
            if attempt + 1 < attempts:
                delay = 2**attempt
                time.sleep(delay)

    raise RuntimeError(f"{label} request failed after {attempts} attempts") from error


def _parse_price(value):
    """Parses provider price strings such as '$1,234.56'."""
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    price = float(value)
    if not math.isfinite(price) or price <= 0:
        raise ValueError(f"Invalid price value: {value!r}")
    return price


def _fetch_nasdaq_price(ticker):
    """Fetches a US stock or ETF quote from Nasdaq."""
    url = NASDAQ_INFO_URL.format(ticker=ticker)
    for asset_class in ("stocks", "etf"):
        payload = _request_json(
            f"{url}?assetclass={asset_class}",
            f"Nasdaq {ticker}",
        )
        data = payload.get("data") or {}
        value = (data.get("primaryData") or {}).get("lastSalePrice")
        if value and value != "N/A":
            return _parse_price(value)
    raise RuntimeError(f"Nasdaq returned no price for {ticker}")


def _fetch_coinbase_price(ticker):
    """Fetches the cryptocurrency price from Coinbase."""
    pair = ticker if "-" in ticker else f"{ticker}-USD"
    payload = _request_json(
        COINBASE_TICKER_URL.format(pair=pair),
        f"Coinbase {pair}",
    )
    value = payload.get("price")
    if value:
        return _parse_price(value)
    raise RuntimeError(f"Coinbase returned no price for {pair}")


def _fetch_yfinance_price(ticker):
    """Fetches a quote from Yahoo Finance."""
    data = yf.Ticker(ticker, session=_get_market_session())
    hist = data.history(period="5d", interval="1d", timeout=10)
    if not hist.empty:
        return _parse_price(hist["Close"].iloc[-1])
    raise RuntimeError(f"Yahoo Finance returned no price for {ticker}")


def fetch_price(ticker, market):
    """Uses Nasdaq for US, Coinbase for crypto, and yfinance otherwise."""
    if market == "US":
        return _fetch_nasdaq_price(ticker)
    elif market == "Crypto":
        return _fetch_coinbase_price(ticker)
    else:
        return _fetch_yfinance_price(ticker)


def fetch_usd_rates():
    """Return USD exchange rates, raising if the provider data is unusable."""
    payload = _request_json(USD_RATES_URL, "USD exchange rates")
    if payload.get("result") != "success":
        raise RuntimeError(f"Exchange-rate provider returned {payload.get('result')!r}")

    rates = payload.get("rates")
    if not rates:
        raise RuntimeError("Exchange-rate provider returned no rates")

    mapping = {code.upper(): _parse_price(value) for code, value in rates.items()}
    mapping["USD"] = 1.0
    return mapping


def fetch_gold_price():
    """Return the USD gold price, raising if the provider data is unusable."""
    payload = _request_json(GOLD_PRICE_URL, "Gold price")
    value = payload.get("price")
    if value is None:
        raise RuntimeError("Gold-price provider returned no price")
    return _parse_price(value)


def run_parallel_update(db_id, process_func, label):
    """Update pages concurrently, then raise all page errors together."""

    def worker(page):
        try:
            new_props = process_func(page)
            notion_client.pages.update(page_id=page["id"], properties=new_props)
        except Exception as e:
            name = get_title(page["properties"]) or page.get("id")
            raise RuntimeError(f"{label} update failed for {name}") from e

    try:
        pages = query_all_pages(notion_client, db_id)
    except Exception as e:
        raise RuntimeError(f"Failed to query {label} database") from e

    if not pages:  # empty database is not an error
        logger.warning("No entries found for %s.", label)
        return

    errors = []
    total = len(pages)
    workers = min(5, (total + 2) // 3)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, page) for page in pages]
        for future in futures:
            error = future.exception()
            if error is not None:
                errors.append(error)

    success_count = total - len(errors)
    logger.info("Finished %s update: %d/%d success", label, success_count, total)

    if errors:
        raise ExceptionGroup(f"{label} update failed", errors)
