import os
import threading
import logging
from dotenv import load_dotenv

from notion_client import Client
from backend.core.state import global_state
from backend.services.asset_service import update_assets
from backend.services.currency_service import update_currencies
from backend.services.xact_service import (
    XactService,
    process_image,
    extract_xact_data,
    create_new_entry,
)


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
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        self.port = int(os.environ.get("TRIGGER_PORT", 5001))
        self.interval = 60 * 60
        self.lock = threading.Lock()  # prevents overlapping cycles


config = Config()
notion_client = Client(auth=config.token) if config.token else None
xact_service = XactService(notion_client) if notion_client else None


def run_all_updates():
    """Triggers both Assets and Currencies updates."""
    if not config.lock.acquire(blocking=False):
        logging.warning("Update already in progress. Skipping.")
        return

    try:
        global_state.start_cycle()

        if not config.token:
            msg = "INTERNAL_INTEGRATION_TOKEN missing."
            logging.error(msg)
            global_state.add_error("Config", msg)
            return

        # 1. Assets
        if config.assets_db_id:
            update_assets(notion_client, config.assets_db_id, global_state)
        else:
            msg = "Assets database ID missing."
            logging.error(msg)
            global_state.add_error("Config", msg)

        # 2. Currencies
        if config.currency_db_id:
            update_currencies(notion_client, config.currency_db_id, global_state)
        else:
            msg = "Currencies database ID missing."
            logging.error(msg)
            global_state.add_error("Config", msg)

    except Exception as e:
        logging.critical(f"Critical Error: {e}", exc_info=True)
        global_state.add_error("Critical", str(e))
    finally:
        snapshot = global_state.get_snapshot()
        message = (
            "✅ All updates successful"
            if snapshot["success"]
            else f"❌️ Completed with {len(snapshot['errors'])} errors"
        )
        logging.info("========== " + message + " ==========")

        global_state.finish_cycle()
        config.lock.release()


def get_cat_and_acct_opts():
    """
    Fetches current list of categories and accounts from Notion databases.

    Used by the frontend to populate dropdown options.
    """
    if not xact_service:
        return {"categories": [], "accounts": []}

    category_map = xact_service.fetch_category_map(config.category_db_id, refresh=True)
    account_map = xact_service.fetch_account_map(config.account_db_id, refresh=True)

    categories = list(category_map.keys())
    accounts = list(account_map.keys())
    return {"categories": categories, "accounts": accounts}


def get_xact_data_from_img(image_bytes):
    """Extracts transaction data from an image using Gemini AI."""
    if not xact_service:
        raise RuntimeError("Transaction (Income/Expense) service is not initialized.")

    processed_image = process_image(image_bytes)

    category_map = xact_service.fetch_category_map(config.category_db_id)
    account_map = xact_service.fetch_account_map(config.account_db_id)

    extracted_data = extract_xact_data(
        processed_image,
        config.gemini_api_key,
        category_map,
        account_map,
    )

    return extracted_data


def create_xact_entry(transaction):
    """Creates an Income/Expense entry from user-confirmed data."""
    if not xact_service:
        raise RuntimeError("Transaction (Income/Expense) service is not initialized.")

    category_map = xact_service.fetch_category_map(config.category_db_id)
    account_map = xact_service.fetch_account_map(config.account_db_id)

    notion_url = create_new_entry(
        notion_client, config.inc_exp_db_id, transaction, category_map, account_map
    )

    return notion_url
