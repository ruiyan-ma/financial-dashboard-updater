import os
import sys
import threading
import logging
import time
import httpx
from dotenv import load_dotenv

from notion_client import Client
from openai import OpenAI
from backend.core.state import global_state
from backend.services.asset_service import update_assets
from backend.services.currency_service import update_currencies
from backend.services.xact_service import (
    XactService,
    process_image,
    extract_xact_data,
    create_new_entry,
)

logger = logging.getLogger(__name__)


class Config:
    """Central configuration for the updater."""

    def __init__(self):
        load_dotenv()
        self.token = os.environ.get("INTERNAL_INTEGRATION_TOKEN")
        self.assets_db_id = os.environ.get("ASSETS_DATABASE_ID")
        self.currency_db_id = os.environ.get("CURRENCIES_DATABASE_ID")
        self.inc_exp_db_id = os.environ.get("INC_EXP_DATABASE_ID")
        self.category_db_id = os.environ.get("CATEGORIES_DATABASE_ID")
        self.account_db_id = os.environ.get("ACCOUNTS_DATABASE_ID")
        self.model_api_key = os.environ.get("MODEL_API_KEY")
        self.model_base_url = os.environ.get(
            "MODEL_BASE_URL", "https://api.siliconflow.cn/v1"
        )
        self.model_name = os.environ.get("MODEL_NAME", "Qwen/Qwen3.6-35B-A3B")
        self.xact_option_cache_ttl = int(os.environ.get("XACT_OPTION_CACHE_TTL", 300))
        self.port = int(os.environ.get("TRIGGER_PORT", 5001))
        self.lock = threading.Lock()  # prevents overlapping cycles

    def validate(self):
        """Exits the process if any required env var is missing."""
        required = {
            "INTERNAL_INTEGRATION_TOKEN": self.token,
            "ASSETS_DATABASE_ID": self.assets_db_id,
            "CURRENCIES_DATABASE_ID": self.currency_db_id,
            "INC_EXP_DATABASE_ID": self.inc_exp_db_id,
            "CATEGORIES_DATABASE_ID": self.category_db_id,
            "ACCOUNTS_DATABASE_ID": self.account_db_id,
            "MODEL_API_KEY": self.model_api_key,
        }
        missing = [name for name, val in required.items() if not val]
        if missing:
            print(
                f"\nFATAL: Missing required env vars: {', '.join(missing)}.\n"
                f"Set them in .env and restart.\n",
                file=sys.stderr,
            )
            sys.exit(1)


config = Config()
config.validate()

# All API clients bypass shell proxy settings
notion_client = Client(auth=config.token, client=httpx.Client(trust_env=False))
xact_service = XactService(
    notion_client,
    config.xact_option_cache_ttl,
)
openai_client = OpenAI(
    api_key=config.model_api_key,
    base_url=config.model_base_url,
    http_client=httpx.Client(trust_env=False),
)


def run_all_updates():
    """Triggers both Assets and Currencies updates."""
    if not config.lock.acquire(blocking=False):
        logger.warning("Update already in progress. Skipping.")
        return

    try:
        global_state.start_cycle()
        update_assets(notion_client, config.assets_db_id, global_state)
        update_currencies(notion_client, config.currency_db_id, global_state)

    except Exception as e:
        logger.exception("Unexpected error in run_all_updates.")
        global_state.add_error("Updater", str(e))
    finally:
        snapshot = global_state.get_snapshot()
        message = (
            "✅ All updates successful"
            if snapshot["success"]
            else f"❌️ Completed with {len(snapshot['errors'])} errors"
        )
        logger.info("========== %s ==========", message)

        global_state.finish_cycle()
        config.lock.release()


def get_cat_and_acct_opts():
    """
    Fetches current list of categories and accounts from Notion databases.

    Used by the frontend to populate dropdown options.
    """
    category_map, account_map = xact_service.fetch_category_and_account(
        config.category_db_id, config.account_db_id
    )

    categories = list(category_map.keys())
    accounts = list(account_map.keys())
    return {"categories": categories, "accounts": accounts}


def get_xact_data_from_img(image_bytes):
    """
    Extracts transaction data from an image using AI.

    Refreshes category and account if cache is expired or empty.
    """
    start_time = time.perf_counter()

    # 1. Process image
    processed_image = process_image(image_bytes)

    # 2. Fetch category_map and account_map
    category_map, account_map = xact_service.fetch_category_and_account(
        config.category_db_id, config.account_db_id
    )

    # 3. AI Extraction
    extracted_data = extract_xact_data(
        processed_image,
        openai_client,
        config.model_name,
        category_map,
        account_map,
    )

    logger.info(
        "Transaction extracted in %.2fs using %s",
        time.perf_counter() - start_time,
        config.model_name,
    )

    return extracted_data


def create_xact_entry(transaction):
    """Creates an Income/Expense entry from user-confirmed data."""
    category_map, account_map = xact_service.fetch_category_and_account(
        config.category_db_id, config.account_db_id
    )

    notion_url = create_new_entry(
        notion_client, config.inc_exp_db_id, transaction, category_map, account_map
    )

    return notion_url
