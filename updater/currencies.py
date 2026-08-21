from shared.utils import get_title
from updater.market_data import (
    fetch_gold_price,
    fetch_usd_rates,
    run_parallel_update,
)

TROY_OUNCE_TO_GRAMS = 31.1034768


def calculate_rates(base_code, props, usd_rates, gold_usd_ounce):
    """Calculates updated values for all 'To ' properties."""
    updated_props = {}

    # 1. Identify Target Currencies
    targets = {k: k[3:].strip().upper() for k in props.keys() if k.startswith("To ")}

    # 2. Find base to USD exchange rate
    if base_code == "GOLD":
        base_to_usd = float(gold_usd_ounce) / TROY_OUNCE_TO_GRAMS
    else:
        if base_code not in usd_rates:
            raise Exception(f"Could not find USD rate for {base_code}")
        base_to_usd = 1.0 / usd_rates[base_code]

    # 3. Calculate base to target exchange rate
    for prop_name, tgt_code in targets.items():
        if tgt_code not in usd_rates:
            raise Exception(f"Could not find USD rate for {tgt_code}")
        base_to_target = base_to_usd * usd_rates[tgt_code]
        updated_props[prop_name] = {"number": float(base_to_target)}

    return updated_props


def process_currency(page, usd_rates, gold_usd_ounce):
    """Return the Notion properties to update, or raise if processing fails."""
    props = page["properties"]

    # Extract Name (Title)
    code = get_title(props)
    if not code:
        raise Exception("Currency code is empty!")

    code = code.strip().upper()
    updated_props = calculate_rates(code, props, usd_rates, gold_usd_ounce)
    return updated_props


def update_currencies(database_id):
    """Update all Currency pages concurrently."""

    # Fetch one coherent rate snapshot per cycle
    usd_rates = fetch_usd_rates()
    gold_usd_ounce = fetch_gold_price()

    def process_with_snapshot(page):
        return process_currency(page, usd_rates, gold_usd_ounce)

    run_parallel_update(database_id, process_with_snapshot, "Currencies")
