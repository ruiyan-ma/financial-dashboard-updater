"""Update market data once, then publish the Dashboard snapshot."""

import time

from updater.assets import update_assets
from updater.currencies import update_currencies
from shared.utils import required_env, setup_logging
from updater.snapshot import generate_snapshot

FORMULA_REFRESH_DELAY_SECONDS = 5


def main():
    """Run one complete Dashboard refresh task."""
    setup_logging()
    errors = []

    try:
        update_assets(required_env("ASSETS_DATABASE_ID"))
    except Exception as e:
        errors.append(e)

    try:
        update_currencies(required_env("CURRENCIES_DATABASE_ID"))
    except Exception as e:
        errors.append(e)

    if errors:
        raise ExceptionGroup("Market data update failed", errors)

    # Give Notion Formula and Rollup properties time to recalculate.
    time.sleep(FORMULA_REFRESH_DELAY_SECONDS)
    generate_snapshot()


if __name__ == "__main__":
    main()
