from backend.services.utils import fetch_price, run_parallel_update, get_title

TROY_OUNCE_TO_GRAMS = 31.1034768


def get_currency_rate(base, target):
    """Fetches exchange rate, attempting inverse pair if direct lookup fails."""
    if base == target:
        return 1.0

    # 1. Try Direct Pair (e.g., USDCNY=X)
    rate = fetch_price(f"{base}{target}=X")
    if rate is not None:
        return rate

    # 2. Try Inverse Pair (e.g., CNYUSD=X)
    inv = fetch_price(f"{target}{base}=X")
    if inv is not None and inv != 0:
        return 1.0 / inv

    return None


def calculate_rates(base_code, props):
    """Calculates updated values for all 'To ' properties."""
    updated_props = {}

    # 1. Identify Target Currencies
    targets = {k: k[3:].strip().upper() for k in props.keys() if k.startswith("To ")}

    # 2. Handle Base Price (Special case for Gold)
    base_price = 1.0
    if base_code == "GOLD":
        gold_usd_ounce = fetch_price("GC=F")
        if not gold_usd_ounce:
            raise Exception(f"Could not find price for Gold")
        base_price = float(gold_usd_ounce) / TROY_OUNCE_TO_GRAMS
        base_code = "USD"

    # 3. Calculate conversion for each target
    for prop_name, tgt_code in targets.items():
        rate = get_currency_rate(base_code, tgt_code)
        if rate is not None:
            updated_props[prop_name] = {"number": float(base_price * rate)}
        else:
            raise Exception(f"Could not find rate for {base_code} to {tgt_code}")

    return updated_props


def process_currency(page):
    """Processes a single currency row from Notion."""
    props = page["properties"]

    # Extract Name (Title)
    code = get_title(props)
    if not code:
        raise Exception("Currency code is empty!")

    code = code.strip().upper()
    updated_props = calculate_rates(code, props)
    return code, updated_props


def update_currencies(client, database_id, update_state):
    """Main entry for currency updates."""
    run_parallel_update(
        client, database_id, process_currency, update_state, "Currencies"
    )
