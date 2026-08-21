"""Configure API clients and orchestrate transaction tracker operations."""

import httpx

from notion_client import Client
from openai import OpenAI
from tracker.config import TrackerConfig
from tracker.transactions import (
    TransactionCache,
    prepare_image,
    extract_transaction_data,
    create_transaction_page,
)

config = TrackerConfig()

# All API clients bypass shell proxy settings
notion_client = Client(auth=config.notion_token, client=httpx.Client(trust_env=False))
transaction_cache = TransactionCache(
    notion_client,
    config.cache_ttl_seconds,
)
openai_client = OpenAI(
    api_key=config.model_api_key,
    base_url=config.model_base_url,
    http_client=httpx.Client(trust_env=False),
)


def get_category_and_account():
    """Returns current category and account names for the web form."""
    category_map, account_map = transaction_cache.get_category_and_account_maps(
        config.category_db_id, config.account_db_id
    )
    return {"categories": list(category_map), "accounts": list(account_map)}


def extract_transaction_from_image(image_bytes):
    """Prepare an image and extract transaction data with the vision model."""

    # 1. Prepare image
    prepared_image = prepare_image(image_bytes)

    # 2. Get category_map and account_map
    category_map, account_map = transaction_cache.get_category_and_account_maps(
        config.category_db_id, config.account_db_id
    )

    # 3. AI Extraction
    return extract_transaction_data(
        prepared_image,
        openai_client,
        config.model_name,
        category_map,
        account_map,
    )


def create_transaction(transaction):
    """Creates an Income/Expense page from confirmed transaction data."""
    category_map, account_map = transaction_cache.get_category_and_account_maps(
        config.category_db_id, config.account_db_id
    )

    return create_transaction_page(
        notion_client, config.inc_exp_db_id, transaction, category_map, account_map
    )
