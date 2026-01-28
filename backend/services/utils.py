import logging
from concurrent.futures import ThreadPoolExecutor
from notion_client import Client
import yfinance as yf


class Colors:
    """ANSI color codes for terminal UI."""

    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    ENDC = "\033[0m"


def setup_logging():
    """Configures logging system."""
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Silence third-party noise
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google.genai").setLevel(logging.WARNING)


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
    """Fetches price for a given ticker."""
    try:
        data = yf.Ticker(ticker)
        # 1. Try fast_info (quickest, real-time)
        price = data.fast_info.get("last_price")
        # 2. Fallback to recent history (period="5d" covers weekends and holidays)
        if price is None:
            # Fallback to history
            hist = data.history(period="5d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]
        return price
    except Exception:
        return None


def run_parallel_update(client, database_id, process_func, update_state, label):
    """Generic runner for Notion database updates."""
    success_count = 0

    def worker(page):
        nonlocal success_count
        try:
            # The process_func should return (identifier, new_props) or raise exceptions
            identifier, new_props = process_func(page)
            client.pages.update(page_id=page["id"], properties=new_props)
            update_state.update_progress(f"✅ Updated {identifier}", "success")
            success_count += 1

        except Exception as e:
            name = get_title(page["properties"]) or page.get("id")
            update_state.update_progress(f"❌ Failed on {name}", "error")
            update_state.add_error(name, str(e))
            logging.error(f"Failed on {name}: {e}")

    try:
        results = client.databases.query(database_id=database_id).get("results", [])
        if not results:
            logging.warning(f"No entries found for {label}.")
            return

        total = len(results)
        workers = min(10, (total + 2) // 3)
        update_state.set_phase(f"Updating {label}...", total)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            executor.map(worker, results)

        logging.info(f"Finished {label} update: {success_count}/{total} success")

    except Exception as e:
        update_state.add_error(f"{label}", str(e))
        logging.exception(f"Error querying {label} database: {e}")
