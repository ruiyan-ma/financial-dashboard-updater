import os
import threading
import logging
from dotenv import load_dotenv

from backend.services.asset_service import update_assets
from backend.services.currency_service import update_currencies
from backend.core.state import global_state


class Config:
    """Central configuration for the updater."""

    def __init__(self):
        load_dotenv()
        self.token = os.environ.get("INTERNAL_INTEGRATION_TOKEN")
        self.assets_db_id = os.environ.get("ASSETS_DATABASE_ID")
        self.currency_db_id = os.environ.get("CURRENCIES_DATABASE_ID")
        self.port = int(os.environ.get("TRIGGER_PORT", 5001))
        self.interval = 60 * 60
        self.lock = threading.Lock()  # prevents overlapping cycles


config = Config()


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
            update_assets(config.token, config.assets_db_id, global_state)
        else:
            msg = "Assets database ID missing."
            logging.error(msg)
            global_state.add_error("Config", msg)

        # 2. Currencies
        if config.currency_db_id:
            update_currencies(config.token, config.currency_db_id, global_state)
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
