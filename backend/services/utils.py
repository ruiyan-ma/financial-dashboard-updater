import math
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from notion_client import Client
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOGS_DIR / "app.log"

logger = logging.getLogger(__name__)


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
    """
    Extract title from Notion page properties.

    Optimization: Title column is always named "Name"
    """
    title_prop = properties.get("Name", {})
    if title_prop["title"]:
        return title_prop["title"][0]["plain_text"]
    return None


def fetch_price(ticker):
    """Fetches price for a given ticker.

    Returns None when no usable price is found. Callers are responsible for
    deciding whether that constitutes a failure, so this function intentionally 
    stays silent on the common "not found" path.
    """
    try:
        data = yf.Ticker(ticker)
        # 1. Try fast_info (quickest, real-time)
        price = data.fast_info.get("last_price")
        # 2. Fallback to recent history (period="5d" covers weekends and holidays)
        if price is None:
            hist = data.history(period="5d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]
        if price is not None and math.isfinite(price):
            return price
        return None
    except Exception:
        # Unexpected error from yfinance itself (network, SSL, library bug)
        logger.warning("yfinance lookup failed for %s", ticker, exc_info=True)
        return None


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
