from updater.market_data import fetch_price, run_parallel_update


def format_ticker(ticker, market=None):
    """Applies market-specific ticker formatting for yfinance."""
    if market == "HK" and ".HK" not in ticker:
        return f"{ticker}.HK"
    if market == "CN" and ".S" not in ticker:
        return f"{ticker}.SS" if ticker.startswith("6") else f"{ticker}.SZ"
    if market == "Crypto" and "-" not in ticker:
        return f"{ticker}-USD"
    return ticker


def process_asset(page):
    """Return the Notion properties to update, or raise if processing fails."""
    props = page["properties"]

    # Extract Ticker (Text) and Market (Select)
    ticker_data = props.get("Ticker", {}).get("rich_text", [])
    ticker = ticker_data[0]["plain_text"].strip() if ticker_data else ""
    if not ticker:
        raise Exception("Ticker is empty!")

    market_data = props.get("Market", {}).get("select")
    market = market_data["name"] if market_data else None
    if not market:
        raise Exception("Market is empty!")

    target_ticker = format_ticker(ticker, market)
    price = fetch_price(target_ticker, market)
    return {"Price": {"number": float(price)}}


def update_assets(database_id):
    """Update all Asset pages concurrently."""
    run_parallel_update(database_id, process_asset, "Assets")
