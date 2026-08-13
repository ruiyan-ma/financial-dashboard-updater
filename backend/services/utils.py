import math
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import curl_cffi.requests
import yfinance as yf

# yfinance handles every market except US stocks and cryptocurrencies.
yf.config.network.retries = 2

NASDAQ_INFO_URL = "https://api.nasdaq.com/api/quote/{ticker}/info"
COINBASE_TICKER_URL = "https://api.exchange.coinbase.com/products/{pair}/ticker"
USD_RATES_URL = "https://open.er-api.com/v6/latest/USD"
GOLD_PRICE_URL = "https://api.gold-api.com/price/XAU"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOGS_DIR / "app.log"

logger = logging.getLogger(__name__)

_thread_state = threading.local()


def _get_market_session():
    """Returns one direct market-data session per worker thread."""
    if not hasattr(_thread_state, "market_session"):
        _thread_state.market_session = curl_cffi.requests.Session(
            impersonate="chrome", trust_env=False
        )
    return _thread_state.market_session


class Colors:
    """ANSI color codes for terminal UI."""

    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"


def setup_logging():
    """Configures logging system with both console and file output."""
    LOGS_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Reset handlers so repeated calls (e.g. Flask debug reloader) don't duplicate output
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Silence third-party noise
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    # Suppress yfinance "symbol-not-found" noise (404 / delisted / no data).
    yfinance_noise = re.compile(r"HTTP Error 404|possibly delisted|No data found")

    class YFinanceNoiseFilter(logging.Filter):
        def filter(self, record):
            return not yfinance_noise.search(record.getMessage())

    logging.getLogger("yfinance").addFilter(YFinanceNoiseFilter())

    # Suppress noise from HTTPS handshakes / port scanners hitting the HTTP port.
    werkzeug_noise = re.compile(r"code 400, message Bad request (version|syntax)")

    class WerkzeugNoiseFilter(logging.Filter):
        def filter(self, record):
            return not werkzeug_noise.search(record.getMessage())

    logging.getLogger("werkzeug").addFilter(WerkzeugNoiseFilter())


def get_title(properties):
    """Extracts title from Notion page properties."""
    title = properties.get("Name", {}).get("title", [])
    return title[0]["plain_text"] if title else None


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
                logger.warning(
                    "%s request failed (attempt %d/%d); retrying in %ds: %s",
                    label,
                    attempt + 1,
                    attempts,
                    delay,
                    e,
                )
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
    return None


def _fetch_coinbase_price(ticker):
    """Fetches the cryptocurrency price from Coinbase."""
    pair = ticker if "-" in ticker else f"{ticker}-USD"
    payload = _request_json(
        COINBASE_TICKER_URL.format(pair=pair),
        f"Coinbase {pair}",
    )
    value = payload.get("price")
    return _parse_price(value) if value else None


def _fetch_yfinance_price(ticker):
    """Fetches a quote from Yahoo Finance."""
    data = yf.Ticker(ticker, session=_get_market_session())
    hist = data.history(period="5d", interval="1d", timeout=10)
    return None if hist.empty else _parse_price(hist["Close"].iloc[-1])


def fetch_price(ticker, market):
    """Uses Nasdaq for US, Coinbase for crypto, and yfinance otherwise."""
    try:
        if market == "US":
            provider = "Nasdaq"
            return _fetch_nasdaq_price(ticker)
        elif market == "Crypto":
            provider = "Coinbase"
            return _fetch_coinbase_price(ticker)
        else:
            provider = "Yahoo Finance"
            return _fetch_yfinance_price(ticker)
    except Exception as e:
        logger.warning("%s lookup failed for %s: %s", provider, ticker, e)
        return None


def fetch_usd_rates():
    """Returns a mapping of currency codes to their exchange rates against USD."""
    payload = _request_json(USD_RATES_URL, "USD exchange rates")
    if payload.get("result") != "success":
        raise RuntimeError(f"Exchange-rate provider returned {payload.get('result')!r}")

    rates = payload.get("rates") or {}
    mapping = {code.upper(): _parse_price(value) for code, value in rates.items()}
    mapping["USD"] = 1.0
    return mapping


def fetch_gold_price():
    """Returns the current USD price for one troy ounce of gold."""
    payload = _request_json(GOLD_PRICE_URL, "Gold price")
    value = payload.get("price")
    return _parse_price(value) if value else None


def run_parallel_update(client, database_id, process_func, update_state, label):
    """Generic runner for Notion database updates."""

    def worker(page):
        try:
            # The process_func should return (identifier, new_props) or raise exceptions
            identifier, new_props = process_func(page)
            client.pages.update(page_id=page["id"], properties=new_props)
            update_state.update_progress(f"✅ {identifier}", "success")
            return True

        except Exception as e:
            name = get_title(page["properties"]) or page.get("id")
            update_state.update_progress(f"❌ {name}", "error")
            update_state.add_error(name, str(e))
            logger.exception("[%s] Failed on %s", label, name)
            return False

    try:
        pages = client.databases.query(database_id=database_id).get("results", [])
        if not pages:
            logger.warning("No entries found for %s.", label)
            return

        total = len(pages)
        workers = min(5, (total + 2) // 3)
        update_state.set_phase(f"Updating {label}...", total)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            outcomes = list(executor.map(worker, pages))

        success_count = sum(outcomes)
        logger.info("Finished %s update: %d/%d success", label, success_count, total)

    except Exception as e:
        update_state.add_error(f"{label}", str(e))
        logger.exception("Error querying %s database", label)
